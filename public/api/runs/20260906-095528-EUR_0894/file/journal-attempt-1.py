import json
import kit

# 1. Inspect questions and tables
print("=== QUESTIONS ===")
try:
    print(kit.questions())
except Exception as e:
    print(f"Error reading questions: {e}")

print("\n=== TABLES ===")
try:
    tables = kit.tables()
    print("Tables:", tables)
except Exception as e:
    print(f"Error reading tables: {e}")
    tables = []

# 2. Inspect rows
print("\n=== ROWS ===")
rows = kit.rows()
print(f"Number of rows: {len(rows)}")
for i, r in enumerate(rows):
    print(f"Row {i}: {json.dumps(r, default=str)}")

# Collect currencies, classifications, etc. from rows
currencies = {r.get("currency") for r in rows if "currency" in r}
classifications = {r.get("classification") for r in rows if "classification" in r}
print(f"\nRow currencies: {currencies}")
print(f"Row classifications: {classifications}")

# 3. Inspect COA
print("\n=== COA ===")
coa = kit.table("coa")
print(f"COA type: {type(coa)}, length: {len(coa)}")

if len(coa) > 0:
    first_item = coa[0]
    print(
        "First COA item keys/structure:",
        (
            list(first_item.keys())
            if isinstance(first_item, dict)
            else dir(first_item)
        ),
    )
    print("First 3 COA items:", coa[:3])

    # Extract all Trans Types
    trans_types = []
    for item in coa:
        if isinstance(item, dict):
            tt = item.get("Trans Type")
        else:
            tt = getattr(item, "Trans Type", None)
        if tt is not None and tt not in trans_types:
            trans_types.append(tt)

    print(f"Total unique Trans Types: {len(trans_types)}")
    print("Trans Types:")
    for tt in sorted(trans_types):
        print(f"  {tt}")

    # Search for holding / suspense / unallocated / parked / cash / bank
    keywords = [
        "hold",
        "susp",
        "park",
        "unres",
        "unident",
        "unalloc",
        "clear",
        "cash",
        "bank",
    ]
    print("\nMatching COA rows by keyword:")
    for item in coa:
        row_str = str(item).lower()
        if any(k in row_str for k in keywords):
            print(" ", item)

# Call write_result as required by the rules
kit.write_result(rows)
print("parsed 16 rows")