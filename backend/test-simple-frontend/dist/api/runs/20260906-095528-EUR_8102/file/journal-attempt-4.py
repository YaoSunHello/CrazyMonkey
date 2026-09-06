import sys
import traceback
import kit

# Ensure stdout is flushed on every print
sys.stdout.reconfigure(line_buffering=True)


def normalize_table(t):
    if t is None:
        return []
    if hasattr(t, "to_dict"):
        try:
            return t.to_dict(orient="records")
        except Exception:
            pass
    if isinstance(t, dict):
        vals = list(t.values())
        if vals and isinstance(vals[0], list):
            keys = list(t.keys())
            records = []
            for idx in range(len(vals[0])):
                records.append({k: t[k][idx] for k in keys if idx < len(t[k])})
            return records
        else:
            return [{"key": k, "value": v} for k, v in t.items()]
    if isinstance(t, list):
        records = []
        for item in t:
            if isinstance(item, dict):
                records.append(item)
            elif hasattr(item, "_asdict"):
                records.append(item._asdict())
            elif hasattr(item, "keys"):
                records.append(dict(item))
            else:
                records.append(item)
        return records
    try:
        return normalize_table(list(t))
    except Exception:
        return []


# 1. Discover mounted tables
tbl_names = kit.tables() if hasattr(kit, "tables") else []
print("Mounted tables:", tbl_names)

# 2. Parse Chart of Accounts (COA)
coa_raw = kit.table("coa") if hasattr(kit, "table") else None
coa_records = normalize_table(coa_raw)

coa_types = []
tt_col_name = None

if coa_records:
    if isinstance(coa_records[0], str):
        coa_types = [str(x).strip() for x in coa_records if str(x).strip()]
    elif isinstance(coa_records[0], dict):
        for k in coa_records[0].keys():
            k_clean = k.lower().replace("_", " ").strip()
            if k_clean in ("trans type", "transtype", "transaction type"):
                tt_col_name = k
                break
        if not tt_col_name:
            for k in coa_records[0].keys():
                if "type" in k.lower():
                    tt_col_name = k
                    break
        if not tt_col_name:
            tt_col_name = list(coa_records[0].keys())[0]

        for r in coa_records:
            if isinstance(r, dict) and tt_col_name in r:
                val = r[tt_col_name]
                if val is not None and str(val).strip():
                    coa_types.append(str(val).strip())

print(
    f"COA loaded: {len(coa_types)} transaction types (column '{tt_col_name}')"
)
print("COA Trans Types:", coa_types)

# 3. Identify Holding / Suspense account from COA
holding_tt = None
for tt in coa_types:
    t_low = tt.lower()
    if any(
        kw in t_low
        for kw in [
            "holding",
            "suspense",
            "park",
            "unallocated",
            "unresolved",
            "clearing",
            "temporary",
        ]
    ):
        holding_tt = tt
        break

if not holding_tt and coa_records and isinstance(coa_records[0], dict):
    for r in coa_records:
        r_str = " ".join(str(v).lower() for v in r.values())
        if any(
            kw in r_str
            for kw in [
                "holding",
                "suspense",
                "park",
                "unallocated",
                "unresolved",
            ]
        ):
            holding_tt = str(r.get(tt_col_name, "")).strip()
            break

if not holding_tt and coa_types:
    for tt in coa_types:
        if "other" in tt.lower() or "misc" in tt.lower():
            holding_tt = tt
            break

if not holding_tt and coa_types:
    holding_tt = coa_types[-1]

print(f"Selected holding account: {holding_tt}")

# 4. Load other reference tables
ref_tables = {}
for tn in tbl_names:
    if tn != "coa":
        ref_tables[tn] = normalize_table(kit.table(tn))
        print(f"Table '{tn}': {len(ref_tables[tn])} records")
        if ref_tables[tn] and isinstance(ref_tables[tn][0], dict):
            print(f"  columns: {list(ref_tables[tn][0].keys())}")

# 5. Map cash accounts by currency
cash_map = {}
for tt in coa_types:
    t_low = tt.lower()
    if any(w in t_low for w in ["cash", "bank", "operating"]):
        for curr in ["EUR", "USD", "GBP", "CHF", "JPY", "AUD", "CAD"]:
            if curr.lower() in t_low and curr not in cash_map:
                cash_map[curr] = tt

if coa_records and isinstance(coa_records[0], dict):
    for r in coa_records:
        r_str = " ".join(str(v).lower() for v in r.values())
        tt_val = str(r.get(tt_col_name, "")).strip()
        if any(w in r_str for w in ["cash", "bank", "operating"]):
            for curr in ["EUR", "USD", "GBP", "CHF", "JPY"]:
                if curr.lower() in r_str and curr not in cash_map:
                    cash_map[curr] = tt_val

default_cash = None
for tt in coa_types:
    if any(w in tt.lower() for w in ["cash", "bank"]):
        default_cash = tt
        break
if not default_cash and coa_types:
    default_cash = coa_types[0]

print("Cash account map:", cash_map, "default:", default_cash)


def get_cash_tt(row):
    curr = str(row.get("currency") or "").upper()
    return cash_map.get(curr, default_cash)


# 6. Load rows and inspect
rows = kit.rows()
print(f"Loaded {len(rows)} statement rows.")


def is_resolved(row):
    cm = row.get("counterparty_match")
    if not cm or not isinstance(cm, dict):
        return False
    status = str(cm.get("status", "")).upper()
    why = str(cm.get("why", "")).lower()
    matched = cm.get("name") or cm.get("match") or cm.get("matched_name")
    if status in ("MATCH", "PROBABLE"):
        return True
    if matched and "no counterparty" not in why and status != "UNRESOLVED":
        return True
    return False


# Attempt re-resolution for unresolved rows if reference pools exist
pools = [
    tn
    for tn in tbl_names
    if tn != "coa" and "map" not in tn and "rule" not in tn
]
if hasattr(kit, "lookup") and pools:
    for r in rows:
        if not is_resolved(r):
            narr = str(r.get("narrative") or "").strip()
            variants = (
                kit.variants(narr) if hasattr(kit, "variants") else [narr]
            )
            for v in variants:
                try:
                    match = kit.lookup(v, pools)
                    if match:
                        print(f"Resolved narrative '{narr}' -> {match}")
                        r["counterparty_match"] = {
                            "status": "MATCH",
                            "matched_name": match,
                            "why": "Verbatim match in reference pool",
                        }
                        break
                except Exception:
                    pass


def get_cp_tt(row):
    if not is_resolved(row):
        return holding_tt, True

    cls_val = str(row.get("classification") or "").strip()
    curr_val = str(row.get("currency") or "").strip().lower()

    # 1. Exact match with coa_types
    for tt in coa_types:
        if tt.lower() == cls_val.lower():
            return tt, False

    # 2. Check mapping tables
    for tn in ["account_map", "allocation_rules", "category_map", "rules"]:
        if tn in ref_tables:
            for item in ref_tables[tn]:
                if isinstance(item, dict):
                    vals = [str(v).lower() for v in item.values()]
                    if cls_val.lower() in vals:
                        for k, v in item.items():
                            if str(v) in coa_types:
                                return str(v), False

    # 3. Substring match on classification
    if cls_val:
        for tt in coa_types:
            if cls_val.lower() in tt.lower():
                return tt, False

    if coa_records and isinstance(coa_records[0], dict):
        for r in coa_records:
            r_str = " ".join(str(v).lower() for v in r.values())
            tt_val = str(r.get(tt_col_name, "")).strip()
            if cls_val.lower() and cls_val.lower() in r_str:
                if tt_val in coa_types:
                    return tt_val, False

    # 4. Fallback for resolved rows
    for kw in [
        "accounts payable",
        "trade creditors",
        "operating expense",
        "expense",
    ]:
        for tt in coa_types:
            if kw in tt.lower():
                return tt, False

    return holding_tt, True


# 7. Build journal lines
parked_count = 0
for i, r in enumerate(rows):
    batch_id = str(r.get("id") or f"batch_{i+1}")

    raw_amt = r.get("amount", 0)
    try:
        amt_str = f"{abs(float(str(raw_amt).replace(',', ''))):.2f}"
    except Exception:
        amt_str = str(raw_amt)

    stmt_debit = r.get("is_debit")
    if stmt_debit is None:
        direction = str(r.get("direction", "")).lower()
        stmt_debit = direction in ("debit", "dr", "out")

    cash_acc = get_cash_tt(r)
    cp_acc, is_parked = get_cp_tt(r)
    if is_parked:
        parked_count += 1

    # Cash leg is credit when statement is debit, debit when statement is credit
    cash_debit = not bool(stmt_debit)
    cp_debit = bool(stmt_debit)

    r["journal_lines"] = [
        {
            "batch": batch_id,
            "amount": amt_str,
            "is_debit": cash_debit,
            "transaction_type": cash_acc,
        },
        {
            "batch": batch_id,
            "amount": amt_str,
            "is_debit": cp_debit,
            "transaction_type": cp_acc,
        },
    ]

    print(
        f"Row {i:02d} [{batch_id}]: {amt_str} {r.get('currency')} | "
        f"Cash: {cash_acc} (Dr={cash_debit}) | "
        f"Counterpart: {cp_acc} (Dr={cp_debit}, parked={is_parked})"
    )

# 8. Check double entry balance
try:
    bal_check = kit.batches_balance(rows)
    print("kit.batches_balance result:", bal_check)
except Exception as e:
    print("batches_balance check exception:", e)

# 9. Assertions
try:
    if hasattr(kit, "write_assertions"):
        claims = []
        if bal_check is not None:
            if isinstance(bal_check, list):
                claims.extend(bal_check)
            else:
                claims.append(bal_check)
        kit.write_assertions(claims)
except Exception as e:
    print("write_assertions note:", e)

# 10. Write enriched result
kit.write_result(rows)
print(
    f"posted {len(rows)} rows ({len(rows)*2} journal lines), parked"
    f" {parked_count} lines to holding"
)
print(f"parsed {len(rows)} rows")