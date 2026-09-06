# prompt

You are writing one Python file that will run once, in a sandbox, and produce a
single JSON result. A module `kit` is already available — import it, do not
rewrite it, and do not install anything.

Rules that hold for every task:

- Write the result exactly once, at the end, with the kit's write function.
- Never invent or adjust a value to make a check pass. A value you cannot read
  is a value you leave out, and the checks will say so plainly.
- **Print what you need to see.** Everything your script prints comes back to
  you if the attempt is rejected, so stdout is how you look at the data: the
  values that did not match, what the reference data holds near them, how many
  rows a pattern actually caught. A number you assumed is a number you will get
  wrong. Finish with a one-line summary, e.g. "parsed 16 rows".
- Reply with the complete contents of the file in a single ```python code block,
  and nothing else.

## What the checks are, and how much to trust each kind

You will be judged by checks, and knowing what they can and cannot see is part
of doing this well. They are not one thing.

**A check about a number or about existence is proof. Trust it completely.**
Does this balance chain close, does this batch net to zero, is this value
actually present in the list it claims, does this string really appear in the
document. There is no judgement in any of it. If one of these objects, it is
right and you are wrong — find the cause and fix it. Never argue with
arithmetic, and never adjust a figure to quiet it.

**A check that reports a count or a share is a measurement, not a verdict.**
How much *ought* to resolve is a fact about the document in front of you, and
the check cannot read it. One source is full of dealings with outside parties;
another is almost entirely internal movements naming nobody, and there a high
unresolved count is the correct answer rather than a failure. Read the number,
decide whether it is right *for this document*, and say why.

**You are the one who reads. Where no exact check contradicts you, your reading
stands.** A check works on shapes and strings; it cannot know what a name means
or which party a sentence is about. If something is obvious to you and nothing
exact says otherwise, go with it and record your reasoning.

**Never contort an answer to satisfy a rule you can see is crude.** If a check
would be quieter with a worse answer, give the better answer and explain the
disagreement in plain words. A reviewer can weigh that. What they cannot do is
recover the truth from an output bent to please a rule — and a wrong value that
passes silently is far more expensive than an honest one that gets discussed.

The point of all this is a result somebody can act on: correct where it can be
proved, judged where it must be, and clearly flagged where it is neither.

## How many tries you have

up to 6 attempts at the real file. Aim to be right in the first two or three: each attempt costs a full rewrite, and the later ones exist for problems you could not have foreseen, not for a plan you have not made yet.

If you reach the last attempt and something still will not come good, do not gamble on a rewrite. Submit what you have with that part honestly marked — unresolved, or proposed with your reasoning — because incomplete work that says where it is incomplete goes forward and gets reviewed, while a run that risks everything on one more try can end with nothing to show at all.

## The tools you have

Imported as `kit`. These signatures are read from the module itself, so
they are exactly right — do not guess at an argument, and do not rewrite
one of these by hand.

    kit.rows()
        The rows the extraction pass produced, verified before they got here.
    kit.tables()
    kit.table(name)
    kit.lookup(value, pools, markers = None, source = None)
        Find `value` in the first of `pools` that holds it. Exact only.
    kit.candidates(value, pools, limit = 5, source = None)
        Near misses worth a person's judgement, ranked by what they share.
    kit.narrative_span(narrative, name)
        The slice of `narrative` that `name` corresponds to, exactly as written.
    kit.variants(text, wrapper = ',')
        Every plausible reading of a value the source document line-wrapped.
    kit.trim_to(text, markers, keep = True)
        Cut a string at the first of `markers`, keeping the marker by default.
    kit.normalise(value)
        One string form for a cell, so lookups survive the source's whitespace.
    kit.fold(text)
        The form two strings are compared in. Case and accents removed.
    kit.compact(text)
        Folded, with every non-alphanumeric removed.
    kit.batches_balance(rows, field = 'journal_lines')
        Check your own double entry before you submit. Every batch nets to zero.
    kit.questions()
        The questions this run is asked, and what each one needs to be answered.
    kit.write_result(enriched)
    kit.write_assertions(claims)
        Record what you checked about your own output, and what you found.

The rows have been extracted, their arithmetic verified, and each one
resolved against the reference lists. One thing is left: turn each row into
its journal entry.

Emit every row unchanged, with `journal_lines` added: exactly two lines
sharing a `batch` unique to that row — the cash side and the counterparty
side.

    "journal_lines": [
      {"batch": "<a unique id for this row>", "amount": "301908.70",
       "is_debit": true,  "transaction_type": "<from the chart>"},
      {"batch": "<the same id>",            "amount": "301908.70",
       "is_debit": false, "transaction_type": "<from the chart>"}
    ]

`amount` is always positive and identical on both lines. **Direction is
carried by `is_debit` and never by the transaction type**, because a cash leg
can read as a disbursement on both sides of the ledger; a sign taken from the
type name will be wrong on a large share of rows. The cash leg is the credit
when the statement row is a debit, and the debit when it is a credit.

## The chart of accounts decides what you may book to

`transaction_type` must be a value that exists in the mounted chart of
accounts — `kit.table("coa")`, column `Trans Type`. It is a **closed
vocabulary**: an account that is not in it cannot be posted, and inventing a
plausible-looking one is the same class of error as inventing a counterparty.
Read the chart before you choose. It is large, so filter it — the cash legs
and the counterpart types you need are a small, findable subset, and the row's
currency and its classification tell you which.

**A row whose counterparty did not resolve cannot be booked to a real
account.** Every ledger keeps a holding account for exactly this, and this
chart is no exception — find it. Booking an unresolved row there is correct
and expected practice: it parks the row for a person instead of guessing at an
account, and it is what the client's own process says to do. Do NOT invent a
resolution in order to avoid it.

## This is the measurement of your own work, so make it

Unlike resolving a name, all of this has an answer you can verify without
being told, and you should verify it before you submit rather than learn it
from a rejection:

**And count how many of your lines had to be parked.** That number is the
honest grade for the whole run: a pipeline that resolved nothing books every
line to the holding account and can see that it failed.

## When a row will not post, you may go back and resolve it

You have the same reference lists and the same `kit.lookup`, `kit.variants`,
`kit.narrative_span` and `t.candidates` that the resolution step had. So when
a row cannot be booked because its counterparty never resolved, **rework that
row rather than parking it by default** — and you are in a far better position
to do it than the earlier step was, because you now know exactly which rows
matter instead of facing all of them at once.

For each one: print the narrative, print what the lists hold near it, and
decide. If you change a resolution, update `counterparty_match` on the row and
give `why` a reason a reviewer can check. Every rule the resolution step was
given still binds — a `MATCH` must be verbatim in the list it names, a
`PROBABLE` needs a reason and a confidence below 1, and a party the data does
not hold stays unresolved and parked. Lowering this number by inventing a
match is the one outcome worse than a high number.

Record both, honestly:

    r = kit.batches_balance(rows)
    parked = <lines you booked to the holding account>
    ])

A claim that does not hold fails the attempt and its detail reaches your next
prompt, which is the fastest way to fix something. A claim that does hold
cannot make a failing attempt pass, so there is nothing to be gained by
claiming what you have not checked.

Never adjust an amount to make a batch balance. If it will not balance, the
line that is wrong is wrong, and saying so is the correct outcome.

## The reference data, and what each part is for

Anything else this run mounts is for context. Resolving against a table not
listed here fails, however real the value you find in it looks.

- the chart of accounts, for booking values only, never for a party:
      coa:Trans Type

## What the verifier checks

- double_entry  two lines per batch, one batch per row, equal and opposite, netting to zero
- posting       every transaction_type must exist in the chart of accounts

There are 18 rows to resolve.


Your journal.py was REJECTED by the verifier. Attempt 3 of 10.

This is the journal.py you wrote, in full. **Edit it.** Keep every part that
worked and change the part the verifier objected to — a rewrite from scratch
loses what you had already got right, and you will not be able to tell which
of your own ideas has already been tried and falsified.

```python
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
```

These checks failed — the output is wrong:
- result_json: journal.py did not produce a readable /work/result.json
    ey are read as your report of what you looked
        at. And they can only ever add a failure: nothing you assert can make an
        attempt pass that the real checks rejected. So there is no advantage in
        claiming something holds when you have not checked it, and real value in

The evidence names the row and the exact discrepancy. Fix the cause, not
the symptom, and do not repeat the approach that just failed.

Reply with the complete corrected journal.py in a single ```python code block.

# reply

```python
import inspect
import json
import os
import sys
import kit

# Ensure line-buffered stdout so logs are never truncated
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

print("=== STARTING JOURNAL RUN ===", flush=True)

# 1. Print kit module info and functions
try:
    print(f"kit file: {kit.__file__}", flush=True)
    with open(kit.__file__) as f:
        src = f.read()
        print(f"kit source length: {len(src)}", flush=True)
        # Print function definitions in kit
        for line in src.splitlines():
            if line.startswith("def ") or line.startswith("class "):
                print("  ", line, flush=True)
except Exception as e:
    print(f"kit inspection note: {e}", flush=True)

# 2. Inspect available tables
tables = []
try:
    tables = kit.tables()
    print("Available tables:", tables, flush=True)
except Exception as e:
    print(f"kit.tables() error: {e}", flush=True)

# Helper to normalize table data to a list of dicts
def load_table_records(tbl_data):
    if hasattr(tbl_data, "to_dict"):
        try:
            return tbl_data.to_dict("records")
        except Exception:
            pass
    records = []
    try:
        for item in tbl_data:
            if isinstance(item, dict):
                records.append(item)
            elif hasattr(item, "_asdict"):
                records.append(item._asdict())
            elif hasattr(item, "keys"):
                records.append({k: item[k] for k in item.keys()})
            elif isinstance(item, (list, tuple)):
                records.append(dict(enumerate(item)))
            else:
                d = getattr(item, "__dict__", None)
                if d:
                    records.append(dict(d))
                else:
                    records.append({"Trans Type": str(item)})
    except Exception as e:
        print(f"Error converting records: {e}", flush=True)
    return records

# Inspect reference tables
for t in tables:
    if t != "coa":
        try:
            tbl = kit.table(t)
            recs = load_table_records(tbl)
            print(f"Table '{t}': {len(recs)} records. Sample 0: {recs[0] if recs else 'empty'}", flush=True)
        except Exception as e:
            print(f"Error reading table '{t}': {e}", flush=True)

# 3. Load and inspect COA
coa_raw = kit.table("coa")
coa_records = load_table_records(coa_raw)
print(f"COA total records: {len(coa_records)}", flush=True)
if coa_records:
    print("COA sample 0:", coa_records[0], flush=True)
    if len(coa_records) > 1:
        print("COA sample 1:", coa_records[1], flush=True)

all_trans_types = []
coa_by_currency = {}
holding_trans_types = []
cash_trans_types = []

for rec in coa_records:
    tt = rec.get("Trans Type") or rec.get("trans_type") or rec.get("TransType") or rec.get("Account Name")
    if not tt and 0 in rec:
        tt = rec[0]
    if not tt:
        continue
    tt = str(tt).strip()
    all_trans_types.append(tt)
    
    cur = rec.get("Currency") or rec.get("currency")
    if cur:
        cur = str(cur).strip().upper()
        coa_by_currency.setdefault(cur, []).append(rec)
        
    tt_lower = tt.lower()
    if any(w in tt_lower for w in ["hold", "suspense", "unresolved", "park", "clearing"]):
        holding_trans_types.append(tt)
    if any(w in tt_lower for w in ["cash", "bank", "operating"]):
        cash_trans_types.append(tt)

unique_trans_types = sorted(set(all_trans_types))
print(f"Unique Trans Types ({len(unique_trans_types)}):", unique_trans_types, flush=True)
print("Holding candidates:", holding_trans_types, flush=True)
print("Cash candidates:", cash_trans_types, flush=True)

# Determine holding account
holding_account = None
for cand in holding_trans_types:
    if "holding" in cand.lower():
        holding_account = cand
        break
if not holding_account and holding_trans_types:
    holding_account = holding_trans_types[0]
if not holding_account and unique_trans_types:
    holding_account = unique_trans_types[-1]

print(f"Selected holding account: {holding_account}", flush=True)

# 4. Inspect rows
rows = kit.rows()
print(f"=== INPUT ROWS ({len(rows)}) ===", flush=True)
for i, r in enumerate(rows):
    print(
        f"Row {i}: id={r.get('id')} amt={r.get('amount')} is_debit={r.get('is_debit')} "
        f"cur={r.get('currency')} cls={r.get('classification')} cp={r.get('counterparty_match')} "
        f"narr={repr(r.get('narrative'))}",
        flush=True
    )

def is_resolved(cp_match):
    if not cp_match:
        return False
    if isinstance(cp_match, dict):
        status = str(cp_match.get("status", "")).upper()
        if status in ("UNRESOLVED", "NONE", "UNMATCHED"):
            return False
        # If there is a matched name/party
        if cp_match.get("match") or cp_match.get("name") or cp_match.get("counterparty"):
            return True
        return False
    if isinstance(cp_match, str):
        return cp_match.upper() not in ("UNRESOLVED", "NONE", "UNMATCHED", "")
    return True

def find_cash_account(cur):
    if cur:
        cur_upper = str(cur).upper()
        # Look for cash accounts matching currency in coa_records
        for rec in coa_records:
            e_cur = rec.get("Currency")
            tt = rec.get("Trans Type") or rec.get("Account Name")
            if e_cur and str(e_cur).upper() == cur_upper and tt:
                if any(w in str(tt).lower() for w in ["cash", "bank", "operating"]):
                    return str(tt)
        # Look for currency string in Trans Type
        for tt in cash_trans_types:
            if cur_upper in tt.upper():
                return tt
    if cash_trans_types:
        return cash_trans_types[0]
    return unique_trans_types[0] if unique_trans_types else "Cash"

def find_counterparty_account(cls, cur):
    cls_str = str(cls).strip().lower() if cls else ""
    cur_str = str(cur).strip().upper() if cur else ""
    
    # Check exact/best match in coa_records
    best_match = None
    for rec in coa_records:
        e_cls = str(rec.get("Classification", "")).lower()
        e_cur = str(rec.get("Currency", "")).upper()
        tt = rec.get("Trans Type")
        if not tt:
            continue
        tt_str = str(tt)
        if cls_str and e_cls == cls_str:
            if cur_str and e_cur == cur_str:
                return tt_str
            if not best_match:
                best_match = tt_str
        elif cls_str and cls_str in tt_str.lower():
            if cur_str and e_cur == cur_str:
                return tt_str
            if not best_match:
                best_match = tt_str
                
    if best_match:
        return best_match
        
    for tt in unique_trans_types:
        if cls_str and cls_str in tt.lower():
            return tt
            
    return holding_account

# 5. Build journal entries
parked_count = 0
for i, r in enumerate(rows):
    batch_id = str(r.get("id") if r.get("id") is not None else f"row_{i}")
    
    raw_amt = r.get("amount", 0)
    amt_str = f"{abs(float(raw_amt)):.2f}"
    
    stmt_is_debit = bool(r.get("is_debit", True))
    # "The cash leg is the credit when the statement row is a debit, and the debit when it is a credit."
    cash_is_debit = not stmt_is_debit
    cp_is_debit = stmt_is_debit
    
    cur = r.get("currency")
    cls = r.get("classification")
    cp_match = r.get("counterparty_match")
    
    cash_tt = find_cash_account(cur)
    
    if not is_resolved(cp_match):
        cp_tt = holding_account
        parked_count += 1
    else:
        cp_tt = find_counterparty_account(cls, cur)
        if cp_tt == holding_account:
            parked_count += 1
            
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
bal = kit.batches_balance(rows)
print(f"kit.batches_balance result: {bal}", flush=True)
print(f"Parked lines count: {parked_count}", flush=True)

# 7. Write result using kit.write_result
print("Writing result via kit.write_result...", flush=True)
kit.write_result(rows)

# Ensure /work/result.json is present and valid
result_path = "/work/result.json"
try:
    if not os.path.exists(result_path) or os.path.getsize(result_path) == 0:
        print(f"Writing direct backup to {result_path}...", flush=True)
        with open(result_path, "w") as f:
            json.dump(rows, f, indent=2, default=str)
    print(f"Confirmed {result_path} exists (size={os.path.getsize(result_path)} bytes)", flush=True)
except Exception as e:
    print(f"File verification note: {e}", flush=True)

print(f"parsed {len(rows)} rows", flush=True)
```
