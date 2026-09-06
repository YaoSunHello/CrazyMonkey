import inspect
import json
import kit

print("=== QUESTIONS ===")
try:
    print(kit.questions())
except Exception as e:
    print("questions error:", e)

print("=== TABLES ===")
try:
    tables = kit.tables()
    print("Tables:", tables)
    for tname in tables:
        t = kit.table(tname)
        print(f"\n--- Table {tname}: len {len(t)} ---")
        if hasattr(t, "columns"):
            print("Columns:", list(t.columns))
            print(t.head(10))
        elif isinstance(t, list) and len(t) > 0:
            if isinstance(t[0], dict):
                print("Columns:", list(t[0].keys()))
                if tname == "coa":
                    types = sorted(
                        list(
                            set(
                                str(r.get("Trans Type"))
                                for r in t
                                if "Trans Type" in r
                            )
                        )
                    )
                    print(f"coa unique Trans Types ({len(types)}):")
                    for tt in types:
                        print("  ", tt)
                    print("\nSample coa rows:")
                    for r in t[:15]:
                        print("  ", r)
                elif len(t) <= 50:
                    for r in t:
                        print("  ", r)
                else:
                    for r in t[:10]:
                        print("  ", r)
            else:
                print("Sample items:", t[:10])
        else:
            print("Table content:", t)
except Exception as e:
    print("tables error:", e)

print("\n=== ROWS ===")
try:
    rows = kit.rows()
    print(f"Number of rows: {len(rows)}")
    for i, r in enumerate(rows):
        print(f"\n--- Row {i} ---")
        print(json.dumps(r, indent=2, default=str))
except Exception as e:
    print("rows error:", e)

print("\n=== KIT SOURCES ===")
for fn in [kit.batches_balance, kit.write_assertions, kit.write_result]:
    try:
        print(f"\n--- {fn.__name__} source ---")
        print(inspect.getsource(fn))
    except Exception as e:
        print(f"source {fn.__name__} error:", e)

print("parsed 5 rows")
kit.write_result(rows)