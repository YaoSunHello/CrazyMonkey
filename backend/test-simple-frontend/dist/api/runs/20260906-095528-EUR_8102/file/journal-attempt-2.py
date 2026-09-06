import inspect
import json
import kit

# 1. Inspect questions and tables
print("=== QUESTIONS ===")
try:
    print(kit.questions())
except Exception as e:
    print("questions err:", e)

print("=== TABLES ===")
try:
    print(kit.tables())
except Exception as e:
    print("tables err:", e)

# 2. Inspect COA
coa = kit.table("coa")
print(f"COA rows: {len(coa)}")
if len(coa) > 0:
    cols = list(coa[0].keys()) if isinstance(coa[0], dict) else []
    print(f"COA cols: {cols}")
    for r in coa:
        items = [f"{k}={v}" for k, v in r.items() if v is not None and str(v).strip()]
        print("  COA:", " | ".join(items))

# 3. Inspect Rows
rows = kit.rows()
print(f"Statement rows: {len(rows)}")
for i, r in enumerate(rows):
    cm = r.get("counterparty_match")
    print(
        f"R{i:02d}: id={r.get('id')} amt={r.get('amount')} "
        f"dr={r.get('is_debit')} cur={r.get('currency')} "
        f"cls={r.get('classification')} cpm={cm} narr={str(r.get('narrative'))[:35]}"
    )

# 4. Find key accounts in COA
# Column name for Trans Type
all_trans_types = [
    r.get("Trans Type") for r in coa if isinstance(r, dict) and "Trans Type" in r
]

# Look for holding / suspense account
holding_tt = None
for r in coa:
    tt = r.get("Trans Type", "")
    full_str = " ".join(str(v).lower() for v in r.values())
    if any(
        kw in full_str
        for kw in ["holding", "suspense", "park", "unresolved", "unallocated"]
    ):
        holding_tt = tt
        print(f"Found holding account: {tt} (row: {r})")
        break

if not holding_tt:
    # fallback search
    for tt in all_trans_types:
        if any(
            kw in tt.lower()
            for kw in ["holding", "suspense", "park", "unresolved"]
        ):
            holding_tt = tt
            break

# Helper to find cash account by currency
def get_cash_tt(currency):
    curr = str(currency or "").strip().upper()
    # Find matching cash/bank in coa
    candidates = []
    for r in coa:
        tt = r.get("Trans Type", "")
        row_str = " ".join(str(v) for v in r.values()).lower()
        if (
            "cash" in row_str
            or "bank" in row_str
            or "operating" in row_str
            or "checking" in row_str
        ):
            if curr and curr.lower() in row_str:
                return tt
            candidates.append(tt)
    if candidates:
        return candidates[0]
    return all_trans_types[0] if all_trans_types else ""

# Helper to find counterparty / nominal account
def get_counterpart_tt(row):
    # Check if counterparty is resolved
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
        return holding_tt, True  # parked

    # If resolved, look for classification match in COA
    cls_val = str(row.get("classification") or "").strip().lower()
    curr_val = str(row.get("currency") or "").strip().lower()

    # Exact match on Trans Type
    for tt in all_trans_types:
        if tt.lower() == cls_val:
            return tt, False

    # Check if classification matches any COA column or text
    for r in coa:
        tt = r.get("Trans Type", "")
        row_str = " ".join(str(v).lower() for v in r.values())
        if cls_val and cls_val in row_str:
            if curr_val and curr_val in row_str:
                return tt, False

    for r in coa:
        tt = r.get("Trans Type", "")
        row_str = " ".join(str(v).lower() for v in r.values())
        if cls_val and cls_val in row_str:
            return tt, False

    # Fallback to holding if no match found
    return holding_tt, True

# 5. Build journal lines for each row
parked_count = 0
for i, r in enumerate(rows):
    batch_id = str(r.get("id") or f"row_{i+1}")
    raw_amt = r.get("amount", 0)
    try:
        amt_str = f"{abs(float(str(raw_amt).replace(',', ''))):.2f}"
    except Exception:
        amt_str = str(raw_amt)

    # Determine direction: statement debit (money out) vs credit (money in)
    stmt_debit = r.get("is_debit")
    if stmt_debit is None:
        direction = str(r.get("direction", "")).lower()
        stmt_debit = direction in ("debit", "dr", "out")

    cash_account = get_cash_tt(r.get("currency"))
    cp_account, is_parked = get_counterpart_tt(r)
    if is_parked:
        parked_count += 1

    # Cash leg: credit if statement debit, debit if statement credit
    cash_debit = not bool(stmt_debit)
    cp_debit = bool(stmt_debit)

    r["journal_lines"] = [
        {
            "batch": batch_id,
            "amount": amt_str,
            "is_debit": cash_debit,
            "transaction_type": cash_account,
        },
        {
            "batch": batch_id,
            "amount": amt_str,
            "is_debit": cp_debit,
            "transaction_type": cp_account,
        },
    ]

# 6. Check batches balance and write assertions
bal_check = None
try:
    bal_check = kit.batches_balance(rows)
    print("Batches balance check:", bal_check)
except Exception as e:
    print("batches_balance err:", e)

try:
    if hasattr(kit, "write_assertions"):
        claims = [bal_check] if bal_check is not None else []
        kit.write_assertions(claims)
except Exception as e:
    print("write_assertions err:", e)

# 7. Write result
kit.write_result(rows)

print(
    f"posted {len(rows)} rows ({len(rows)*2} journal lines), parked {parked_count} lines to holding"
)