import sys
import kit

print("=== INSPECTION START ===")
print("kit attributes:", dir(kit))

try:
    tables = kit.tables()
    print("kit.tables():", tables)
except Exception as e:
    print("kit.tables() failed:", type(e), e)

try:
    print("kit.table:", type(kit.table))
    t = kit.table("coa")
    print("type(kit.table('coa')):", type(t))
    if hasattr(t, "columns"):
        print("COA columns:", t.columns)
        print("COA head:\n", t.head())
    elif isinstance(t, list):
        print("COA list len:", len(t))
        if t:
            print("COA[0]:", t[0])
    elif isinstance(t, dict):
        print("COA dict keys:", list(t.keys())[:10])
    else:
        print("COA repr:", repr(t)[:200])
except Exception as e:
    print("kit.table('coa') failed:", type(e), e)

try:
    q = kit.questions()
    print("kit.questions():", q)
except Exception as e:
    print("kit.questions() failed:", type(e), e)

try:
    rows = kit.rows()
    print(f"kit.rows() count: {len(rows)}")
    for i, r in enumerate(rows):
        print(f"ROW {i}: {r}")
except Exception as e:
    print("kit.rows() failed:", type(e), e)

print("=== INSPECTION END ===")
sys.stdout.flush()

assert False, "Forced stop to inspect stdout"