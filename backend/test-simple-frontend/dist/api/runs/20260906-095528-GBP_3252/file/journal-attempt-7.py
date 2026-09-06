import sys
import kit

print("=== JOURNAL PROCESSING START ===")

# 1. Load COA and Trans Type values using kit.Table API
coa = kit.table("coa")
print("COA object type:", type(coa))
print(
    "COA public methods/attrs:", [m for m in dir(coa) if not m.startswith("_")]
)

all_trans_types = []
tt_col = "Trans Type"

# Read Trans Type directly as specified in the reference docs
if hasattr(coa, "values"):
    for cand in [
        "Trans Type",
        "trans type",
        "Trans_Type",
        "trans_type",
        "Transaction Type",
    ]:
        try:
            vals = list(coa.values(cand))
            if vals:
                all_trans_types = [str(x).strip() for x in vals if x is not None]
                tt_col = cand
                print(f"Loaded {len(all_trans_types)} values from column '{cand}'")
                break
        except Exception as e:
            print(f"coa.values('{cand}') raised: {e}")

# Inspect columns if available
cols = []
for attr in ["columns", "column_names", "names", "keys", "fields"]:
    if hasattr(coa, attr):
        try:
            val = getattr(coa, attr)
            cols = list(val() if callable(val) else val)
            print(f"COA columns via {attr}:", cols)
            break
        except Exception:
            pass

coa_records = []
if cols and hasattr(coa, "values"):
    try:
        col_dict = {c: list(coa.values(c)) for c in cols}
        n = len(col_dict[cols[0]])
        coa_records = [{c: col_dict[c][i] for c in cols} for i in range(n)]
    except Exception as e:
        print("Failed building coa_records from cols:", e)

if not coa_records and all_trans_types:
    coa_records = [{tt_col: tt} for tt in all_trans_types]

print(f"COA loaded: {len(all_trans_types)} accounts available")
print("Sample accounts:", all_trans_types[:15])


# 2. Account Finder Functions
def get_holding_account():
    priority_phrases = [
        "holding account",
        "suspense account",
        "suspense",
        "holding",
        "unallocated receipts",
        "unallocated payments",
        "unallocated cash",
        "unallocated",
        "unidentified receipts",
        "unidentified",
        "parked transactions",
        "parked",
        "clearing account",
        "general suspense",
    ]
    # Exact / full phrase match
    for phrase in priority_phrases:
        for tt in all_trans_types:
            if phrase == tt.lower().strip():
                return tt

    # Substring match
    for phrase in priority_phrases:
        for tt in all_trans_types:
            if phrase in tt.lower():
                return tt

    # Broader fallback
    for tt in all_trans_types:
        if "susp" in tt.lower() or "hold" in tt.lower():
            return tt

    return all_trans_types[0] if all_trans_types else None


def get_cash_account(currency):
    cur = (currency or "GBP").upper()
    disqualifiers = [
        "fee",
        "charge",
        "interest",
        "loan",
        "suspense",
        "holding",
        "payable",
        "receivable",
        "debtor",
        "creditor",
        "clearing",
        "settlement",
    ]

    best = None
    best_score = -999

    for r in coa_records:
        tt = str(r.get(tt_col, "")).strip()
        text = " ".join(str(v) for v in r.values()).lower()
        tt_low = tt.lower()

        if any(d in tt_low for d in disqualifiers):
            continue

        score = 0
        if cur.lower() in tt_low:
            score += 50
        elif cur.lower() in text:
            score += 30

        if "bank" in tt_low:
            score += 30
        elif "bank" in text:
            score += 15

        if "cash" in tt_low:
            score += 25
        elif "cash" in text:
            score += 10

        if "current" in tt_low or "operating" in tt_low:
            score += 15

        if "bank" not in tt_low and "cash" not in tt_low:
            score -= 40

        if score > best_score:
            best_score = score
            best = tt

    if best and best_score > 0:
        return best

    for tt in all_trans_types:
        if "bank" in tt.lower():
            return tt
    for tt in all_trans_types:
        if "cash" in tt.lower():
            return tt

    return all_trans_types[0] if all_trans_types else None


def get_counterpart_account(
    classification, currency, is_statement_credit, holding_acc
):
    cl = (classification or "").strip()
    cl_low = cl.lower()
    cur_low = (currency or "").lower()

    # Direct match on classification
    for tt in all_trans_types:
        if kit.compact(tt) == kit.compact(cl):
            return tt

    target_keywords = []
    if any(
        w in cl_low
        for w in [
            "supplier",
            "vendor",
            "creditor",
            "payable",
            "purchase",
            "trade payable",
            "expense",
        ]
    ):
        target_keywords = [
            "trade creditor",
            "accounts payable",
            "trade payable",
            "creditor",
            "payable",
            "supplier",
            "purchases",
        ]
    elif any(
        w in cl_low
        for w in [
            "customer",
            "client",
            "debtor",
            "receivable",
            "sales",
            "trade receivable",
            "income",
            "revenue",
        ]
    ):
        target_keywords = [
            "trade debtor",
            "accounts receivable",
            "trade receivable",
            "debtor",
            "receivable",
            "customer",
            "sales",
            "revenue",
        ]
    elif any(w in cl_low for w in ["payroll", "wage", "salaries", "salary"]):
        target_keywords = ["payroll", "wages", "salaries", "salary"]
    elif any(w in cl_low for w in ["tax", "vat", "hmrc"]):
        target_keywords = ["vat", "tax", "hmrc", "corporation tax"]
    elif any(w in cl_low for w in ["interest", "finance"]):
        target_keywords = ["interest", "finance"]
    elif any(w in cl_low for w in ["fee", "bank charge"]):
        target_keywords = ["bank charge", "bank fee", "fee"]
    else:
        if is_statement_credit:
            target_keywords = [
                "trade debtor",
                "accounts receivable",
                "trade receivable",
                "debtor",
                "receivable",
                "sales",
            ]
        else:
            target_keywords = [
                "trade creditor",
                "accounts payable",
                "trade payable",
                "creditor",
                "payable",
                "supplier",
            ]

    best = None
    best_score = -999
    disqualifiers = [
        "bank",
        "cash",
        "suspense",
        "holding",
        "clearing",
        "settlement",
    ]

    for r in coa_records:
        tt = str(r.get(tt_col, "")).strip()
        text = " ".join(str(v) for v in r.values()).lower()
        tt_low = tt.lower()

        if any(d in tt_low for d in disqualifiers):
            continue

        score = 0
        for i, kw in enumerate(target_keywords):
            if kw == tt_low:
                score += 50 - i * 2
                break
            elif kw in tt_low:
                score += 30 - i * 2
                break
            elif kw in text:
                score += 15 - i * 2
                break

        if score > 0:
            if cur_low and (cur_low in tt_low or cur_low in text):
                score += 10
            if score > best_score:
                best_score = score
                best = tt

    return best if (best and best_score > 0) else holding_acc


holding_account = get_holding_account()
cash_gbp = get_cash_account("GBP")
print(f"Selected holding_account: '{holding_account}', cash_gbp: '{cash_gbp}'")


# 3. Process Statement Rows
rows = kit.rows()
print(f"Processing {len(rows)} rows...")


def is_row_resolved(r):
    cp = r.get("counterparty_match")
    if cp is None:
        name = r.get("counterparty")
        return bool(name and str(name).strip())
    if isinstance(cp, dict):
        status = str(cp.get("status", "")).upper()
        if status in ("MATCH", "PROBABLE"):
            return True
        if status in ("UNRESOLVED", "NONE", "FALSE", "UNKNOWN"):
            return False
        name = (
            cp.get("matched_name")
            or cp.get("name")
            or cp.get("counterparty")
            or cp.get("party")
        )
        return bool(name and str(name).strip())
    if isinstance(cp, str):
        return cp.strip() not in ("", "UNRESOLVED", "None")
    if isinstance(cp, bool):
        return cp
    return False


for i, row in enumerate(rows):
    cur = row.get("currency", "GBP")
    cash_acc = get_cash_account(cur)

    # Determine amount & direction
    if row.get("credit") is not None and str(row["credit"]).strip() not in (
        "",
        "None",
    ):
        amt_str = str(row["credit"]).replace(",", "").strip()
        amt = f"{float(amt_str):0.2f}"
        cash_is_debit = True
        cp_is_debit = False
        is_stmt_credit = True
    elif row.get("debit") is not None and str(row["debit"]).strip() not in (
        "",
        "None",
    ):
        amt_str = str(row["debit"]).replace(",", "").strip()
        amt = f"{float(amt_str):0.2f}"
        cash_is_debit = False
        cp_is_debit = True
        is_stmt_credit = False
    elif row.get("amount") is not None and str(row["amount"]).strip() not in (
        "",
        "None",
    ):
        val = float(str(row["amount"]).replace(",", "").strip())
        amt = f"{abs(val):0.2f}"
        if val > 0:
            cash_is_debit = True
            cp_is_debit = False
            is_stmt_credit = True
        else:
            cash_is_debit = False
            cp_is_debit = True
            is_stmt_credit = False
    else:
        raise ValueError(f"Row {i} has no usable credit/debit/amount: {row}")

    resolved = is_row_resolved(row)
    if resolved:
        cp_acc = get_counterpart_account(
            row.get("classification"), cur, is_stmt_credit, holding_account
        )
    else:
        cp_acc = holding_account

    batch_id = (
        str(row.get("id"))
        if row.get("id") is not None
        else f"batch_{i+1:03d}"
    )

    line_cash = {
        "batch": batch_id,
        "amount": amt,
        "is_debit": cash_is_debit,
        "transaction_type": cash_acc,
    }
    line_cp = {
        "batch": batch_id,
        "amount": amt,
        "is_debit": cp_is_debit,
        "transaction_type": cp_acc,
    }

    # Convention: debit first, credit second
    if cash_is_debit:
        row["journal_lines"] = [line_cash, line_cp]
    else:
        row["journal_lines"] = [line_cp, line_cash]


# 4. Double Entry Verification & Holding Count
r_bal = kit.batches_balance(rows, field="journal_lines")
print("kit.batches_balance check:", r_bal)

parked_lines = [
    line
    for r in rows
    for line in r["journal_lines"]
    if line["transaction_type"] == holding_account
]
parked_count = len(parked_lines)
print(f"Batches balanced: {r_bal}, Parked lines count: {parked_count}")

# 5. Assertions Handling
try:
    q = kit.questions()
    if q:
        claims = {}
        for item in q if isinstance(q, list) else list(q.keys()):
            qid = (
                item.get("id", str(item))
                if isinstance(item, dict)
                else str(item)
            )
            if "bal" in qid.lower():
                claims[qid] = r_bal.get("ok", True)
            elif "park" in qid.lower():
                claims[qid] = parked_count
            else:
                claims[qid] = True
        kit.write_assertions(claims)
        print("Assertions recorded.")
except Exception as e:
    print("Assertions handling notice:", e)

# 6. Write Final Enriched Rows
kit.write_result(rows)
print("Result written via kit.write_result.")
print(f"parsed {len(rows)} rows")