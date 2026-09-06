import inspect
import sys
import kit

# Ensure stdout flushes immediately
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

print("=== INSPECTING ENVIRONMENT ===", flush=True)

# 1. Inspect questions
try:
    q = kit.questions()
    print("QUESTIONS:", q, flush=True)
except Exception as e:
    print("questions error:", e, flush=True)

# 2. Inspect tables
tables = kit.tables()
print("TABLES:", tables, flush=True)

# 3. Inspect batches_balance and write_assertions
try:
    print("batches_balance source:\n", inspect.getsource(kit.batches_balance), flush=True)
except Exception as e:
    print("batches_balance inspect error:", e, flush=True)

try:
    print("write_assertions source:\n", inspect.getsource(kit.write_assertions), flush=True)
except Exception as e:
    print("write_assertions inspect error:", e, flush=True)

# 4. Inspect other tables (reference lists)
for t in tables:
    if t != "coa":
        tbl = kit.table(t)
        print(f"\n--- Table '{t}' (len={len(tbl) if hasattr(tbl, '__len__') else '?'}) ---", flush=True)
        for idx, item in enumerate(tbl):
            if idx < 10:
                print(f"  [{idx}]: {item}", flush=True)
            elif idx == 10:
                print(f"  ... ({len(tbl) - 10} more)", flush=True)

# 5. Inspect COA table
coa_raw = kit.table("coa")
coa = list(coa_raw)
print(f"\nCOA total rows: {len(coa)}", flush=True)
if coa:
    print("COA sample 0:", coa[0], flush=True)
    if len(coa) > 1:
        print("COA sample 1:", coa[1], flush=True)

# Inspect all Trans Types and unique values of any relevant columns
trans_types = set()
currencies = set()
classifications = set()
for entry in coa:
    if isinstance(entry, dict):
        if "Trans Type" in entry:
            trans_types.add(entry["Trans Type"])
        if "Currency" in entry:
            currencies.add(entry["Currency"])
        if "Classification" in entry:
            classifications.add(entry["Classification"])
    elif isinstance(entry, str):
        trans_types.add(entry)

print(f"COA unique Trans Types ({len(trans_types)}):", sorted(trans_types), flush=True)
if currencies:
    print("COA Currencies:", sorted(currencies), flush=True)
if classifications:
    print("COA Classifications:", sorted(classifications), flush=True)

# Look for holding / suspense accounts
holding_candidates = [
    tt for tt in trans_types
    if any(w in tt.lower() for w in ["hold", "suspense", "unresolved", "park", "clearing"])
]
print("Holding account candidates in COA:", holding_candidates, flush=True)

# Look for cash / bank accounts
cash_candidates = [
    tt for tt in trans_types
    if any(w in tt.lower() for w in ["cash", "bank", "operating"])
]
print("Cash account candidates in COA:", cash_candidates, flush=True)

# 6. Inspect rows
rows = kit.rows()
print(f"\n=== ROWS ({len(rows)}) ===", flush=True)
for i, r in enumerate(rows):
    print(
        f"Row {i}: id={r.get('id')} date={r.get('date')} amt={r.get('amount')} "
        f"is_debit={r.get('is_debit')} cur={r.get('currency')} cls={r.get('classification')} "
        f"cp={r.get('counterparty_match')} narr={repr(r.get('narrative', ''))}",
        flush=True
    )

# 7. Helper to find accounts in COA
def find_coa_entry(classification=None, currency=None, is_cash=False):
    for entry in coa:
        if not isinstance(entry, dict):
            continue
        e_cur = entry.get("Currency")
        e_cls = entry.get("Classification")
        e_type = entry.get("Type") or entry.get("Account Type")
        tt = entry.get("Trans Type", "")
        
        if is_cash:
            if currency and e_cur and e_cur.upper() != currency.upper():
                continue
            if any(w in tt.lower() for w in ["cash", "bank"]):
                return tt
        else:
            if currency and e_cur and e_cur.upper() != currency.upper():
                continue
            if classification and e_cls and e_cls.lower() == classification.lower():
                return tt
            if classification and classification.lower() in tt.lower():
                return tt
    return None

# Find the default holding account
holding_account = holding_candidates[0] if holding_candidates else None
if not holding_account:
    for entry in coa:
        tt = entry.get("Trans Type", "") if isinstance(entry, dict) else str(entry)
        if "holding" in tt.lower() or "suspense" in tt.lower():
            holding_account = tt
            break

print(f"Selected holding account: {holding_account}", flush=True)

# 8. Build tentative journal lines
parked_count = 0
for i, r in enumerate(rows):
    batch_id = r.get("id") or f"batch_{i}"
    
    # Amount formatting
    raw_amt = r.get("amount")
    amt_str = f"{abs(float(raw_amt)):.2f}"
    
    # Statement row debit / credit
    # "The cash leg is the credit when the statement row is a debit, and the debit when it is a credit."
    stmt_is_debit = r.get("is_debit", True)
    cash_is_debit = not stmt_is_debit
    cp_is_debit = stmt_is_debit
    
    cur = r.get("currency")
    cls = r.get("classification")
    cp_match = r.get("counterparty_match")
    
    # Cash transaction type
    cash_tt = find_coa_entry(currency=cur, is_cash=True)
    if not cash_tt:
        # Fallback to currency-matching cash candidate or first cash candidate
        cur_cash = [tt for tt in cash_candidates if cur and cur.lower() in tt.lower()]
        cash_tt = cur_cash[0] if cur_cash else (cash_candidates[0] if cash_candidates else "Cash")
    
    # Counterparty transaction type
    # Check if counterparty resolved
    is_resolved = False
    if isinstance(cp_match, dict):
        is_resolved = bool(cp_match.get("match") or cp_match.get("name"))
    elif cp_match:
        is_resolved = True
        
    if not is_resolved:
        cp_tt = holding_account
        parked_count += 1
    else:
        cp_tt = find_coa_entry(classification=cls, currency=cur, is_cash=False)
        if not cp_tt:
            # Fallback
            cls_matches = [tt for tt in trans_types if cls and cls.lower() in tt.lower()]
            cp_tt = cls_matches[0] if cls_matches else holding_account
            if cp_tt == holding_account:
                parked_count += 1
                
    r["journal_lines"] = [
        {
            "batch": batch_id,
            "amount": amt_str,
            "is_debit": cash_is_debit,
            "transaction_type": cash_tt
        },
        {
            "batch": batch_id,
            "amount": amt_str,
            "is_debit": cp_is_debit,
            "transaction_type": cp_tt
        }
    ]

# 9. Verify batches balance
bal = kit.batches_balance(rows)
print("batches_balance check:", bal, flush=True)
print(f"Parked counterparty lines count: {parked_count}", flush=True)

# 10. Write assertions if available
try:
    kit.write_assertions({
        "batches_balance": bal,
        "parked_lines": parked_count
    })
except Exception as e:
    try:
        kit.write_assertions([bal, parked_count])
    except Exception as e2:
        print("write_assertions note:", e2, flush=True)

# 11. Write result
kit.write_result(rows)

print(f"parsed {len(rows)} rows", flush=True)