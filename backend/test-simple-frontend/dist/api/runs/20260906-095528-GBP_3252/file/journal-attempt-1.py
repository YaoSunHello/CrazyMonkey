import json
import kit

print("=== TABLES ===")
tables = kit.tables()
print("Available tables:", tables)

print("\n=== QUESTIONS ===")
try:
    print(kit.questions())
except Exception as e:
    print("Error getting questions:", e)

print("\n=== ROWS ===")
rows = kit.rows()
print(f"Total rows: {len(rows)}")
for i, r in enumerate(rows):
    print(f"Row {i}:", json.dumps(r, default=str))

print("\n=== COA TABLE ===")
coa = kit.table("coa")
print(f"COA total rows: {len(coa)}")
if len(coa) > 0:
    print("COA columns:", list(coa[0].keys()))

# Print all trans types or full table if small
if len(coa) <= 250:
    print("\nAll COA rows:")
    for c in coa:
        print(c)
else:
    print("\nCOA Trans Types (sample 50):")
    for c in coa[:50]:
        print(c)

    print("\nSearching for Holding / Suspense / Parked in COA:")
    for c in coa:
        row_str = " ".join(str(v).lower() for v in c.values())
        if any(
            k in row_str
            for k in [
                "hold",
                "susp",
                "park",
                "unres",
                "unalloc",
                "clear",
                "sundry",
                "temp",
                "error",
                "unknown",
            ]
        ):
            print("MATCH HOLDING:", c)

    print("\nSearching for Cash / Bank in COA:")
    for c in coa:
        row_str = " ".join(str(v).lower() for v in c.values())
        if any(k in row_str for k in ["cash", "bank"]):
            print("MATCH CASH:", c)

# Let's also check any other tables available
for t_name in tables:
    if t_name != "coa":
        t = kit.table(t_name)
        print(f"\n=== TABLE: {t_name} (rows: {len(t)}) ===")
        if len(t) > 0:
            print("Columns:", list(t[0].keys()))
            if len(t) <= 30:
                for row in t:
                    print(row)
            else:
                for row in t[:10]:
                    print(row)

# Fail intentionally to inspect output
assert False, "Inspection complete"