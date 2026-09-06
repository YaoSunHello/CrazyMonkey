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

There are 10 rows to resolve.


# reply

```python
import json
import kit

# 1. Questions
print("=== QUESTIONS ===")
try:
    q = kit.questions()
    print(json.dumps(q, indent=2, default=str))
except Exception as e:
    print(f"Error reading questions: {e}")

# 2. Tables and Reference Data
print("\n=== TABLES ===")
try:
    tables = kit.tables()
    print("Available tables:", tables)
    for name in tables:
        tbl = kit.table(name)
        print(f"\n--- Table: {name} ---")
        if hasattr(tbl, "shape"):
            print("Shape:", tbl.shape)
            print("Columns:", tbl.columns.tolist())
            print(tbl.to_string())
        elif isinstance(tbl, list):
            print(f"Count: {len(tbl)}")
            for idx, item in enumerate(tbl):
                print(f"  [{idx}]: {item}")
        elif isinstance(tbl, dict):
            print(f"Dict keys: {list(tbl.keys())}")
            for k, v in tbl.items():
                print(f"  {k}: {v}")
        else:
            print("Type:", type(tbl))
            print(tbl)
except Exception as e:
    print(f"Error reading tables: {e}")

# 3. Statement Rows
print("\n=== ROWS ===")
rows = kit.rows()
print(f"Total rows: {len(rows)}")
for i, r in enumerate(rows):
    print(f"\n--- Row {i} ---")
    for k, v in sorted(r.items()):
        print(f"  {k}: {v}")

# 4. Candidates / Lookups for Counterparties
print("\n=== CANDIDATES FOR ROWS ===")
for i, r in enumerate(rows):
    narrative = r.get("narrative", "")
    print(f"\nRow {i} narrative: {repr(narrative)}")
    print(f"  counterparty_match: {r.get('counterparty_match')}")
    for t_name in kit.tables():
        if t_name == "coa":
            continue
        try:
            cands = kit.candidates(narrative, [t_name])
            print(f"  Candidates in {t_name}: {cands}")
        except Exception as e:
            try:
                tbl = kit.table(t_name)
                cands = kit.candidates(narrative, [tbl])
                print(f"  Candidates in {t_name} (obj): {cands}")
            except Exception as e2:
                print(f"  Candidate lookup error on {t_name}: {e2}")

# 5. Check batches_balance behavior
print("\n=== TEST BATCHES_BALANCE ===")
try:
    test_batch = [
        {
            "journal_lines": [
                {
                    "batch": "test-1",
                    "amount": "100.00",
                    "is_debit": True,
                    "transaction_type": "Test",
                },
                {
                    "batch": "test-1",
                    "amount": "100.00",
                    "is_debit": False,
                    "transaction_type": "Test",
                },
            ]
        }
    ]
    bb_res = kit.batches_balance(test_batch)
    print("batches_balance result:", bb_res)
except Exception as e:
    print(f"Error testing batches_balance: {e}")

# 6. Create initial placeholder journal lines to trigger verifier check & inspect output
enriched = []
for i, r in enumerate(rows):
    row_copy = dict(r)
    amt = str(r.get("amount", "0.00"))
    batch_id = f"batch_{i+1}"
    row_copy["journal_lines"] = [
        {
            "batch": batch_id,
            "amount": amt,
            "is_debit": True,
            "transaction_type": "__INSPECTION__",
        },
        {
            "batch": batch_id,
            "amount": amt,
            "is_debit": False,
            "transaction_type": "__INSPECTION__",
        },
    ]
    enriched.append(row_copy)

kit.write_result(enriched)
print("inspected 10 rows")
```
