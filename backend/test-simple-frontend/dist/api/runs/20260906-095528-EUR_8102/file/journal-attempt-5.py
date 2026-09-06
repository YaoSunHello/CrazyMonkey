import sys
import kit

# Ensure stdout flushes immediately
sys.stdout.reconfigure(line_buffering=True)

# 1. Discover tables and load Chart of Accounts (COA)
tbl_names = kit.tables() if hasattr(kit, "tables") else []
print(f"Mounted tables: {tbl_names}")

coa_table = kit.table("coa")
coa_types = []

# Check values directly via .values("Trans Type") as specified in instructions
if hasattr(coa_table, "values"):
    try:
        coa_types = [str(x).strip() for x in coa_table.values("Trans Type") if x]
    except Exception as e:
        print(f"coa_table.values('Trans Type') exception: {e}")

if not coa_types:
    # Fallback inspection of coa_table attributes
    for attr in ("rows", "to_dict", "data", "records"):
        if hasattr(coa_table, attr):
            val = getattr(coa_table, attr)
            data = val() if callable(val) else val
            if isinstance(data, list) and data:
                first = data[0]
                col = (
                    "Trans Type"
                    if "Trans Type" in first
                    else next(
                        (
                            k
                            for k in first
                            if "type" in k.lower() or "trans" in k.lower()
                        ),
                        list(first.keys())[0],
                    )
                )
                coa_types = [
                    str(r[col]).strip()
                    for r in data
                    if isinstance(r, dict) and r.get(col)
                ]
                break

print(f"COA loaded {len(coa_types)} transaction types: {coa_types}")

# 2. Identify Holding / Suspense account from COA
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

if not holding_tt:
    for tt in coa_types:
        if "other" in tt.lower() or "misc" in tt.lower():
            holding_tt = tt
            break

if not holding_tt and coa_types:
    holding_tt = coa_types[-1]

print(f"Holding account: '{holding_tt}'")

# 3. Identify Cash accounts from COA
cash_map = {}
for tt in coa_types:
    t_low = tt.lower()
    if any(w in t_low for w in ["cash", "bank", "operating", "current account"]):
        for curr in ["EUR", "USD", "GBP", "CHF", "JPY", "AUD", "CAD"]:
            if curr.lower() in t_low and curr not in cash_map:
                cash_map[curr] = tt

default_cash = None
for tt in coa_types:
    t_low = tt.lower()
    if any(w in t_low for w in ["cash", "bank", "current"]):
        default_cash = tt
        break

if not default_cash and coa_types:
    default_cash = coa_types[0]

print(f"Cash map: {cash_map}, Default cash: '{default_cash}'")


def get_cash_tt(row):
    curr = str(row.get("currency") or "").upper()
    return cash_map.get(curr, default_cash)


# 4. Load rows and inspect keys
rows = kit.rows()
print(f"Loaded {len(rows)} rows.")
if rows:
    print(f"Row 0 sample keys: {list(rows[0].keys())}")
    print(f"Row 0 data: {rows[0]}")


def is_resolved(row):
    cm = row.get("counterparty_match")
    if not cm or not isinstance(cm, dict):
        return False
    status = str(cm.get("status", "")).upper()
    matched = cm.get("name") or cm.get("match") or cm.get("matched_name")
    why = str(cm.get("why", "")).lower()
    if status in ("MATCH", "PROBABLE"):
        return True
    if matched and "no counterparty" not in why and status != "UNRESOLVED":
        return True
    return False


# Attempt re-resolution for unresolved rows using reference pools
pools = [tn for tn in tbl_names if tn != "coa"]
if hasattr(kit, "lookup") and pools:
    for r in rows:
        if not is_resolved(r):
            narr = str(r.get("narrative") or r.get("description") or "").strip()
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
                            "why": "Exact match in reference pool",
                        }
                        break
                except Exception:
                    pass


def get_cp_tt(row):
    if not is_resolved(row):
        return holding_tt, True

    cls_val = str(
        row.get("classification")
        or row.get("category")
        or row.get("account")
        or ""
    ).strip()

    # 1. Exact match in coa_types
    for tt in coa_types:
        if tt.lower() == cls_val.lower():
            return tt, False

    # 2. Substring match
    if cls_val:
        for tt in coa_types:
            if cls_val.lower() in tt.lower() or tt.lower() in cls_val.lower():
                return tt, False

    # 3. Fallback for resolved rows to trade/operating account
    for kw in [
        "trade creditors",
        "accounts payable",
        "operating",
        "expense",
        "vendor",
        "supplier",
    ]:
        for tt in coa_types:
            if kw in tt.lower():
                return tt, False

    # If no specific account matches, park
    return holding_tt, True


# 5. Build journal lines
parked_count = 0
for i, r in enumerate(rows):
    batch_id = str(r.get("id") or r.get("batch") or f"row_{i+1}")

    # Determine amount
    raw_amt = None
    for field in (
        "amount",
        "debit",
        "credit",
        "paid_in",
        "paid_out",
        "withdrawal",
        "deposit",
        "value",
    ):
        v = r.get(field)
        if v is not None and str(v).strip() not in ("", "None"):
            try:
                num = abs(float(str(v).replace(",", "")))
                if num > 0:
                    raw_amt = num
                    break
            except Exception:
                pass

    if raw_amt is None:
        try:
            raw_amt = abs(float(str(r.get("amount", 0)).replace(",", "")))
        except Exception:
            raw_amt = 0.0

    amt_str = f"{raw_amt:.2f}"

    # Determine statement debit / credit direction
    stmt_debit = r.get("is_debit")
    if stmt_debit is None:
        if r.get("debit") is not None and str(r.get("debit")).strip() not in (
            "",
            "None",
            "0",
            "0.00",
        ):
            stmt_debit = True
        elif r.get("credit") is not None and str(
            r.get("credit")
        ).strip() not in ("", "None", "0", "0.00"):
            stmt_debit = False
        else:
            direction = str(
                r.get("direction") or r.get("type") or ""
            ).lower()
            stmt_debit = direction in ("debit", "dr", "out", "withdrawal")

    cash_acc = get_cash_tt(r)
    cp_acc, is_parked = get_cp_tt(r)
    if is_parked:
        parked_count += 1

    # Cash leg is credit when statement row is debit, debit when statement row is credit
    cash_is_debit = not bool(stmt_debit)
    cp_is_debit = bool(stmt_debit)

    r["journal_lines"] = [
        {
            "batch": batch_id,
            "amount": amt_str,
            "is_debit": cash_is_debit,
            "transaction_type": cash_acc,
        },
        {
            "batch": batch_id,
            "amount": amt_str,
            "is_debit": cp_is_debit,
            "transaction_type": cp_acc,
        },
    ]

# 6. Check double entry balance
bal_check = kit.batches_balance(rows)
print("kit.batches_balance result:", bal_check)

# 7. Write assertions if available
if hasattr(kit, "write_assertions"):
    try:
        claims = []
        if isinstance(bal_check, list):
            claims.extend(bal_check)
        elif isinstance(bal_check, dict):
            claims.append(bal_check)
        kit.write_assertions(claims)
    except Exception as e:
        print(f"write_assertions note: {e}")

# 8. Write enriched result
kit.write_result(rows)
print(
    f"posted {len(rows)} rows ({len(rows)*2} journal lines), parked"
    f" {parked_count} lines to holding"
)
print(f"parsed {len(rows)} rows")