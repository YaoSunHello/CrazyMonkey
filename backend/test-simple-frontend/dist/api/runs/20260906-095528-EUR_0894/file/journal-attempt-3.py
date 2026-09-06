import sys
import kit

sys.stdout.reconfigure(line_buffering=True)

print("=== START JOURNAL PROCESSING ===", flush=True)

# 1. Inspect Reference Tables and COA
print(f"Tables: {kit.tables()}", flush=True)
coa = kit.table("coa")

# Inspect columns of COA
cols = []
if hasattr(coa, "columns"):
    c = coa.columns
    cols = list(c() if callable(c) else c)
elif hasattr(coa, "headers"):
    c = coa.headers
    cols = list(c() if callable(c) else c)

print(f"COA cols: {cols}", flush=True)

# Read Trans Type values from coa
coa_trans_types = []
if hasattr(coa, "values"):
    try:
        coa_trans_types = [t for t in coa.values("Trans Type") if t]
    except Exception as e:
        print(f"Error reading coa.values('Trans Type'): {e}", flush=True)

# Build records from columns & values if available
coa_records = []
if cols and hasattr(coa, "values"):
    try:
        col_map = {col: list(coa.values(col)) for col in cols}
        n_rows = len(col_map[cols[0]])
        for idx in range(n_rows):
            coa_records.append({col: col_map[col][idx] for col in cols})
    except Exception as e:
        print(f"Error building coa_records from col_map: {e}", flush=True)

if not coa_records:
    try:
        for item in coa:
            if isinstance(item, dict):
                coa_records.append(item)
            elif hasattr(item, "to_dict"):
                coa_records.append(item.to_dict())
            elif hasattr(item, "_asdict"):
                coa_records.append(item._asdict())
            elif hasattr(item, "keys"):
                coa_records.append({k: item[k] for k in item.keys()})
    except Exception as e:
        print(f"Error iterating coa: {e}", flush=True)

if not coa_trans_types and coa_records:
    coa_trans_types = [
        r.get("Trans Type") for r in coa_records if r.get("Trans Type")
    ]

# Deduplicate while preserving order
seen = set()
unique_tt = []
for tt in coa_trans_types:
    if tt not in seen:
        seen.add(tt)
        unique_tt.append(tt)
coa_trans_types = unique_tt

print(f"Found {len(coa_trans_types)} unique Trans Types:", flush=True)
for tt in coa_trans_types:
    print(f"  {tt}", flush=True)
if coa_records:
    print(f"Sample COA record: {coa_records[0]}", flush=True)

# 2. Account Resolution Helpers
holding_keywords = [
    "holding",
    "suspense",
    "unallocated",
    "unresolved",
    "parked",
    "clearing",
    "unknown",
    "transit",
]


def find_holding_account():
    for kw in holding_keywords:
        for r in coa_records:
            r_text = " ".join(str(v).lower() for v in r.values())
            if kw in r_text:
                tt = r.get("Trans Type")
                if tt:
                    return tt
    for kw in holding_keywords:
        for tt in coa_trans_types:
            if kw in tt.lower():
                return tt
    for tt in coa_trans_types:
        if "other" in tt.lower():
            return tt
    return coa_trans_types[-1] if coa_trans_types else "Suspense"


holding_account = find_holding_account()
print(f"Selected holding account: {holding_account}", flush=True)


def find_cash_account(curr):
    curr_str = (curr or "").lower()
    cash_keywords = ["cash", "bank", "settlement", "current account"]

    # 1. In records matching cash keyword and currency
    for r in coa_records:
        r_text = " ".join(str(v).lower() for v in r.values())
        if (
            any(ck in r_text for ck in cash_keywords)
            and curr_str
            and curr_str in r_text
        ):
            tt = r.get("Trans Type")
            if tt:
                return tt

    # 2. In trans types matching cash keyword and currency
    for tt in coa_trans_types:
        tt_lower = tt.lower()
        if (
            any(ck in tt_lower for ck in cash_keywords)
            and curr_str
            and curr_str in tt_lower
        ):
            return tt

    # 3. In records matching cash keyword
    for r in coa_records:
        r_text = " ".join(str(v).lower() for v in r.values())
        if any(ck in r_text for ck in cash_keywords):
            tt = r.get("Trans Type")
            if tt:
                return tt

    # 4. In trans types matching cash keyword
    for tt in coa_trans_types:
        if any(ck in tt.lower() for ck in cash_keywords):
            return tt

    return coa_trans_types[0] if coa_trans_types else "Cash"


def find_counterpart_account(classification, curr, is_resolved):
    if not is_resolved:
        return holding_account

    cls_str = (classification or "").lower()
    curr_str = (curr or "").lower()
    cash_keywords = ["cash", "bank", "settlement", "current account"]

    # 1. In records matching classification and currency (not cash)
    best_record_tt = None
    for r in coa_records:
        r_text = " ".join(str(v).lower() for v in r.values())
        if any(ck in r_text for ck in cash_keywords):
            continue
        if cls_str and cls_str in r_text:
            tt = r.get("Trans Type")
            if tt and curr_str and curr_str in r_text:
                return tt
            if tt and not best_record_tt:
                best_record_tt = tt

    if best_record_tt:
        return best_record_tt

    # 2. In trans types matching classification and currency (not cash)
    best_tt = None
    for tt in coa_trans_types:
        tt_lower = tt.lower()
        if any(ck in tt_lower for ck in cash_keywords):
            continue
        if cls_str and cls_str in tt_lower:
            if curr_str and curr_str in tt_lower:
                return tt
            if not best_tt:
                best_tt = tt

    if best_tt:
        return best_tt

    # 3. Match individual words of classification
    cls_words = [w for w in cls_str.split() if len(w) > 3]
    for w in cls_words:
        for tt in coa_trans_types:
            tt_lower = tt.lower()
            if any(ck in tt_lower for ck in cash_keywords):
                continue
            if w in tt_lower:
                return tt

    return holding_account


# 3. Parse Amount and Direction
def parse_amount_and_direction(r):
    def clean_val(v):
        if v is None or v == "":
            return None
        try:
            return float(str(v).replace(",", "").strip())
        except ValueError:
            return None

    d_num = clean_val(r.get("debit"))
    c_num = clean_val(r.get("credit"))

    if d_num is not None and abs(d_num) > 0:
        return f"{abs(d_num):.2f}", True

    if c_num is not None and abs(c_num) > 0:
        return f"{abs(c_num):.2f}", False

    amt_num = clean_val(r.get("amount"))
    if amt_num is not None:
        if r.get("is_debit") is not None:
            return f"{abs(amt_num):.2f}", bool(r["is_debit"])
        if amt_num < 0:
            return f"{abs(amt_num):.2f}", True
        else:
            return f"{abs(amt_num):.2f}", False

    return "0.00", False


# 4. Process Rows
rows = kit.rows()
print(f"Processing {len(rows)} rows...", flush=True)

parked_count = 0
for i, r in enumerate(rows):
    batch_id = r.get("id") or f"batch_{i + 1}"
    amount_str, is_stmt_debit = parse_amount_and_direction(r)
    curr = r.get("currency")
    classification = r.get("classification")

    # Counterparty match status
    c_match = r.get("counterparty_match", {})
    status = (
        c_match.get("status")
        if isinstance(c_match, dict)
        else getattr(c_match, "status", None)
    )
    matched_name = (
        c_match.get("matched_name")
        if isinstance(c_match, dict)
        else getattr(c_match, "matched_name", None)
    )
    is_resolved = status in ("MATCH", "PROBABLE") and bool(matched_name)

    cash_tt = find_cash_account(curr)
    cp_tt = find_counterpart_account(classification, curr, is_resolved)

    # Ensure transaction types exist in COA
    if cash_tt not in coa_trans_types:
        cash_tt = coa_trans_types[0]
    if cp_tt not in coa_trans_types:
        cp_tt = holding_account if holding_account in coa_trans_types else coa_trans_types[0]

    if cp_tt == holding_account:
        parked_count += 1

    # Direction rule:
    # Cash leg is CREDIT when statement row is DEBIT, and DEBIT when statement row is CREDIT.
    cash_is_debit = not is_stmt_debit
    cp_is_debit = is_stmt_debit

    r["journal_lines"] = [
        {
            "batch": str(batch_id),
            "amount": amount_str,
            "is_debit": cash_is_debit,
            "transaction_type": cash_tt,
        },
        {
            "batch": str(batch_id),
            "amount": amount_str,
            "is_debit": cp_is_debit,
            "transaction_type": cp_tt,
        },
    ]

    print(
        f"Row {i:02d}: amt={amount_str}, stmt_deb={is_stmt_debit}, curr={curr}, "
        f"class={classification}, resolved={is_resolved} -> cash={cash_tt}, cp={cp_tt}",
        flush=True,
    )

print(f"Total lines parked to holding account: {parked_count}", flush=True)

# 5. Check Double Entry Balance
bal_res = kit.batches_balance(rows)
print(f"batches_balance result: {bal_res}", flush=True)

# 6. Write Result exactly once
kit.write_result(rows)
print(f"parsed {len(rows)} rows", flush=True)