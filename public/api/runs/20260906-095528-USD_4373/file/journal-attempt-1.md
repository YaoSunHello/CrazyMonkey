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

There are 19 rows to resolve.


# reply

```python
import kit

# 1. Inspect tables and COA
print("Tables:", kit.tables())
coa = kit.table("coa")
print(f"COA has {len(coa)} entries. Columns: {coa.columns if hasattr(coa, 'columns') else (list(coa[0].keys()) if coa else 'empty')}")

# Print first few entries of COA
for i, entry in enumerate(coa[:20]):
    print(f"COA[{i}]: {entry}")

# Search for holding / suspense / cash accounts in COA
trans_types = []
for entry in coa:
    tt = entry.get("Trans Type") or entry.get("trans_type") or entry.get("Transaction Type")
    trans_types.append((tt, entry))

print(f"Total trans types: {len(trans_types)}")

# Let's inspect rows
rows = kit.rows()
print(f"Total rows: {len(rows)}")
for i, r in enumerate(rows):
    print(f"Row {i}: {r}")

# Print questions if any
print("Questions:", kit.questions())

# Find holding account
holding_candidates = [
    tt for tt, entry in trans_types 
    if any(term in str(entry).lower() for term in ["holding", "suspense", "unresolved", "unallocated", "clearing", "parked"])
]
print("Holding candidates:", holding_candidates)

# Find cash / bank accounts
cash_candidates = [
    tt for tt, entry in trans_types 
    if any(term in str(entry).lower() for term in ["cash", "bank", "operating", "checking", "current"])
]
print("Cash candidates:", cash_candidates)

# Print all trans types to inspect their names
print("All Trans Types:")
for tt, entry in trans_types:
    print("  ", tt, "-->", entry)

# Try to match rows to accounts
# Let's check how rows indicate cash leg vs counterparty leg
# And create journal lines accordingly
# To be safe on attempt 1, let's build the best mapping we can
# If we need to see stdout, we can raise an assertion or let's see how batches_balance works.

enriched_rows = []
for i, r in enumerate(rows):
    r_copy = dict(r)
    # determine batch id
    batch_id = r.get("batch") or f"BATCH-{i+1:04d}"
    
    # Amount
    amt = str(r.get("amount", "0.00")).replace(",", "").replace("-", "")
    # Check debit / credit on the row
    # In statement row: "The cash leg is the credit when the statement row is a debit, and the debit when it is a credit."
    # How is row debit/credit represented? Let's check r's keys.
    is_stmt_debit = False
    if "is_debit" in r:
        is_stmt_debit = bool(r["is_debit"])
    elif "direction" in r:
        is_stmt_debit = r["direction"].lower() in ["debit", "dr", "out", "outflow", "withdrawal", "payment"]
    elif "type" in r:
        is_stmt_debit = r["type"].lower() in ["debit", "dr", "out", "withdrawal", "payment"]
    elif float(r.get("amount", 0)) < 0:
        is_stmt_debit = True
        
    cash_is_debit = not is_stmt_debit
    cp_is_debit = is_stmt_debit
    
    # Find matching trans types (placeholder logic for attempt 1 inspection if needed)
    # We will pick the first cash and holding candidates if not sure
    cash_tt = cash_candidates[0] if cash_candidates else (trans_types[0][0] if trans_types else "Cash")
    cp_tt = holding_candidates[0] if holding_candidates else (trans_types[-1][0] if trans_types else "Holding")
    
    # But wait! If counterparty_match resolved to something, let's see what row holds
    # Let's see what counterparty fields exist
    
    lines = [
        {"batch": batch_id, "amount": amt, "is_debit": cash_is_debit, "transaction_type": cash_tt},
        {"batch": batch_id, "amount": amt, "is_debit": cp_is_debit, "transaction_type": cp_tt}
    ]
    r_copy["journal_lines"] = lines
    enriched_rows.append(r_copy)

# Verify batches balance
bal = kit.batches_balance(enriched_rows)
print("Batches balance check:", bal)

# Intentional assertion to review stdout in attempt 1 if not completely confident,
# OR write result if we want verifier feedback.
# Let's assert False to inspect all data clearly first!
assert False, "Inspection pass: reviewing stdout for COA, rows, and account mappings."
```
