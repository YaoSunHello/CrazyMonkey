import inspect
import json
import os
import sys
import kit

# Ensure line-buffered stdout so logs are never truncated
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

print("=== STARTING JOURNAL RUN ===", flush=True)

# 1. Print kit module info and functions
try:
    print(f"kit file: {kit.__file__}", flush=True)
    with open(kit.__file__) as f:
        src = f.read()
        print(f"kit source length: {len(src)}", flush=True)
        # Print function definitions in kit
        for line in src.splitlines():
            if line.startswith("def ") or line.startswith("class "):
                print("  ", line, flush=True)
except Exception as e:
    print(f"kit inspection note: {e}", flush=True)

# 2. Inspect available tables
tables = []
try:
    tables = kit.tables()
    print("Available tables:", tables, flush=True)
except Exception as e:
    print(f"kit.tables() error: {e}", flush=True)

# Helper to normalize table data to a list of dicts
def load_table_records(tbl_data):
    if hasattr(tbl_data, "to_dict"):
        try:
            return tbl_data.to_dict("records")
        except Exception:
            pass
    records = []
    try:
        for item in tbl_data:
            if isinstance(item, dict):
                records.append(item)
            elif hasattr(item, "_asdict"):
                records.append(item._asdict())
            elif hasattr(item, "keys"):
                records.append({k: item[k] for k in item.keys()})
            elif isinstance(item, (list, tuple)):
                records.append(dict(enumerate(item)))
            else:
                d = getattr(item, "__dict__", None)
                if d:
                    records.append(dict(d))
                else:
                    records.append({"Trans Type": str(item)})
    except Exception as e:
        print(f"Error converting records: {e}", flush=True)
    return records

# Inspect reference tables
for t in tables:
    if t != "coa":
        try:
            tbl = kit.table(t)
            recs = load_table_records(tbl)
            print(f"Table '{t}': {len(recs)} records. Sample 0: {recs[0] if recs else 'empty'}", flush=True)
        except Exception as e:
            print(f"Error reading table '{t}': {e}", flush=True)

# 3. Load and inspect COA
coa_raw = kit.table("coa")
coa_records = load_table_records(coa_raw)
print(f"COA total records: {len(coa_records)}", flush=True)
if coa_records:
    print("COA sample 0:", coa_records[0], flush=True)
    if len(coa_records) > 1:
        print("COA sample 1:", coa_records[1], flush=True)

all_trans_types = []
coa_by_currency = {}
holding_trans_types = []
cash_trans_types = []

for rec in coa_records:
    tt = rec.get("Trans Type") or rec.get("trans_type") or rec.get("TransType") or rec.get("Account Name")
    if not tt and 0 in rec:
        tt = rec[0]
    if not tt:
        continue
    tt = str(tt).strip()
    all_trans_types.append(tt)
    
    cur = rec.get("Currency") or rec.get("currency")
    if cur:
        cur = str(cur).strip().upper()
        coa_by_currency.setdefault(cur, []).append(rec)
        
    tt_lower = tt.lower()
    if any(w in tt_lower for w in ["hold", "suspense", "unresolved", "park", "clearing"]):
        holding_trans_types.append(tt)
    if any(w in tt_lower for w in ["cash", "bank", "operating"]):
        cash_trans_types.append(tt)

unique_trans_types = sorted(set(all_trans_types))
print(f"Unique Trans Types ({len(unique_trans_types)}):", unique_trans_types, flush=True)
print("Holding candidates:", holding_trans_types, flush=True)
print("Cash candidates:", cash_trans_types, flush=True)

# Determine holding account
holding_account = None
for cand in holding_trans_types:
    if "holding" in cand.lower():
        holding_account = cand
        break
if not holding_account and holding_trans_types:
    holding_account = holding_trans_types[0]
if not holding_account and unique_trans_types:
    holding_account = unique_trans_types[-1]

print(f"Selected holding account: {holding_account}", flush=True)

# 4. Inspect rows
rows = kit.rows()
print(f"=== INPUT ROWS ({len(rows)}) ===", flush=True)
for i, r in enumerate(rows):
    print(
        f"Row {i}: id={r.get('id')} amt={r.get('amount')} is_debit={r.get('is_debit')} "
        f"cur={r.get('currency')} cls={r.get('classification')} cp={r.get('counterparty_match')} "
        f"narr={repr(r.get('narrative'))}",
        flush=True
    )

def is_resolved(cp_match):
    if not cp_match:
        return False
    if isinstance(cp_match, dict):
        status = str(cp_match.get("status", "")).upper()
        if status in ("UNRESOLVED", "NONE", "UNMATCHED"):
            return False
        # If there is a matched name/party
        if cp_match.get("match") or cp_match.get("name") or cp_match.get("counterparty"):
            return True
        return False
    if isinstance(cp_match, str):
        return cp_match.upper() not in ("UNRESOLVED", "NONE", "UNMATCHED", "")
    return True

def find_cash_account(cur):
    if cur:
        cur_upper = str(cur).upper()
        # Look for cash accounts matching currency in coa_records
        for rec in coa_records:
            e_cur = rec.get("Currency")
            tt = rec.get("Trans Type") or rec.get("Account Name")
            if e_cur and str(e_cur).upper() == cur_upper and tt:
                if any(w in str(tt).lower() for w in ["cash", "bank", "operating"]):
                    return str(tt)
        # Look for currency string in Trans Type
        for tt in cash_trans_types:
            if cur_upper in tt.upper():
                return tt
    if cash_trans_types:
        return cash_trans_types[0]
    return unique_trans_types[0] if unique_trans_types else "Cash"

def find_counterparty_account(cls, cur):
    cls_str = str(cls).strip().lower() if cls else ""
    cur_str = str(cur).strip().upper() if cur else ""
    
    # Check exact/best match in coa_records
    best_match = None
    for rec in coa_records:
        e_cls = str(rec.get("Classification", "")).lower()
        e_cur = str(rec.get("Currency", "")).upper()
        tt = rec.get("Trans Type")
        if not tt:
            continue
        tt_str = str(tt)
        if cls_str and e_cls == cls_str:
            if cur_str and e_cur == cur_str:
                return tt_str
            if not best_match:
                best_match = tt_str
        elif cls_str and cls_str in tt_str.lower():
            if cur_str and e_cur == cur_str:
                return tt_str
            if not best_match:
                best_match = tt_str
                
    if best_match:
        return best_match
        
    for tt in unique_trans_types:
        if cls_str and cls_str in tt.lower():
            return tt
            
    return holding_account

# 5. Build journal entries
parked_count = 0
for i, r in enumerate(rows):
    batch_id = str(r.get("id") if r.get("id") is not None else f"row_{i}")
    
    raw_amt = r.get("amount", 0)
    amt_str = f"{abs(float(raw_amt)):.2f}"
    
    stmt_is_debit = bool(r.get("is_debit", True))
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
print(f"kit.batches_balance result: {bal}", flush=True)
print(f"Parked lines count: {parked_count}", flush=True)

# 7. Write result using kit.write_result
print("Writing result via kit.write_result...", flush=True)
kit.write_result(rows)

# Ensure /work/result.json is present and valid
result_path = "/work/result.json"
try:
    if not os.path.exists(result_path) or os.path.getsize(result_path) == 0:
        print(f"Writing direct backup to {result_path}...", flush=True)
        with open(result_path, "w") as f:
            json.dump(rows, f, indent=2, default=str)
    print(f"Confirmed {result_path} exists (size={os.path.getsize(result_path)} bytes)", flush=True)
except Exception as e:
    print(f"File verification note: {e}", flush=True)

print(f"parsed {len(rows)} rows", flush=True)