import kit

# 1. Inspect tables and COA
print("Tables:", kit.tables())
coa = kit.table("coa")
print(f"COA has {len(coa)} entries. Columns: {coa.columns if hasattr(coa, 'columns') else (list(coa[0].keys()) if coa else 'empty')}")

# Print first few entries of COA
for i, entry in enumerate(coa[:20]):
    print(f"COA[{i}]: {entry}")

# Search for holding / suspense / cash accounts in COA
trans_types = []
for entry in coa:
    tt = entry.get("Trans Type") or entry.get("trans_type") or entry.get("Transaction Type")
    trans_types.append((tt, entry))

print(f"Total trans types: {len(trans_types)}")

# Let's inspect rows
rows = kit.rows()
print(f"Total rows: {len(rows)}")
for i, r in enumerate(rows):
    print(f"Row {i}: {r}")

# Print questions if any
print("Questions:", kit.questions())

# Find holding account
holding_candidates = [
    tt for tt, entry in trans_types 
    if any(term in str(entry).lower() for term in ["holding", "suspense", "unresolved", "unallocated", "clearing", "parked"])
]
print("Holding candidates:", holding_candidates)

# Find cash / bank accounts
cash_candidates = [
    tt for tt, entry in trans_types 
    if any(term in str(entry).lower() for term in ["cash", "bank", "operating", "checking", "current"])
]
print("Cash candidates:", cash_candidates)

# Print all trans types to inspect their names
print("All Trans Types:")
for tt, entry in trans_types:
    print("  ", tt, "-->", entry)

# Try to match rows to accounts
# Let's check how rows indicate cash leg vs counterparty leg
# And create journal lines accordingly
# To be safe on attempt 1, let's build the best mapping we can
# If we need to see stdout, we can raise an assertion or let's see how batches_balance works.

enriched_rows = []
for i, r in enumerate(rows):
    r_copy = dict(r)
    # determine batch id
    batch_id = r.get("batch") or f"BATCH-{i+1:04d}"
    
    # Amount
    amt = str(r.get("amount", "0.00")).replace(",", "").replace("-", "")
    # Check debit / credit on the row
    # In statement row: "The cash leg is the credit when the statement row is a debit, and the debit when it is a credit."
    # How is row debit/credit represented? Let's check r's keys.
    is_stmt_debit = False
    if "is_debit" in r:
        is_stmt_debit = bool(r["is_debit"])
    elif "direction" in r:
        is_stmt_debit = r["direction"].lower() in ["debit", "dr", "out", "outflow", "withdrawal", "payment"]
    elif "type" in r:
        is_stmt_debit = r["type"].lower() in ["debit", "dr", "out", "withdrawal", "payment"]
    elif float(r.get("amount", 0)) < 0:
        is_stmt_debit = True
        
    cash_is_debit = not is_stmt_debit
    cp_is_debit = is_stmt_debit
    
    # Find matching trans types (placeholder logic for attempt 1 inspection if needed)
    # We will pick the first cash and holding candidates if not sure
    cash_tt = cash_candidates[0] if cash_candidates else (trans_types[0][0] if trans_types else "Cash")
    cp_tt = holding_candidates[0] if holding_candidates else (trans_types[-1][0] if trans_types else "Holding")
    
    # But wait! If counterparty_match resolved to something, let's see what row holds
    # Let's see what counterparty fields exist
    
    lines = [
        {"batch": batch_id, "amount": amt, "is_debit": cash_is_debit, "transaction_type": cash_tt},
        {"batch": batch_id, "amount": amt, "is_debit": cp_is_debit, "transaction_type": cp_tt}
    ]
    r_copy["journal_lines"] = lines
    enriched_rows.append(r_copy)

# Verify batches balance
bal = kit.batches_balance(enriched_rows)
print("Batches balance check:", bal)

# Intentional assertion to review stdout in attempt 1 if not completely confident,
# OR write result if we want verifier feedback.
# Let's assert False to inspect all data clearly first!
assert False, "Inspection pass: reviewing stdout for COA, rows, and account mappings."