import kit

print("=== TABLES ===")
tables = kit.tables()
print("Tables:", tables)

print("\n=== QUESTIONS ===")
try:
    print(kit.questions())
except Exception as e:
    print("questions error:", e)

print("\n=== ROWS ===")
rows = kit.rows()
print(f"Total rows: {len(rows)}")
for i, r in enumerate(rows):
    print(f"\n--- Row {i} ---")
    for k, v in r.items():
        print(f"  {k}: {v}")

print("\n=== COA TABLE ===")
try:
    coa = kit.table("coa")
    print(f"COA type: {type(coa)}, len: {len(coa) if hasattr(coa, '__len__') else 'no len'}")
    if hasattr(coa, "columns"):
        print("COA columns:", coa.columns)
    elif len(coa) > 0 and isinstance(coa[0], dict):
        print("COA keys:", list(coa[0].keys()))
    
    # Print coa entries
    for i, entry in enumerate(coa):
        print(f"  {i}: {entry}")
except Exception as e:
    print("COA error:", e)

for t in tables:
    if t != "coa":
        print(f"\n=== TABLE: {t} ===")
        try:
            tbl = kit.table(t)
            print(f"len: {len(tbl)}")
            if len(tbl) > 0:
                print("sample 0:", tbl[0])
                if len(tbl) <= 20:
                    for idx, row in enumerate(tbl):
                        print(f"  {idx}: {row}")
        except Exception as e:
            print(f"Table {t} error:", e)

assert False, "End of inspection pass"