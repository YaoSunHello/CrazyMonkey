import inspect
import json
import sys
import traceback
import kit

# Ensure stdout is flushed on every print
sys.stdout.reconfigure(line_buffering=True)

print("=== INSPECT KIT ===", flush=True)
for name in [
    "batches_balance",
    "write_result",
    "write_assertions",
    "questions",
    "tables",
    "table",
]:
    if hasattr(kit, name):
        fn = getattr(kit, name)
        try:
            print(f"kit.{name}{inspect.signature(fn)}: {fn.__doc__}", flush=True)
        except Exception as e:
            print(f"kit.{name}: {e}", flush=True)


def load_table(name):
    try:
        t = kit.table(name)
        if hasattr(t, "to_dict"):
            return t.to_dict(orient="records")
        if isinstance(t, list):
            if len(t) > 0 and not isinstance(t[0], dict):
                if hasattr(t[0], "_asdict"):
                    return [r._asdict() for r in t]
                elif hasattr(t[0], "keys"):
                    return [dict(r) for r in t]
            return t
        res = list(t)
        if res and not isinstance(res[0], dict):
            if hasattr(res[0], "_asdict"):
                return [r._asdict() for r in res]
            elif hasattr(res[0], "keys"):
                return [dict(r) for r in res]
        return res
    except Exception as e:
        print(f"Error loading table {name}: {e}", flush=True)
        traceback.print_exc()
        return []


print("=== TABLES AVAILABLE ===", flush=True)
try:
    tbl_names = kit.tables()
    print("Tables:", tbl_names, flush=True)
except Exception as e:
    tbl_names = []
    print("tables err:", e, flush=True)

tables = {}
for tn in tbl_names:
    t_data = load_table(tn)
    tables[tn] = t_data
    print(f"Table '{tn}': {len(t_data)} rows", flush=True)
    if t_data:
        print(f"  Columns: {list(t_data[0].keys())}", flush=True)
        for sample_r in t_data[:5]:
            print(f"  sample: {sample_r}", flush=True)

# Inspect COA in detail
coa = tables.get("coa", [])
print(f"COA total rows: {len(coa)}", flush=True)
trans_types = []
tt_col = "Trans Type"
if coa:
    for k in coa[0].keys():
        if k.lower() == "trans type":
            tt_col = k
            break
    trans_types = [
        r.get(tt_col) for r in coa if isinstance(r, dict) and r.get(tt_col)
    ]
    print(
        f"Sample Trans Types ({len(trans_types)} total): {trans_types[:15]}",
        flush=True,
    )
    # Print all trans types
    print("All COA Trans Types:", flush=True)
    for tt in trans_types:
        print(f"  TT: {tt}", flush=True)

# Inspect account_map and allocation_rules if present
if "account_map" in tables:
    print("=== ACCOUNT MAP ===", flush=True)
    for r in tables["account_map"]:
        print("  map:", r, flush=True)

if "allocation_rules" in tables:
    print("=== ALLOCATION RULES ===", flush=True)
    for r in tables["allocation_rules"]:
        print("  rule:", r, flush=True)

# Inspect Rows
rows = kit.rows()
print(f"=== ROWS ({len(rows)}) ===", flush=True)
for i, r in enumerate(rows):
    print(f"Row {i}: {r}", flush=True)

# Identify Holding / Suspense account from COA
holding_tt = None
for r in coa:
    tt = str(r.get(tt_col, ""))
    full_str = " ".join(str(v).lower() for v in r.values())
    if any(
        kw in full_str
        for kw in ["holding", "suspense", "park", "unallocated", "unresolved"]
    ):
        holding_tt = tt
        print(f"Selected holding_tt: {holding_tt} from {r}", flush=True)
        break

if not holding_tt:
    for tt in trans_types:
        if any(
            kw in tt.lower()
            for kw in ["holding", "suspense", "park", "unresolved"]
        ):
            holding_tt = tt
            print(f"Selected holding_tt fallback: {holding_tt}", flush=True)
            break

# Function to pick cash account
def get_cash_account(row):
    currency = str(row.get("currency") or "").upper()
    # Check account_map if available
    if "account_map" in tables:
        for m in tables["account_map"]:
            m_str = " ".join(str(v).lower() for v in m.values())
            if "cash" in m_str or "bank" in m_str:
                if currency and currency.lower() in m_str:
                    for k, v in m.items():
                        if v in trans_types:
                            return v
    # Search in COA
    candidates = []
    for r in coa:
        tt = r.get(tt_col, "")
        r_str = " ".join(str(v).lower() for v in r.values())
        if "cash" in r_str or "bank" in r_str or "operating" in r_str:
            if currency and currency.lower() in r_str:
                return tt
            candidates.append(tt)
    if candidates:
        return candidates[0]
    return trans_types[0] if trans_types else "Cash"


# Function to pick counterpart account
def get_counterpart_account(row):
    cm = row.get("counterparty_match")
    is_res = False
    if cm and isinstance(cm, dict):
        status = str(cm.get("status", "")).upper()
        why = str(cm.get("why", "")).lower()
        matched = cm.get("name") or cm.get("match") or cm.get("matched")
        if status in ("MATCH", "PROBABLE") or (
            matched and "no counterparty" not in why and status != "UNRESOLVED"
        ):
            is_res = True

    if not is_res:
        return holding_tt or trans_types[0], True

    cls_val = str(row.get("classification") or "").strip()
    curr_val = str(row.get("currency") or "").strip().lower()

    # Check account_map
    if "account_map" in tables:
        for m in tables["account_map"]:
            vals = [str(v).lower() for v in m.values()]
            if cls_val.lower() in vals:
                for k, v in m.items():
                    if v in trans_types:
                        return v, False

    # Exact match on Trans Type
    for tt in trans_types:
        if tt.lower() == cls_val.lower():
            return tt, False

    # Check if classification text in COA
    for r in coa:
        tt = r.get(tt_col, "")
        r_str = " ".join(str(v).lower() for v in r.values())
        if cls_val.lower() and cls_val.lower() in r_str:
            if curr_val and curr_val in r_str:
                return tt, False

    for r in coa:
        tt = r.get(tt_col, "")
        r_str = " ".join(str(v).lower() for v in r.values())
        if cls_val.lower() and cls_val.lower() in r_str:
            return tt, False

    return holding_tt or trans_types[0], True


# Build journal lines
parked_count = 0
for i, r in enumerate(rows):
    batch_id = str(r.get("id") or f"batch_{i+1}")
    raw_amt = r.get("amount", 0)
    try:
        amt_str = f"{abs(float(str(raw_amt).replace(',', ''))):.2f}"
    except Exception:
        amt_str = str(raw_amt)

    stmt_debit = r.get("is_debit")
    if stmt_debit is None:
        direction = str(r.get("direction", "")).lower()
        stmt_debit = direction in ("debit", "dr", "out")

    cash_acc = get_cash_account(r)
    cp_acc, is_parked = get_counterpart_account(r)
    if is_parked:
        parked_count += 1

    # Cash leg is credit when stmt is debit, debit when stmt is credit
    cash_debit = not bool(stmt_debit)
    cp_debit = bool(stmt_debit)

    r["journal_lines"] = [
        {
            "batch": batch_id,
            "amount": amt_str,
            "is_debit": cash_debit,
            "transaction_type": cash_acc,
        },
        {
            "batch": batch_id,
            "amount": amt_str,
            "is_debit": cp_debit,
            "transaction_type": cp_acc,
        },
    ]

# Batches balance
bal_check = None
try:
    bal_check = kit.batches_balance(rows)
    print("batches_balance check:", bal_check, flush=True)
except Exception as e:
    print("batches_balance err:", e, flush=True)

try:
    if hasattr(kit, "write_assertions"):
        claims = []
        if bal_check is not None:
            if isinstance(bal_check, list):
                claims.extend(bal_check)
            else:
                claims.append(bal_check)
        kit.write_assertions(claims)
        print("write_assertions called successfully", flush=True)
except Exception as e:
    print("write_assertions err:", e, flush=True)

# Write result
kit.write_result(rows)
print(f"Result written successfully: {len(rows)} rows", flush=True)
print(
    f"posted {len(rows)} rows ({len(rows)*2} journal lines), parked {parked_count} lines to holding",
    flush=True,
)