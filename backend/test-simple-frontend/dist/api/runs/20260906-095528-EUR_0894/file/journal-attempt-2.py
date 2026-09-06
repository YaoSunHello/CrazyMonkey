import json
import sys
import kit

# Ensure unbuffered output
sys.stdout.reconfigure(line_buffering=True)

print("=== START JOURNAL PROCESSING ===", flush=True)

# 1. Questions & Tables
try:
    print(f"Questions: {kit.questions()}", flush=True)
except Exception as e:
    print(f"Questions error: {e}", flush=True)

try:
    tables = kit.tables()
    print(f"Tables: {tables}", flush=True)
except Exception as e:
    print(f"Tables error: {e}", flush=True)

# 2. Inspect Rows
rows = kit.rows()
print(f"Total rows: {len(rows)}", flush=True)

# Print summary of each row
for i, r in enumerate(rows):
    c_match = r.get("counterparty_match", {})
    status = (
        c_match.get("status")
        if isinstance(c_match, dict)
        else getattr(c_match, "status", None)
    )
    name = (
        c_match.get("matched_name")
        if isinstance(c_match, dict)
        else getattr(c_match, "matched_name", None)
    )
    print(
        f"Row {i:02d}: amt={r.get('amount')}, deb={r.get('debit')}, cred={r.get('credit')}, "
        f"curr={r.get('currency')}, class={r.get('classification')}, "
        f"cp_status={status}, cp_name={name}",
        flush=True,
    )

# 3. Load and Inspect Chart of Accounts
coa_raw = kit.table("coa")
print(f"COA raw type: {type(coa_raw)}", flush=True)

if hasattr(coa_raw, "to_dict"):
    coa_records = coa_raw.to_dict(orient="records")
elif hasattr(coa_raw, "iterrows"):
    coa_records = [row.to_dict() for _, row in coa_raw.iterrows()]
elif isinstance(coa_raw, list):
    coa_records = [
        dict(r) if hasattr(r, "items") else r
        for r in coa_raw
        if isinstance(r, dict) or hasattr(r, "items")
    ]
else:
    coa_records = []

print(f"COA record count: {len(coa_records)}", flush=True)
if coa_records:
    print(f"COA sample record keys: {list(coa_records[0].keys())}", flush=True)
    print(f"COA sample record: {coa_records[0]}", flush=True)

# Extract all Trans Types
coa_trans_types = []
for item in coa_records:
    tt = item.get("Trans Type") if isinstance(item, dict) else None
    if tt and tt not in coa_trans_types:
        coa_trans_types.append(tt)

print(f"Unique Trans Types ({len(coa_trans_types)}):", flush=True)
for tt in sorted(coa_trans_types):
    print(f"  {tt}", flush=True)

# Print all COA rows for full visibility
print("--- ALL COA RECORDS ---", flush=True)
for cr in coa_records:
    print(f"  {cr}", flush=True)


# 4. Helper to find Trans Types
def find_matching_trans_type(candidates, default=None):
    for c in candidates:
        for tt in coa_trans_types:
            if c.lower() == tt.lower():
                return tt
    for c in candidates:
        for tt in coa_trans_types:
            if c.lower() in tt.lower():
                return tt
    return default


# Find holding account
holding_keywords = [
    "holding",
    "suspense",
    "unallocated",
    "unresolved",
    "parked",
    "clearing",
    "unknown",
]
holding_candidates = []
for cr in coa_records:
    row_str = " ".join(str(v).lower() for v in cr.values())
    if any(hk in row_str for hk in holding_keywords):
        tt = cr.get("Trans Type")
        if tt and tt not in holding_candidates:
            holding_candidates.append(tt)

print(f"Holding candidates: {holding_candidates}", flush=True)
holding_account = holding_candidates[0] if holding_candidates else None
print(f"Selected holding account: {holding_account}", flush=True)


# Find cash account by currency
def get_cash_account(currency):
    curr = (currency or "").upper()
    # Check records matching currency and cash/bank
    for cr in coa_records:
        row_str = " ".join(str(v).lower() for v in cr.values())
        if ("cash" in row_str or "bank" in row_str) and (curr.lower() in row_str):
            tt = cr.get("Trans Type")
            if tt:
                return tt
    # Check if Trans Type contains cash and curr
    for tt in coa_trans_types:
        if "cash" in tt.lower() and curr.lower() in tt.lower():
            return tt
    # Any cash account
    for tt in coa_trans_types:
        if "cash" in tt.lower() or "bank" in tt.lower():
            return tt
    return coa_trans_types[0] if coa_trans_types else "Cash"


# Find counterpart account by classification and currency
def get_counterpart_account(classification, currency, is_resolved):
    if not is_resolved or not holding_account:
        return holding_account

    cls_str = (classification or "").lower()
    curr_str = (currency or "").lower()

    # Look for exact or keyword match in COA records
    best_tt = None
    for cr in coa_records:
        row_str = " ".join(str(v).lower() for v in cr.values())
        tt = cr.get("Trans Type")
        if not tt:
            continue
        # Avoid cash accounts for counterpart leg
        if "cash" in tt.lower() or "bank" in tt.lower():
            continue
        if cls_str in row_str:
            if curr_str and curr_str in row_str:
                return tt
            if not best_tt:
                best_tt = tt

    if best_tt:
        return best_tt

    # Search in trans type directly
    for tt in coa_trans_types:
        if "cash" in tt.lower() or "bank" in tt.lower():
            continue
        if cls_str in tt.lower():
            return tt

    return holding_account


# 5. Extract amount and statement debit/credit for each row
def parse_amount_and_direction(r):
    debit_val = r.get("debit")
    credit_val = r.get("credit")

    def clean_val(v):
        if v is None or v == "":
            return None
        try:
            return float(str(v).replace(",", "").strip())
        except ValueError:
            return None

    d_num = clean_val(debit_val)
    c_num = clean_val(credit_val)

    if d_num is not None and d_num > 0:
        return f"{d_num:.2f}", True
    if c_num is not None and c_num > 0:
        return f"{c_num:.2f}", False

    amt_val = clean_val(r.get("amount"))
    if amt_val is not None:
        if r.get("is_debit") is not None:
            return f"{abs(amt_val):.2f}", bool(r["is_debit"])
        if amt_val < 0:
            return f"{abs(amt_val):.2f}", True
        else:
            return f"{abs(amt_val):.2f}", False

    return "0.00", False


# 6. Build Journal Lines
parked_count = 0
for i, r in enumerate(rows):
    batch_id = r.get("id") or f"batch_{i + 1}"
    amount_str, is_stmt_debit = parse_amount_and_direction(r)
    currency = r.get("currency")
    classification = r.get("classification")

    # Check resolution status
    c_match = r.get("counterparty_match", {})
    status = (
        c_match.get("status")
        if isinstance(c_match, dict)
        else getattr(c_match, "status", None)
    )
    matched_name = (
        c_match.get("matched_name")
        if isinstance(c_match, dict)
        else getattr(c_match, "matched_name", None)
    )
    is_resolved = status in ("MATCH", "PROBABLE") and bool(matched_name)

    cash_tt = get_cash_account(currency)
    cp_tt = get_counterpart_account(classification, currency, is_resolved)

    if cp_tt == holding_account:
        parked_count += 1

    # Direction rule:
    # "The cash leg is the credit when the statement row is a debit, and the debit when it is a credit."
    cash_is_debit = not is_stmt_debit
    cp_is_debit = is_stmt_debit

    r["journal_lines"] = [
        {
            "batch": str(batch_id),
            "amount": amount_str,
            "is_debit": cash_is_debit,
            "transaction_type": cash_tt,
        },
        {
            "batch": str(batch_id),
            "amount": amount_str,
            "is_debit": cp_is_debit,
            "transaction_type": cp_tt,
        },
    ]

print(f"\nConstructed journal lines for {len(rows)} rows.", flush=True)
print(f"Total lines parked to holding account: {parked_count}", flush=True)

# 7. Check double entry balance
try:
    bal_res = kit.batches_balance(rows)
    print(f"batches_balance result: {bal_res}", flush=True)
except Exception as e:
    print(f"Error checking batches_balance: {e}", flush=True)

# 8. Write Result
kit.write_result(rows)
print(f"parsed {len(rows)} rows", flush=True)