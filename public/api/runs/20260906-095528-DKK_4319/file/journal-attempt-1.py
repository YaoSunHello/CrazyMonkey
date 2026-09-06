import json
import kit

# 1. Questions
print("=== QUESTIONS ===")
try:
    q = kit.questions()
    print(json.dumps(q, indent=2, default=str))
except Exception as e:
    print(f"Error reading questions: {e}")

# 2. Tables and Reference Data
print("\n=== TABLES ===")
try:
    tables = kit.tables()
    print("Available tables:", tables)
    for name in tables:
        tbl = kit.table(name)
        print(f"\n--- Table: {name} ---")
        if hasattr(tbl, "shape"):
            print("Shape:", tbl.shape)
            print("Columns:", tbl.columns.tolist())
            print(tbl.to_string())
        elif isinstance(tbl, list):
            print(f"Count: {len(tbl)}")
            for idx, item in enumerate(tbl):
                print(f"  [{idx}]: {item}")
        elif isinstance(tbl, dict):
            print(f"Dict keys: {list(tbl.keys())}")
            for k, v in tbl.items():
                print(f"  {k}: {v}")
        else:
            print("Type:", type(tbl))
            print(tbl)
except Exception as e:
    print(f"Error reading tables: {e}")

# 3. Statement Rows
print("\n=== ROWS ===")
rows = kit.rows()
print(f"Total rows: {len(rows)}")
for i, r in enumerate(rows):
    print(f"\n--- Row {i} ---")
    for k, v in sorted(r.items()):
        print(f"  {k}: {v}")

# 4. Candidates / Lookups for Counterparties
print("\n=== CANDIDATES FOR ROWS ===")
for i, r in enumerate(rows):
    narrative = r.get("narrative", "")
    print(f"\nRow {i} narrative: {repr(narrative)}")
    print(f"  counterparty_match: {r.get('counterparty_match')}")
    for t_name in kit.tables():
        if t_name == "coa":
            continue
        try:
            cands = kit.candidates(narrative, [t_name])
            print(f"  Candidates in {t_name}: {cands}")
        except Exception as e:
            try:
                tbl = kit.table(t_name)
                cands = kit.candidates(narrative, [tbl])
                print(f"  Candidates in {t_name} (obj): {cands}")
            except Exception as e2:
                print(f"  Candidate lookup error on {t_name}: {e2}")

# 5. Check batches_balance behavior
print("\n=== TEST BATCHES_BALANCE ===")
try:
    test_batch = [
        {
            "journal_lines": [
                {
                    "batch": "test-1",
                    "amount": "100.00",
                    "is_debit": True,
                    "transaction_type": "Test",
                },
                {
                    "batch": "test-1",
                    "amount": "100.00",
                    "is_debit": False,
                    "transaction_type": "Test",
                },
            ]
        }
    ]
    bb_res = kit.batches_balance(test_batch)
    print("batches_balance result:", bb_res)
except Exception as e:
    print(f"Error testing batches_balance: {e}")

# 6. Create initial placeholder journal lines to trigger verifier check & inspect output
enriched = []
for i, r in enumerate(rows):
    row_copy = dict(r)
    amt = str(r.get("amount", "0.00"))
    batch_id = f"batch_{i+1}"
    row_copy["journal_lines"] = [
        {
            "batch": batch_id,
            "amount": amt,
            "is_debit": True,
            "transaction_type": "__INSPECTION__",
        },
        {
            "batch": batch_id,
            "amount": amt,
            "is_debit": False,
            "transaction_type": "__INSPECTION__",
        },
    ]
    enriched.append(row_copy)

kit.write_result(enriched)
print("inspected 10 rows")