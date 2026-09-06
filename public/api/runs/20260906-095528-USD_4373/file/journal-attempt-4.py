from decimal import Decimal
import kit


# Safely load tables whether they are lists, generators, or custom iterables
def load_table(name):
    t = kit.table(name)
    if isinstance(t, list):
        return t
    return list(t)


# 1. Inspect reference tables
tables = kit.tables()
print("Tables:", tables)

coa = load_table("coa")
print(f"COA count: {len(coa)}")
coa_trans_types = [
    r.get("Trans Type") for r in coa if r.get("Trans Type") is not None
]
print(f"COA Trans Types ({len(coa_trans_types)}):", coa_trans_types)

account_map = load_table("account_map") if "account_map" in tables else []
print(f"account_map count: {len(account_map)}")
for r in account_map:
    print("account_map entry:", r)

allocation_rules = (
    load_table("allocation_rules") if "allocation_rules" in tables else []
)
print(f"allocation_rules count: {len(allocation_rules)}")
for r in allocation_rules:
    print("allocation_rules entry:", r)

for t_name in tables:
    if t_name not in ("coa", "account_map", "allocation_rules"):
        t = load_table(t_name)
        print(f"Table '{t_name}' ({len(t)} entries):")
        for r in t[:10]:
            print(" ", r)

# 2. Inspect rows
rows = kit.rows()
if not isinstance(rows, list):
    rows = list(rows)
print(f"Rows count: {len(rows)}")

for i, r in enumerate(rows):
    dr = r.get("debit")
    cr = r.get("credit")
    cur = r.get("currency")
    cls = r.get("classification")
    cpm = r.get("counterparty_match") or {}
    st = cpm.get("status")
    mn = cpm.get("matched_name")
    raw = r.get("counterparty_raw")
    nar = r.get("narrative") or r.get("description") or ""
    print(
        f"R{i:02d} | id:{r.get('id')} | cur:{cur} | cls:{cls} | dr:{dr} cr:{cr} | cp_st:{st} | cp_match:{mn} | nar:{nar[:40]}"
    )

# 3. Identify holding / suspense account
holding_candidates = [
    tt
    for tt in coa_trans_types
    if any(
        w in tt.lower()
        for w in [
            "holding",
            "suspense",
            "unresolved",
            "unallocated",
            "clearing",
            "parked",
        ]
    )
]
print("Holding account candidates:", holding_candidates)
holding_type = holding_candidates[0] if holding_candidates else None
if not holding_type and coa_trans_types:
    holding_type = coa_trans_types[0]
print("Selected holding_type:", holding_type)

cash_candidates = [
    tt
    for tt in coa_trans_types
    if any(
        w in tt.lower()
        for w in ["cash", "bank", "operating", "current", "demand deposit"]
    )
]
print("Cash account candidates:", cash_candidates)


def get_cash_trans_type(currency):
    curr = (currency or "").strip().lower()

    # Check account_map first
    for row in account_map:
        row_str = " ".join(str(v).lower() for v in row.values())
        if curr in row_str and any(
            w in row_str for w in ["cash", "bank", "operating"]
        ):
            if "Trans Type" in row:
                return row["Trans Type"]

    # Check COA for currency + cash keyword
    for tt in coa_trans_types:
        ttl = tt.lower()
        if curr in ttl and any(
            w in ttl for w in ["cash", "bank", "operating", "current"]
        ):
            return tt

    # Check COA for currency alone
    for tt in coa_trans_types:
        if curr in tt.lower():
            return tt

    if cash_candidates:
        return cash_candidates[0]
    return coa_trans_types[0] if coa_trans_types else None


def get_cp_trans_type(r):
    cpm = r.get("counterparty_match") or {}
    st = cpm.get("status")
    # Unresolved counterparty must go to holding account
    if st not in ("MATCH", "PROBABLE") or not cpm.get("matched_name"):
        return holding_type

    cls = (r.get("classification") or "").strip()
    if not cls:
        return holding_type

    # 1. Check account_map for classification
    for row in account_map:
        for k, v in row.items():
            if str(v).strip().lower() == cls.lower():
                if "Trans Type" in row:
                    return row["Trans Type"]

    # 2. Check COA exact match for classification
    for tt in coa_trans_types:
        if tt.strip().lower() == cls.lower():
            return tt

    # 3. Check COA containing classification
    for tt in coa_trans_types:
        if cls.lower() in tt.lower():
            return tt

    # 4. Check COA containing classification keywords
    cls_words = [
        w for w in cls.lower().split() if w not in ["and", "or", "the", "of", "to"]
    ]
    if cls_words:
        for tt in coa_trans_types:
            if all(w in tt.lower() for w in cls_words):
                return tt

    return holding_type


# 4. Create journal lines for each row
for i, r in enumerate(rows):
    batch_id = str(r.get("id") if r.get("id") is not None else f"batch_{i+1}")

    dr = r.get("debit")
    cr = r.get("credit")
    if dr is not None and str(dr).strip() != "" and Decimal(str(dr)) != 0:
        raw_amt = abs(Decimal(str(dr)))
        is_statement_debit = True
    elif cr is not None and str(cr).strip() != "" and Decimal(str(cr)) != 0:
        raw_amt = abs(Decimal(str(cr)))
        is_statement_debit = False
    else:
        amt = r.get("amount")
        raw_amt = abs(Decimal(str(amt))) if amt is not None else Decimal("0.00")
        is_statement_debit = (
            (Decimal(str(amt)) < 0) if amt is not None else False
        )

    amt_str = f"{raw_amt:.2f}"

    # Cash leg: credit when statement is debit, debit when statement is credit
    cash_is_debit = not is_statement_debit
    cp_is_debit = is_statement_debit

    cash_tt = get_cash_trans_type(r.get("currency"))
    cp_tt = get_cp_trans_type(r)

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

# 5. Validate batches balance
bal = kit.batches_balance(rows, field="journal_lines")
print("Batches balance check:", bal)

parked_lines = sum(
    1
    for r in rows
    for line in r.get("journal_lines", [])
    if line.get("transaction_type") == holding_type
)
print(f"Total lines booked to holding account: {parked_lines}")

kit.write_result(rows)
print(f"parsed {len(rows)} rows")