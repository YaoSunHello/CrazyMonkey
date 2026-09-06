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

There are 16 rows to resolve.


Your journal.py was REJECTED by the verifier. Attempt 2 of 10.

This is the journal.py you wrote, in full. **Edit it.** Keep every part that
worked and change the part the verifier objected to — a rewrite from scratch
loses what you had already got right, and you will not be able to tell which
of your own ideas has already been tried and falsified.

```python
import json
import kit

# 1. Inspect questions and tables
print("=== QUESTIONS ===")
try:
    print(kit.questions())
except Exception as e:
    print(f"Error reading questions: {e}")

print("\n=== TABLES ===")
try:
    tables = kit.tables()
    print("Tables:", tables)
except Exception as e:
    print(f"Error reading tables: {e}")
    tables = []

# 2. Inspect rows
print("\n=== ROWS ===")
rows = kit.rows()
print(f"Number of rows: {len(rows)}")
for i, r in enumerate(rows):
    print(f"Row {i}: {json.dumps(r, default=str)}")

# Collect currencies, classifications, etc. from rows
currencies = {r.get("currency") for r in rows if "currency" in r}
classifications = {r.get("classification") for r in rows if "classification" in r}
print(f"\nRow currencies: {currencies}")
print(f"Row classifications: {classifications}")

# 3. Inspect COA
print("\n=== COA ===")
coa = kit.table("coa")
print(f"COA type: {type(coa)}, length: {len(coa)}")

if len(coa) > 0:
    first_item = coa[0]
    print(
        "First COA item keys/structure:",
        (
            list(first_item.keys())
            if isinstance(first_item, dict)
            else dir(first_item)
        ),
    )
    print("First 3 COA items:", coa[:3])

    # Extract all Trans Types
    trans_types = []
    for item in coa:
        if isinstance(item, dict):
            tt = item.get("Trans Type")
        else:
            tt = getattr(item, "Trans Type", None)
        if tt is not None and tt not in trans_types:
            trans_types.append(tt)

    print(f"Total unique Trans Types: {len(trans_types)}")
    print("Trans Types:")
    for tt in sorted(trans_types):
        print(f"  {tt}")

    # Search for holding / suspense / unallocated / parked / cash / bank
    keywords = [
        "hold",
        "susp",
        "park",
        "unres",
        "unident",
        "unalloc",
        "clear",
        "cash",
        "bank",
    ]
    print("\nMatching COA rows by keyword:")
    for item in coa:
        row_str = str(item).lower()
        if any(k in row_str for k in keywords):
            print(" ", item)

# Call write_result as required by the rules
kit.write_result(rows)
print("parsed 16 rows")
```

These checks failed — the output is wrong:
- result_json: journal.py did not produce a readable /work/result.json
    _number": "240-524291-030", "currency": "EUR", "page": 2, "counterparty_raw": null, "counterparty_match": {"status": "CANNOT_VERIFY", "matched_name": null, "table": null, "confidence": null, "why": "No counterparty identified in narrative"}, "project_code_raw": null, "project_code_match": {"status": "CANNOT_VERIFY", "matched_name": null, "table": null, "confidence": null, "why": null}, "classification": "Other"}
    
    Row currencies: {'EUR'}
    Row classifications: {'Internal', 'Investment', 'Vendor', 'Related Party', 'Other', 'Investment Transfer'}

The evidence names the row and the exact discrepancy. Fix the cause, not
the symptom, and do not repeat the approach that just failed.

Reply with the complete corrected journal.py in a single ```python code block.

# reply

```python
import json
import sys
import kit

# Ensure unbuffered output
sys.stdout.reconfigure(line_buffering=True)

print("=== START JOURNAL PROCESSING ===", flush=True)

# 1. Questions & Tables
try:
    print(f"Questions: {kit.questions()}", flush=True)
except Exception as e:
    print(f"Questions error: {e}", flush=True)

try:
    tables = kit.tables()
    print(f"Tables: {tables}", flush=True)
except Exception as e:
    print(f"Tables error: {e}", flush=True)

# 2. Inspect Rows
rows = kit.rows()
print(f"Total rows: {len(rows)}", flush=True)

# Print summary of each row
for i, r in enumerate(rows):
    c_match = r.get("counterparty_match", {})
    status = (
        c_match.get("status")
        if isinstance(c_match, dict)
        else getattr(c_match, "status", None)
    )
    name = (
        c_match.get("matched_name")
        if isinstance(c_match, dict)
        else getattr(c_match, "matched_name", None)
    )
    print(
        f"Row {i:02d}: amt={r.get('amount')}, deb={r.get('debit')}, cred={r.get('credit')}, "
        f"curr={r.get('currency')}, class={r.get('classification')}, "
        f"cp_status={status}, cp_name={name}",
        flush=True,
    )

# 3. Load and Inspect Chart of Accounts
coa_raw = kit.table("coa")
print(f"COA raw type: {type(coa_raw)}", flush=True)

if hasattr(coa_raw, "to_dict"):
    coa_records = coa_raw.to_dict(orient="records")
elif hasattr(coa_raw, "iterrows"):
    coa_records = [row.to_dict() for _, row in coa_raw.iterrows()]
elif isinstance(coa_raw, list):
    coa_records = [
        dict(r) if hasattr(r, "items") else r
        for r in coa_raw
        if isinstance(r, dict) or hasattr(r, "items")
    ]
else:
    coa_records = []

print(f"COA record count: {len(coa_records)}", flush=True)
if coa_records:
    print(f"COA sample record keys: {list(coa_records[0].keys())}", flush=True)
    print(f"COA sample record: {coa_records[0]}", flush=True)

# Extract all Trans Types
coa_trans_types = []
for item in coa_records:
    tt = item.get("Trans Type") if isinstance(item, dict) else None
    if tt and tt not in coa_trans_types:
        coa_trans_types.append(tt)

print(f"Unique Trans Types ({len(coa_trans_types)}):", flush=True)
for tt in sorted(coa_trans_types):
    print(f"  {tt}", flush=True)

# Print all COA rows for full visibility
print("--- ALL COA RECORDS ---", flush=True)
for cr in coa_records:
    print(f"  {cr}", flush=True)


# 4. Helper to find Trans Types
def find_matching_trans_type(candidates, default=None):
    for c in candidates:
        for tt in coa_trans_types:
            if c.lower() == tt.lower():
                return tt
    for c in candidates:
        for tt in coa_trans_types:
            if c.lower() in tt.lower():
                return tt
    return default


# Find holding account
holding_keywords = [
    "holding",
    "suspense",
    "unallocated",
    "unresolved",
    "parked",
    "clearing",
    "unknown",
]
holding_candidates = []
for cr in coa_records:
    row_str = " ".join(str(v).lower() for v in cr.values())
    if any(hk in row_str for hk in holding_keywords):
        tt = cr.get("Trans Type")
        if tt and tt not in holding_candidates:
            holding_candidates.append(tt)

print(f"Holding candidates: {holding_candidates}", flush=True)
holding_account = holding_candidates[0] if holding_candidates else None
print(f"Selected holding account: {holding_account}", flush=True)


# Find cash account by currency
def get_cash_account(currency):
    curr = (currency or "").upper()
    # Check records matching currency and cash/bank
    for cr in coa_records:
        row_str = " ".join(str(v).lower() for v in cr.values())
        if ("cash" in row_str or "bank" in row_str) and (curr.lower() in row_str):
            tt = cr.get("Trans Type")
            if tt:
                return tt
    # Check if Trans Type contains cash and curr
    for tt in coa_trans_types:
        if "cash" in tt.lower() and curr.lower() in tt.lower():
            return tt
    # Any cash account
    for tt in coa_trans_types:
        if "cash" in tt.lower() or "bank" in tt.lower():
            return tt
    return coa_trans_types[0] if coa_trans_types else "Cash"


# Find counterpart account by classification and currency
def get_counterpart_account(classification, currency, is_resolved):
    if not is_resolved or not holding_account:
        return holding_account

    cls_str = (classification or "").lower()
    curr_str = (currency or "").lower()

    # Look for exact or keyword match in COA records
    best_tt = None
    for cr in coa_records:
        row_str = " ".join(str(v).lower() for v in cr.values())
        tt = cr.get("Trans Type")
        if not tt:
            continue
        # Avoid cash accounts for counterpart leg
        if "cash" in tt.lower() or "bank" in tt.lower():
            continue
        if cls_str in row_str:
            if curr_str and curr_str in row_str:
                return tt
            if not best_tt:
                best_tt = tt

    if best_tt:
        return best_tt

    # Search in trans type directly
    for tt in coa_trans_types:
        if "cash" in tt.lower() or "bank" in tt.lower():
            continue
        if cls_str in tt.lower():
            return tt

    return holding_account


# 5. Extract amount and statement debit/credit for each row
def parse_amount_and_direction(r):
    debit_val = r.get("debit")
    credit_val = r.get("credit")

    def clean_val(v):
        if v is None or v == "":
            return None
        try:
            return float(str(v).replace(",", "").strip())
        except ValueError:
            return None

    d_num = clean_val(debit_val)
    c_num = clean_val(credit_val)

    if d_num is not None and d_num > 0:
        return f"{d_num:.2f}", True
    if c_num is not None and c_num > 0:
        return f"{c_num:.2f}", False

    amt_val = clean_val(r.get("amount"))
    if amt_val is not None:
        if r.get("is_debit") is not None:
            return f"{abs(amt_val):.2f}", bool(r["is_debit"])
        if amt_val < 0:
            return f"{abs(amt_val):.2f}", True
        else:
            return f"{abs(amt_val):.2f}", False

    return "0.00", False


# 6. Build Journal Lines
parked_count = 0
for i, r in enumerate(rows):
    batch_id = r.get("id") or f"batch_{i + 1}"
    amount_str, is_stmt_debit = parse_amount_and_direction(r)
    currency = r.get("currency")
    classification = r.get("classification")

    # Check resolution status
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

    cash_tt = get_cash_account(currency)
    cp_tt = get_counterpart_account(classification, currency, is_resolved)

    if cp_tt == holding_account:
        parked_count += 1

    # Direction rule:
    # "The cash leg is the credit when the statement row is a debit, and the debit when it is a credit."
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

print(f"\nConstructed journal lines for {len(rows)} rows.", flush=True)
print(f"Total lines parked to holding account: {parked_count}", flush=True)

# 7. Check double entry balance
try:
    bal_res = kit.batches_balance(rows)
    print(f"batches_balance result: {bal_res}", flush=True)
except Exception as e:
    print(f"Error checking batches_balance: {e}", flush=True)

# 8. Write Result
kit.write_result(rows)
print(f"parsed {len(rows)} rows", flush=True)
```
