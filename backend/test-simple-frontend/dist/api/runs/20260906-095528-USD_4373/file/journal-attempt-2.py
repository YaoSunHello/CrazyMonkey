import kit

print("Tables:", kit.tables())

# Safely inspect COA and other tables
for tbl_name in kit.tables():
    tbl = kit.table(tbl_name)
    print(f"Table '{tbl_name}' type: {type(tbl)}")
    # If iterable, convert to list or inspect first few
    try:
        tbl_list = list(tbl)
        print(f"Table '{tbl_name}' has {len(tbl_list)} items")
        if tbl_list:
            print(f"Sample from '{tbl_name}': {tbl_list[0]}")
    except Exception as e:
        print(f"Could not list '{tbl_name}': {e}")

# Safely inspect rows
rows = kit.rows()
print(f"Rows type: {type(rows)}")
try:
    rows_list = list(rows)
    print(f"Rows count: {len(rows_list)}")
    for i, r in enumerate(rows_list[:5]):
        print(f"Row {i}: {r}")
except Exception as e:
    print(f"Could not list rows: {e}")

# Inspect questions
try:
    print("Questions:", kit.questions())
except Exception as e:
    print(f"Questions error: {e}")

# Intentional stop to inspect all tables and row structures
assert False, "Inspection pass: dump table schemas and row contents to stdout."