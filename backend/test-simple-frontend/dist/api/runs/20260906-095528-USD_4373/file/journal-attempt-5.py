import csv
from decimal import Decimal
import inspect
import json
import os
import sys
import traceback
import kit

# 0. Inspect kit implementation to understand environment and prevent failures
try:
    with open(kit.__file__) as f:
        kit_src = f.read()
    idx = kit_src.find("def table")
    if idx != -1:
        print("KIT TABLE DEF:", kit_src[idx : idx + 350].replace("\n", " -- "))
    else:
        print("KIT FILE (no def table):", kit_src[:300].replace("\n", " -- "))
except Exception as e:
    print("Could not read kit.__file__:", e)


# Robust table loading
def normalize_table_data(t):
    if t is None:
        return []
    if isinstance(t, list):
        return t
    if hasattr(t, "to_dict"):
        try:
            return t.to_dict(orient="records")
        except Exception:
            return t.to_dict()
    if hasattr(t, "rows"):
        return list(t.rows)
    if hasattr(t, "data"):
        return list(t.data)
    if isinstance(t, dict):
        keys = list(t.keys())
        if keys and isinstance(t[keys[0]], (list, tuple)):
            n = len(t[keys[0]])
            return [{k: t[k][i] for k in keys} for i in range(n)]
        return [t]
    try:
        return list(t)
    except Exception:
        return []


def load_file_from_disk(name):
    search_dirs = [".", "..", "tables", "data", "/work", "/work/tables"]
    for d in search_dirs:
        if not os.path.exists(d):
            continue
        for ext in [".json", ".csv", ".tsv"]:
            path = os.path.join(d, f"{name}{ext}")
            if os.path.exists(path):
                print(f"Found {name} on disk at {path}")
                try:
                    if ext == ".json":
                        with open(path) as fp:
                            return normalize_table_data(json.load(fp))
                    elif ext in (".csv", ".tsv"):
                        delim = "\t" if ext == ".tsv" else ","
                        with open(path, newline="", encoding="utf-8-sig") as fp:
                            return list(csv.DictReader(fp, delimiter=delim))
                except Exception as e:
                    print(f"Error loading {path}: {e}")
    return []


def load_table_safe(name):
    # Try calling kit.table(name)
    try:
        if callable(getattr(kit, "table", None)):
            t = kit.table(name)
            data = normalize_table_data(t)
            if data:
                return data
    except Exception as e:
        print(
            f"kit.table('{name}') raised: {type(e).__name__}: {e} -- {traceback.format_exc().replace(chr(10), ' // ')}"
        )

    # Try subscripting kit.table[name] if table is a mapping
    try:
        if hasattr(kit, "table") and hasattr(kit.table, "__getitem__"):
            t = kit.table[name]
            data = normalize_table_data(t)
            if data:
                return data
    except Exception:
        pass

    # Try attributes on kit
    for attr in [name, f"_{name}", f"{name}_table"]:
        if hasattr(kit, attr):
            data = normalize_table_data(getattr(kit, attr))
            if data:
                return data

    # Fallback to disk
    return load_file_from_disk(name)


# 1. Inspect reference tables
tables = kit.tables() if callable(getattr(kit, "tables", None)) else []
print("Tables from kit.tables():", tables)

coa = load_table_safe("coa")
print(f"COA loaded count: {len(coa)}")


def extract_trans_types(coa_rows):
    res = []
    for r in coa_rows:
        if isinstance(r, dict):
            for k, v in r.items():
                if k.strip().lower() in (
                    "trans type",
                    "transtype",
                    "transaction_type",
                    "trans_type",
                ):
                    if v and str(v).strip():
                        res.append(str(v).strip())
                        break
        elif isinstance(r, str):
            res.append(r.strip())
    return list(dict.fromkeys(res))


coa_trans_types = extract_trans_types(coa)
print(f"COA Trans Types ({len(coa_trans_types)}):", coa_trans_types)

account_map = load_table_safe("account_map")
print(f"account_map count: {len(account_map)}")
for r in account_map:
    print("  account_map entry:", r)

allocation_rules = load_table_safe("allocation_rules")
print(f"allocation_rules count: {len(allocation_rules)}")
for r in allocation_rules:
    print("  allocation_rules entry:", r)

# 2. Identify holding / suspense account
suspense_candidates = [
    tt for tt in coa_trans_types if "suspense" in tt.lower()
]
holding_candidates = [tt for tt in coa_trans_types if "holding" in tt.lower()]
other_candidates = [
    tt
    for tt in coa_trans_types
    if any(
        w in tt.lower() for w in ["unallocated", "unresolved", "clearing", "parked"]
    )
]

if suspense_candidates:
    holding_type = suspense_candidates[0]
elif holding_candidates:
    holding_type = holding_candidates[0]
elif other_candidates:
    holding_type = other_candidates[0]
elif coa_trans_types:
    holding_type = coa_trans_types[0]
else:
    holding_type = "Holding Account"
print("Selected holding_type:", holding_type)

# 3. Cash account resolution
cash_candidates = [
    tt
    for tt in coa_trans_types
    if any(
        w in tt.lower()
        for w in [
            "cash",
            "bank",
            "operating",
            "current",
            "demand deposit",
            "nostro",
        ]
    )
]
print("Cash candidates:", cash_candidates)


def get_cash_trans_type(currency):
    curr = (currency or "").strip().lower()

    # Match in account_map
    for row in account_map:
        vals = [str(v).strip().lower() for v in row.values()]
        if any(curr == v or curr in v for v in vals):
            for k in ["Trans Type", "trans_type", "Account", "account"]:
                if k in row and row[k] in coa_trans_types:
                    return row[k]
            for v in row.values():
                if str(v).strip() in coa_trans_types:
                    return str(v).strip()

    # Currency + cash keywords in COA
    for tt in coa_trans_types:
        ttl = tt.lower()
        if curr in ttl and any(
            w in ttl for w in ["cash", "bank", "operating", "current"]
        ):
            return tt

    # Currency in COA
    for tt in coa_trans_types:
        if curr in tt.lower():
            return tt

    if cash_candidates:
        return cash_candidates[0]
    return coa_trans_types[0] if coa_trans_types else None


# 4. Counterparty account resolution
def get_cp_trans_type(r):
    cpm = r.get("counterparty_match") or {}
    st = cpm.get("status") if isinstance(cpm, dict) else None
    matched_name = (
        cpm.get("matched_name") if isinstance(cpm, dict) else cpm or None
    )

    # Unresolved counterparty books to holding account
    if st not in ("MATCH", "PROBABLE") and not matched_name:
        return holding_type

    cls = (r.get("classification") or "").strip()
    if not cls:
        return holding_type

    # 1. Match classification in account_map
    for row in account_map:
        vals = [str(v).strip().lower() for v in row.values()]
        if cls.lower() in vals:
            for k in ["Trans Type", "trans_type", "Account", "account"]:
                if k in row and row[k] in coa_trans_types:
                    return row[k]
            for v in row.values():
                if str(v).strip() in coa_trans_types:
                    return str(v).strip()

    # 2. Exact match in COA
    for tt in coa_trans_types:
        if tt.strip().lower() == cls.lower():
            return tt

    # 3. Substring match in COA
    for tt in coa_trans_types:
        if cls.lower() in tt.lower():
            return tt
    for tt in coa_trans_types:
        if tt.lower() in cls.lower():
            return tt

    # 4. Keyword match
    cls_words = [
        w for w in cls.lower().split() if w not in ["and", "or", "the", "of", "to"]
    ]
    if cls_words:
        for tt in coa_trans_types:
            if all(w in tt.lower() for w in cls_words):
                return tt

    return holding_type


# 5. Process statement rows
rows = kit.rows()
if not isinstance(rows, list):
    rows = list(rows)
print(f"Total rows to process: {len(rows)}")

for i, r in enumerate(rows):
    batch_id = str(r.get("id") if r.get("id") is not None else f"batch_{i+1}")

    dr = r.get("debit")
    cr = r.get("credit")
    amt = r.get("amount")

    if dr is not None and str(dr).strip() != "" and Decimal(str(dr)) != 0:
        raw_amt = abs(Decimal(str(dr)))
        is_statement_debit = True
    elif cr is not None and str(cr).strip() != "" and Decimal(str(cr)) != 0:
        raw_amt = abs(Decimal(str(cr)))
        is_statement_debit = False
    elif amt is not None and str(amt).strip() != "":
        val = Decimal(str(amt))
        raw_amt = abs(val)
        if "is_debit" in r:
            is_statement_debit = bool(r["is_debit"])
        else:
            is_statement_debit = val < 0
    else:
        raw_amt = Decimal("0.00")
        is_statement_debit = False

    amt_str = f"{raw_amt:.2f}"

    # Direction: cash leg is credit when statement is debit, debit when statement is credit
    cash_is_debit = not is_statement_debit
    cp_is_debit = is_statement_debit

    cash_tt = get_cash_trans_type(r.get("currency"))
    cp_tt = get_cp_trans_type(r)

    # Ensure transaction types are valid COA entries
    if cash_tt not in coa_trans_types and coa_trans_types:
        cash_tt = coa_trans_types[0]
    if cp_tt not in coa_trans_types and coa_trans_types:
        cp_tt = holding_type

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

# 6. Verify batches balance
bal = kit.batches_balance(rows, field="journal_lines")
print("Batches balance check:", bal)

parked_lines = sum(
    1
    for r in rows
    for line in r.get("journal_lines", [])
    if line.get("transaction_type") == holding_type
)
print(f"Total lines booked to holding account: {parked_lines}")

try:
    kit.write_assertions(
        [
            {"claim": "batches_balance", "result": bal},
            {"claim": "parked_lines", "result": parked_lines},
        ]
    )
except Exception as e:
    print("write_assertions notice:", e)

# 7. Write output
kit.write_result(rows)
print(f"parsed {len(rows)} rows")