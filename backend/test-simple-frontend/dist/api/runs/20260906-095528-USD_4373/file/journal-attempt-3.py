from decimal import Decimal
import kit

# 1. Inspect tables
tables = kit.tables()
print("Tables:", tables)

coa = kit.table("coa")
print(f"COA count: {len(coa)}")
if len(coa) > 0:
    print("COA fields:", list(coa[0].keys()))
for r in coa:
    print("COA entry:", r)

for t_name in tables:
    if t_name != "coa":
        t = kit.table(t_name)
        sample = [row.get("name") or row for row in t[:10]] if len(t) > 0 else []
        print(f"Table '{t_name}' ({len(t)}):", sample)

# 2. Inspect rows
rows = kit.rows()
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
        f"R{i:02d} | cur:{cur} | cls:{cls} | dr:{dr} cr:{cr} | cp_st:{st} | cp_match:{mn} | cp_raw:{raw} | nar:{nar[:40]}"
    )

# 3. Detect accounts in COA
holding_type = None
for r in coa:
    tt = r.get("Trans Type", "")
    if any(
        k in tt.lower()
        for k in [
            "holding",
            "suspense",
            "unresolved",
            "unallocated",
            "clearing",
            "parked",
        ]
    ):
        holding_type = tt
        break
if not holding_type and len(coa) > 0:
    holding_type = coa[0].get("Trans Type")
print("Detected holding_type:", holding_type)


def get_cash_trans_type(currency):
    c = (currency or "").lower()
    for r in coa:
        tt = r.get("Trans Type", "")
        if c in tt.lower() and any(
            k in tt.lower() for k in ["cash", "bank", "operating", "current"]
        ):
            return tt
    for r in coa:
        tt = r.get("Trans Type", "")
        if c in tt.lower():
            return tt
    for r in coa:
        tt = r.get("Trans Type", "")
        if any(k in tt.lower() for k in ["cash", "bank"]):
            return tt
    return coa[0].get("Trans Type") if coa else None


def get_cp_trans_type(r):
    cpm = r.get("counterparty_match") or {}
    st = cpm.get("status")
    if st != "MATCH" and st != "PROBABLE":
        return holding_type
    cls = (r.get("classification") or "").lower()
    for row in coa:
        tt = row.get("Trans Type", "")
        if cls and cls in tt.lower():
            return tt
    return holding_type


# 4. Build journal entries
for i, r in enumerate(rows):
    batch_id = str(r.get("id") if r.get("id") is not None else f"row_{i}")
    raw_amt = r.get("credit") if r.get("credit") is not None else r.get("debit")
    amt_str = (
        f"{abs(Decimal(str(raw_amt))):.2f}"
        if raw_amt is not None
        else "0.00"
    )

    is_statement_debit = r.get("debit") is not None
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

bal = kit.batches_balance(rows, field="journal_lines")
print("Batches balance check:", bal)

kit.write_result(rows)
print(f"parsed {len(rows)} rows")