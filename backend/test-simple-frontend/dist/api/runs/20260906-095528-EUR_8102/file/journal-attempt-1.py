import json
import kit

print("=== TABLES ===")
tables = kit.tables()
print("Tables:", tables)

print("\n=== QUESTIONS ===")
try:
    print(kit.questions())
except Exception as e:
    print("Error getting questions:", e)

print("\n=== ROWS (16 rows) ===")
rows = kit.rows()
print(f"Total rows: {len(rows)}")
for i, r in enumerate(rows):
    print(f"--- Row {i} ---")
    print(json.dumps(r, indent=2, default=str))

print("\n=== COA TABLE ===")
try:
    coa = kit.table("coa")
    print(f"COA type: {type(coa)}, length: {len(coa)}")
    if len(coa) > 0:
        print("COA columns/sample:", coa[0] if isinstance(coa, list) else coa)
        # If list of dicts:
        if isinstance(coa, list) and isinstance(coa[0], dict):
            keys = list(coa[0].keys())
            print("COA keys:", keys)
            # Print unique values or interesting rows
            print(f"First 10 rows of COA:")
            for r in coa[:10]:
                print(r)
            
            # Look for holding / suspense / cash / bank / etc.
            keywords = ["hold", "suspense", "park", "unresolved", "cash", "bank", "clearing", "error"]
            print("\nMatching holding/cash rows:")
            for r in coa:
                line_str = " ".join(str(v) for v in r.values()).lower()
                if any(kw in line_str for kw in keywords):
                    print("  MATCH:", r)
            
            # Print all Trans Types if feasible
            trans_types = [r.get("Trans Type") for r in coa if "Trans Type" in r]
            print(f"\nTotal Trans Types: {len(trans_types)}")
            print("Trans Types sample (first 40):", trans_types[:40])
            if len(trans_types) <= 200:
                print("All Trans Types:", trans_types)
except Exception as e:
    print("Error reading COA:", e)

# Also check other tables
for t_name in tables:
    if t_name != "coa":
        try:
            t_data = kit.table(t_name)
            print(f"\n=== Table: {t_name} (len: {len(t_data)}) ===")
            if len(t_data) > 0:
                print("Sample row:", t_data[0])
                if len(t_data) <= 50:
                    for row in t_data:
                        print(row)
        except Exception as e:
            print(f"Error reading {t_name}:", e)

assert False, "Inspection completed"