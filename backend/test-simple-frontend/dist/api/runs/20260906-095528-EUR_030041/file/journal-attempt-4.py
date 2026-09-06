import inspect
import json
import os
import sys
import kit

# Keep stdout line-buffered
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

# 1. Inspect COA table and available columns
coa = kit.table("coa")

coa_columns = []
if hasattr(coa, "columns"):
    cols = coa.columns
    coa_columns = list(cols() if callable(cols) else cols)
elif hasattr(coa, "headers"):
    headers = coa.headers
    coa_columns = list(headers() if callable(headers) else headers)

if not coa_columns:
    # Test known column names
    for cand in ["Trans Type", "trans_type", "Currency", "currency", "Classification", "classification", "Type", "Account", "Account Name"]:
        try:
            coa.values(cand)
            coa_columns.append(cand)
        except Exception:
            pass

# Extract all Trans Types
all_trans_types = []
try:
    all_trans_types = list(coa.values("Trans Type"))
except Exception as e:
    print(f"Error fetching Trans Type: {e}")

# Build coa_records
coa_records = []
if all_trans_types:
    col_data = {}
    for c in coa_columns:
        try:
            col_data[c] = list(coa.values(c))
        except Exception:
            pass
    for j in range(len(all_trans_types)):
        rec = {c: col_data[c][j] for c in col_data if len(col_data[c]) > j}
        coa_records.append(rec)

# Identify Holding account candidates
holding_account = None
for rec in coa_records:
    tt = rec.get("Trans Type", "")
    cls_val = str(rec.get("Classification", "")).lower()
    if any(w in cls_val or w in tt.lower() for w in ["hold", "suspense", "unresolved", "park", "clearing"]):
        holding_account = tt
        break

if not holding_account and all_trans_types:
    for tt in all_trans_types:
        if any(w in tt.lower() for w in ["hold", "suspense", "unresolved", "park", "clearing"]):
            holding_account = tt
            break

# 2. Inspect reference tables for counterparty resolution
ref_tables = [t for t in kit.tables() if t != "coa"]

# 3. Load rows and inspect fields
rows = kit.rows()

def parse_amt(val):
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return abs(float(val))
    s = str(val).replace(",", "").replace(" ", "").replace("€", "").replace("$", "").replace("£", "")
    try:
        return abs(float(s))
    except Exception:
        return None

def get_row_amount_and_direction(r):
    # Check debit / credit columns
    deb = parse_amt(r.get("debit"))
    cred = parse_amt(r.get("credit"))
    if deb is not None and deb > 0:
        return deb, True
    if cred is not None and cred > 0:
        return cred, False

    for d_k, c_k in [("withdrawal", "deposit"), ("paid_out", "paid_in"), ("dr", "cr")]:
        deb = parse_amt(r.get(d_k))
        cred = parse_amt(r.get(c_k))
        if deb is not None and deb > 0:
            return deb, True
        if cred is not None and cred > 0:
            return cred, False

    for k in ["amount", "amt", "value", "net", "total"]:
        amt_val = parse_amt(r.get(k))
        if amt_val is not None:
            if r.get("is_debit") is not None:
                stmt_is_debit = bool(r.get("is_debit"))
            elif r.get("direction"):
                stmt_is_debit = str(r.get("direction")).lower() in ("debit", "dr", "out", "outflow", "withdrawal", "paid_out")
            else:
                try:
                    raw = float(str(r.get(k)).replace(",", ""))
                    stmt_is_debit = (raw < 0)
                except Exception:
                    stmt_is_debit = True
            return amt_val, stmt_is_debit

    return 0.0, True

def is_resolved(cp_match):
    if not cp_match:
        return False
    if isinstance(cp_match, dict):
        st = str(cp_match.get("status", "")).upper()
        if st in ("UNRESOLVED", "NONE", "UNMATCHED", "CANNOT_VERIFY"):
            return False
        return bool(cp_match.get("matched_name") or cp_match.get("match") or cp_match.get("counterparty"))
    if isinstance(cp_match, str):
        return cp_match.upper() not in ("UNRESOLVED", "NONE", "UNMATCHED", "CANNOT_VERIFY", "")
    return True

# Helper to find cash account matching currency
def find_cash_account(cur):
    cur_str = str(cur).strip().upper() if cur else ""
    # 1. Match in coa_records
    for rec in coa_records:
        r_tt = str(rec.get("Trans Type", "")).strip()
        r_cur = str(rec.get("Currency", "")).strip().upper()
        r_cls = str(rec.get("Classification", "")).strip().lower()
        if any(w in r_cls or w in r_tt.lower() for w in ["cash", "bank", "operating", "current"]):
            if cur_str and (r_cur == cur_str or cur_str in r_tt.upper()):
                return r_tt
    # 2. Match in all_trans_types
    for tt in all_trans_types:
        if any(w in tt.lower() for w in ["cash", "bank", "operating", "current"]):
            if cur_str and cur_str in tt.upper():
                return tt
    # Fallback to any cash account
    for tt in all_trans_types:
        if any(w in tt.lower() for w in ["cash", "bank", "operating", "current"]):
            return tt
    return all_trans_types[0] if all_trans_types else None

# Helper to find counterparty account
def find_counterparty_account(cls, cur):
    cls_str = str(cls).strip().lower() if cls else ""
    cur_str = str(cur).strip().upper() if cur else ""
    best = None
    for rec in coa_records:
        r_tt = str(rec.get("Trans Type", "")).strip()
        r_cls = str(rec.get("Classification", "")).strip().lower()
        r_cur = str(rec.get("Currency", "")).strip().upper()
        if cls_str and r_cls == cls_str:
            if cur_str and r_cur == cur_str:
                return r_tt
            if not best:
                best = r_tt
        elif cls_str and (cls_str in r_cls or cls_str in r_tt.lower() or r_cls in cls_str):
            if cur_str and r_cur == cur_str:
                return r_tt
            if not best:
                best = r_tt

    if best:
        return best

    for tt in all_trans_types:
        if cls_str and (cls_str in tt.lower() or tt.lower() in cls_str):
            return tt

    return holding_account

# 4. Attempt upstream resolution where counterparty is not resolved
for r in rows:
    cp = r.get("counterparty_match")
    if not is_resolved(cp):
        narr = r.get("narrative", "")
        # Try candidate matching against reference tables
        for tbl_name in ref_tables:
            try:
                tbl = kit.table(tbl_name)
                # Check candidate matches
                cands = kit.candidates(narr, tbl, limit=1)
                if cands:
                    cand_name, score = cands[0]
                    if score >= 0.85:
                        r["counterparty_match"] = {
                            "status": "PROBABLE",
                            "matched_name": cand_name,
                            "table": tbl_name,
                            "confidence": round(float(score), 2),
                            "why": f"Near match in {tbl_name} with similarity {score:.2f}"
                        }
                        break
            except Exception:
                pass

# 5. Build journal entries
parked_count = 0
for i, r in enumerate(rows):
    batch_id = str(r.get("id") or r.get("batch") or f"batch_{i:03d}")
    amt_val, stmt_is_debit = get_row_amount_and_direction(r)
    amt_str = f"{amt_val:.2f}"

    # "The cash leg is the credit when the statement row is a debit, and the debit when it is a credit."
    cash_is_debit = not stmt_is_debit
    cp_is_debit = stmt_is_debit

    cur = r.get("currency")
    cls = r.get("classification")
    cp_match = r.get("counterparty_match")

    cash_tt = find_cash_account(cur)
    if not is_resolved(cp_match):
        cp_tt = holding_account
        parked_count += 1
    else:
        cp_tt = find_counterparty_account(cls, cur)
        if cp_tt == holding_account:
            parked_count += 1

    r["journal_lines"] = [
        {
            "batch": batch_id,
            "amount": amt_str,
            "is_debit": cash_is_debit,
            "transaction_type": cash_tt,
        },
        {
            "batch": batch_id,
            "amount": amt_str,
            "is_debit": cp_is_debit,
            "transaction_type": cp_tt,
        },
    ]

# 6. Verify batches balance
bal = kit.batches_balance(rows)

# 7. Write result
kit.write_result(rows)

# Ensure /work/result.json is present
result_path = "/work/result.json"
try:
    if not os.path.exists(result_path) or os.path.getsize(result_path) == 0:
        with open(result_path, "w") as f:
            json.dump(rows, f, indent=2, default=str)
except Exception:
    pass

# Debug output at the end so it is captured in verifier tail
print("=== DEBUG SUMMARY ===")
print("COA Trans Types:", all_trans_types)
print("Holding account:", holding_account)
print("COA records sample:", coa_records[:4])
print("Row 0 keys:", list(rows[0].keys()) if rows else [])
if rows:
    r0 = rows[0]
    print(f"Row 0 amount={get_row_amount_and_direction(r0)} jl={r0.get('journal_lines')}")
print(f"Balance check: {bal}")
print(f"Parked lines: {parked_count}")
print(f"parsed {len(rows)} rows")