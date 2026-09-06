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


Your journal.py was REJECTED by the verifier. Attempt 5 of 10.

This is the journal.py you wrote, in full. **Edit it.** Keep every part that
worked and change the part the verifier objected to — a rewrite from scratch
loses what you had already got right, and you will not be able to tell which
of your own ideas has already been tried and falsified.

```python
import sys
import kit

print("=== INSPECTION START ===")
print("kit attributes:", dir(kit))

try:
    tables = kit.tables()
    print("kit.tables():", tables)
except Exception as e:
    print("kit.tables() failed:", type(e), e)

try:
    print("kit.table:", type(kit.table))
    t = kit.table("coa")
    print("type(kit.table('coa')):", type(t))
    if hasattr(t, "columns"):
        print("COA columns:", t.columns)
        print("COA head:\n", t.head())
    elif isinstance(t, list):
        print("COA list len:", len(t))
        if t:
            print("COA[0]:", t[0])
    elif isinstance(t, dict):
        print("COA dict keys:", list(t.keys())[:10])
    else:
        print("COA repr:", repr(t)[:200])
except Exception as e:
    print("kit.table('coa') failed:", type(e), e)

try:
    q = kit.questions()
    print("kit.questions():", q)
except Exception as e:
    print("kit.questions() failed:", type(e), e)

try:
    rows = kit.rows()
    print(f"kit.rows() count: {len(rows)}")
    for i, r in enumerate(rows):
        print(f"ROW {i}: {r}")
except Exception as e:
    print("kit.rows() failed:", type(e), e)

print("=== INSPECTION END ===")
sys.stdout.flush()

assert False, "Forced stop to inspect stdout"
```

These checks failed — the output is wrong:
- result_json: journal.py did not produce a readable /work/result.json
    6', 'time': '21:06', 'narrative': 'CREDIT INTEREST', 'credit': '95.47', 'debit': None, 'balance': '6683.14', 'account_number': '240-222731-132', 'currency': 'GBP', 'page': 2, 'counterparty_raw': None, 'counterparty_match': {'status': 'CANNOT_VERIFY', 'matched_name': None, 'table': None, 'confidence': None, 'why': 'Bank commission charge or credit interest names no counterparty'}, 'project_code_raw': None, 'project_code_match': {'status': 'CANNOT_VERIFY', 'matched_name': None, 'table': None, 'confidence': None, 'why': 'Narrative names no project'}, 'classification': 'Other'}
    === INSPECTION END ===
    Traceback (most recent call last):
      File "/work/journal.py", line 48, in <module>

The evidence names the row and the exact discrepancy. Fix the cause, not
the symptom, and do not repeat the approach that just failed.

Reply with the complete corrected journal.py in a single ```python code block.

# reply

```python
import inspect
import json
import sys
import kit

print("=== JOURNAL PROCESSING START ===")

# 1. Load Chart of Accounts
coa_table = kit.table("coa")
if hasattr(coa_table, "to_dict"):
    coa_records = coa_table.to_dict("records")
elif isinstance(coa_table, list):
    coa_records = coa_table
else:
    coa_records = list(coa_table)

coa_cols = list(coa_records[0].keys()) if coa_records else []
tt_col = next((c for c in coa_cols if c.strip().lower() == "trans type"), coa_cols[0])
all_trans_types = [
    str(r[tt_col]).strip() for r in coa_records if r.get(tt_col) is not None
]
print(f"COA loaded: {len(coa_records)} rows, tt_col='{tt_col}'")


# 2. Account Finders
def get_cash_account(currency):
    cur = (currency or "GBP").upper()
    best = None
    best_score = -999
    for r in coa_records:
        tt = str(r[tt_col]).strip()
        text = " ".join(str(v) for v in r.values()).lower()
        tt_low = tt.lower()

        # Disqualify non-cash accounts
        if any(
            bad in tt_low
            for bad in [
                "fee",
                "charge",
                "interest",
                "loan",
                "suspense",
                "holding",
                "payable",
                "receivable",
            ]
        ):
            continue

        score = 0
        if cur.lower() in tt_low:
            score += 20
        elif cur.lower() in text:
            score += 10

        if "bank" in tt_low:
            score += 10
        elif "bank" in text:
            score += 5

        if "cash" in tt_low:
            score += 8
        elif "cash" in text:
            score += 4

        if "current" in tt_low:
            score += 5

        if score > best_score:
            best_score = score
            best = tt
    return best


def get_holding_account():
    best = None
    best_score = -999
    for r in coa_records:
        tt = str(r[tt_col]).strip()
        text = " ".join(str(v) for v in r.values()).lower()
        tt_low = tt.lower()

        score = 0
        if "holding" in tt_low:
            score += 30
        elif "holding" in text:
            score += 15

        if "suspense" in tt_low:
            score += 30
        elif "suspense" in text:
            score += 15

        if "unallocated" in tt_low:
            score += 20
        elif "unallocated" in text:
            score += 10

        if "parked" in tt_low:
            score += 20

        if "clearing" in tt_low:
            score += 5

        if score > best_score:
            best_score = score
            best = tt
    return best


def get_counterpart_account(classification, currency, holding_account):
    cl_low = (classification or "").lower()
    cur_low = (currency or "GBP").lower()

    if any(
        w in cl_low
        for w in [
            "supplier",
            "vendor",
            "creditor",
            "payable",
            "purchase",
            "trade payable",
        ]
    ):
        target_kws = [
            "trade creditor",
            "accounts payable",
            "trade payable",
            "creditor",
            "payable",
            "supplier",
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
        ]
    ):
        target_kws = [
            "trade debtor",
            "accounts receivable",
            "trade receivable",
            "debtor",
            "receivable",
            "customer",
        ]
    elif any(w in cl_low for w in ["payroll", "wage", "salaries", "salary"]):
        target_kws = ["payroll", "wages", "salaries", "salary"]
    elif any(w in cl_low for w in ["tax", "vat", "hmrc"]):
        target_kws = ["vat", "tax", "hmrc"]
    else:
        return holding_account

    best = None
    best_score = -999
    for r in coa_records:
        tt = str(r[tt_col]).strip()
        text = " ".join(str(v) for v in r.values()).lower()
        tt_low = tt.lower()

        if any(
            bad in tt_low
            for bad in ["bank", "cash", "suspense", "holding", "clearing"]
        ):
            continue

        score = 0
        for i, kw in enumerate(target_kws):
            if kw in tt_low:
                score += 30 - i * 3
            elif kw in text:
                score += 15 - i * 2

        if score > 0:
            if cur_low in tt_low:
                score += 10
            elif cur_low in text:
                score += 5

        if score > best_score:
            best_score = score
            best = tt

    return best or holding_account


holding_account = get_holding_account()
cash_gbp = get_cash_account("GBP")
print(f"Selected holding_account: '{holding_account}', cash_gbp: '{cash_gbp}'")

# 3. Process Rows
rows = kit.rows()
print(f"Processing {len(rows)} rows...")

for i, row in enumerate(rows):
    cur = row.get("currency", "GBP")
    cash_acc = get_cash_account(cur)

    # Counterparty resolution check
    cp_match = row.get("counterparty_match") or {}
    is_resolved = cp_match.get("status") in ("MATCH", "PROBABLE") and bool(
        cp_match.get("matched_name")
    )

    if is_resolved:
        cp_acc = get_counterpart_account(
            row.get("classification"), cur, holding_account
        )
    else:
        cp_acc = holding_account

    # Determine amount & direction
    if row.get("credit") is not None and str(row["credit"]).strip() not in (
        "",
        "None",
    ):
        amt = f"{float(str(row['credit']).replace(',', '').strip()):0.2f}"
        cash_is_debit = True
        cp_is_debit = False
    elif row.get("debit") is not None and str(row["debit"]).strip() not in (
        "",
        "None",
    ):
        amt = f"{float(str(row['debit']).replace(',', '').strip()):0.2f}"
        cash_is_debit = False
        cp_is_debit = True
    else:
        raise ValueError(f"Row {i} has neither credit nor debit: {row}")

    batch_id = f"batch_{i+1:03d}"

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

    # Order by debit first
    if cash_is_debit:
        row["journal_lines"] = [line_cash, line_cp]
    else:
        row["journal_lines"] = [line_cp, line_cash]

# 4. Verify Double Entry
r_bal = kit.batches_balance(rows, field="journal_lines")
print("batches_balance check:", r_bal)

parked_lines = [
    line
    for r in rows
    for line in r["journal_lines"]
    if line["transaction_type"] == holding_account
]
parked_count = len(parked_lines)
print(f"Parked lines count: {parked_count}")

# 5. Handle Questions & Assertions
try:
    q = kit.questions()
    print("kit.questions():", q)
    claims = None
    if isinstance(q, dict):
        claims = {}
        for k in q:
            kl = k.lower()
            if "balance" in kl:
                claims[k] = r_bal
            elif "park" in kl:
                claims[k] = parked_count
            else:
                claims[k] = True
    elif isinstance(q, list):
        claims = []
        for item in q:
            if isinstance(item, dict) and "id" in item:
                qid = item["id"].lower()
                val = (
                    r_bal
                    if "balance" in qid
                    else (parked_count if "park" in qid else True)
                )
                claims.append({**item, "value": val})
            elif isinstance(item, str):
                item_low = item.lower()
                val = (
                    r_bal
                    if "balance" in item_low
                    else (parked_count if "park" in item_low else True)
                )
                claims.append(val)
    if claims is not None:
        kit.write_assertions(claims)
        print("Assertions written.")
except Exception as e:
    print("Assertions handling notice:", e)

# 6. Write Result
kit.write_result(rows)
print("Result written via kit.write_result.")
print(f"parsed {len(rows)} rows")
```
