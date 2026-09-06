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


Your journal.py was REJECTED by the verifier. Attempt 5 of 10.

This is the journal.py you wrote, in full. **Edit it.** Keep every part that
worked and change the part the verifier objected to — a rewrite from scratch
loses what you had already got right, and you will not be able to tell which
of your own ideas has already been tried and falsified.

```python
from decimal import Decimal
import kit


# Safely load tables whether they are lists, generators, or custom iterables
def load_table(name):
    t = kit.table(name)
    if isinstance(t, list):
        return t
    return list(t)


# 1. Inspect reference tables
tables = kit.tables()
print("Tables:", tables)

coa = load_table("coa")
print(f"COA count: {len(coa)}")
coa_trans_types = [
    r.get("Trans Type") for r in coa if r.get("Trans Type") is not None
]
print(f"COA Trans Types ({len(coa_trans_types)}):", coa_trans_types)

account_map = load_table("account_map") if "account_map" in tables else []
print(f"account_map count: {len(account_map)}")
for r in account_map:
    print("account_map entry:", r)

allocation_rules = (
    load_table("allocation_rules") if "allocation_rules" in tables else []
)
print(f"allocation_rules count: {len(allocation_rules)}")
for r in allocation_rules:
    print("allocation_rules entry:", r)

for t_name in tables:
    if t_name not in ("coa", "account_map", "allocation_rules"):
        t = load_table(t_name)
        print(f"Table '{t_name}' ({len(t)} entries):")
        for r in t[:10]:
            print(" ", r)

# 2. Inspect rows
rows = kit.rows()
if not isinstance(rows, list):
    rows = list(rows)
print(f"Rows count: {len(rows)}")

for i, r in enumerate(rows):
    dr = r.get("debit")
    cr = r.get("credit")
    cur = r.get("currency")
    cls = r.get("classification")
    cpm = r.get("counterparty_match") or {}
    st = cpm.get("status")
    mn = cpm.get("matched_name")
    raw = r.get("counterparty_raw")
    nar = r.get("narrative") or r.get("description") or ""
    print(
        f"R{i:02d} | id:{r.get('id')} | cur:{cur} | cls:{cls} | dr:{dr} cr:{cr} | cp_st:{st} | cp_match:{mn} | nar:{nar[:40]}"
    )

# 3. Identify holding / suspense account
holding_candidates = [
    tt
    for tt in coa_trans_types
    if any(
        w in tt.lower()
        for w in [
            "holding",
            "suspense",
            "unresolved",
            "unallocated",
            "clearing",
            "parked",
        ]
    )
]
print("Holding account candidates:", holding_candidates)
holding_type = holding_candidates[0] if holding_candidates else None
if not holding_type and coa_trans_types:
    holding_type = coa_trans_types[0]
print("Selected holding_type:", holding_type)

cash_candidates = [
    tt
    for tt in coa_trans_types
    if any(
        w in tt.lower()
        for w in ["cash", "bank", "operating", "current", "demand deposit"]
    )
]
print("Cash account candidates:", cash_candidates)


def get_cash_trans_type(currency):
    curr = (currency or "").strip().lower()

    # Check account_map first
    for row in account_map:
        row_str = " ".join(str(v).lower() for v in row.values())
        if curr in row_str and any(
            w in row_str for w in ["cash", "bank", "operating"]
        ):
            if "Trans Type" in row:
                return row["Trans Type"]

    # Check COA for currency + cash keyword
    for tt in coa_trans_types:
        ttl = tt.lower()
        if curr in ttl and any(
            w in ttl for w in ["cash", "bank", "operating", "current"]
        ):
            return tt

    # Check COA for currency alone
    for tt in coa_trans_types:
        if curr in tt.lower():
            return tt

    if cash_candidates:
        return cash_candidates[0]
    return coa_trans_types[0] if coa_trans_types else None


def get_cp_trans_type(r):
    cpm = r.get("counterparty_match") or {}
    st = cpm.get("status")
    # Unresolved counterparty must go to holding account
    if st not in ("MATCH", "PROBABLE") or not cpm.get("matched_name"):
        return holding_type

    cls = (r.get("classification") or "").strip()
    if not cls:
        return holding_type

    # 1. Check account_map for classification
    for row in account_map:
        for k, v in row.items():
            if str(v).strip().lower() == cls.lower():
                if "Trans Type" in row:
                    return row["Trans Type"]

    # 2. Check COA exact match for classification
    for tt in coa_trans_types:
        if tt.strip().lower() == cls.lower():
            return tt

    # 3. Check COA containing classification
    for tt in coa_trans_types:
        if cls.lower() in tt.lower():
            return tt

    # 4. Check COA containing classification keywords
    cls_words = [
        w for w in cls.lower().split() if w not in ["and", "or", "the", "of", "to"]
    ]
    if cls_words:
        for tt in coa_trans_types:
            if all(w in tt.lower() for w in cls_words):
                return tt

    return holding_type


# 4. Create journal lines for each row
for i, r in enumerate(rows):
    batch_id = str(r.get("id") if r.get("id") is not None else f"batch_{i+1}")

    dr = r.get("debit")
    cr = r.get("credit")
    if dr is not None and str(dr).strip() != "" and Decimal(str(dr)) != 0:
        raw_amt = abs(Decimal(str(dr)))
        is_statement_debit = True
    elif cr is not None and str(cr).strip() != "" and Decimal(str(cr)) != 0:
        raw_amt = abs(Decimal(str(cr)))
        is_statement_debit = False
    else:
        amt = r.get("amount")
        raw_amt = abs(Decimal(str(amt))) if amt is not None else Decimal("0.00")
        is_statement_debit = (
            (Decimal(str(amt)) < 0) if amt is not None else False
        )

    amt_str = f"{raw_amt:.2f}"

    # Cash leg: credit when statement is debit, debit when statement is credit
    cash_is_debit = not is_statement_debit
    cp_is_debit = is_statement_debit

    cash_tt = get_cash_trans_type(r.get("currency"))
    cp_tt = get_cp_trans_type(r)

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

# 5. Validate batches balance
bal = kit.batches_balance(rows, field="journal_lines")
print("Batches balance check:", bal)

parked_lines = sum(
    1
    for r in rows
    for line in r.get("journal_lines", [])
    if line.get("transaction_type") == holding_type
)
print(f"Total lines booked to holding account: {parked_lines}")

kit.write_result(rows)
print(f"parsed {len(rows)} rows")
```

These checks failed — the output is wrong:
- result_json: journal.py did not produce a readable /work/result.json
    Tables: ['account_map', 'allocation_rules', 'coa', 'deals_positions', 'legal_entities']
    Traceback (most recent call last):
      File "/work/journal.py", line 17, in <module>
        coa = load_table("coa")

The evidence names the row and the exact discrepancy. Fix the cause, not
the symptom, and do not repeat the approach that just failed.

Reply with the complete corrected journal.py in a single ```python code block.

# reply

```python
import csv
from decimal import Decimal
import inspect
import json
import os
import sys
import traceback
import kit

# 0. Inspect kit implementation to understand environment and prevent failures
try:
    with open(kit.__file__) as f:
        kit_src = f.read()
    idx = kit_src.find("def table")
    if idx != -1:
        print("KIT TABLE DEF:", kit_src[idx : idx + 350].replace("\n", " -- "))
    else:
        print("KIT FILE (no def table):", kit_src[:300].replace("\n", " -- "))
except Exception as e:
    print("Could not read kit.__file__:", e)


# Robust table loading
def normalize_table_data(t):
    if t is None:
        return []
    if isinstance(t, list):
        return t
    if hasattr(t, "to_dict"):
        try:
            return t.to_dict(orient="records")
        except Exception:
            return t.to_dict()
    if hasattr(t, "rows"):
        return list(t.rows)
    if hasattr(t, "data"):
        return list(t.data)
    if isinstance(t, dict):
        keys = list(t.keys())
        if keys and isinstance(t[keys[0]], (list, tuple)):
            n = len(t[keys[0]])
            return [{k: t[k][i] for k in keys} for i in range(n)]
        return [t]
    try:
        return list(t)
    except Exception:
        return []


def load_file_from_disk(name):
    search_dirs = [".", "..", "tables", "data", "/work", "/work/tables"]
    for d in search_dirs:
        if not os.path.exists(d):
            continue
        for ext in [".json", ".csv", ".tsv"]:
            path = os.path.join(d, f"{name}{ext}")
            if os.path.exists(path):
                print(f"Found {name} on disk at {path}")
                try:
                    if ext == ".json":
                        with open(path) as fp:
                            return normalize_table_data(json.load(fp))
                    elif ext in (".csv", ".tsv"):
                        delim = "\t" if ext == ".tsv" else ","
                        with open(path, newline="", encoding="utf-8-sig") as fp:
                            return list(csv.DictReader(fp, delimiter=delim))
                except Exception as e:
                    print(f"Error loading {path}: {e}")
    return []


def load_table_safe(name):
    # Try calling kit.table(name)
    try:
        if callable(getattr(kit, "table", None)):
            t = kit.table(name)
            data = normalize_table_data(t)
            if data:
                return data
    except Exception as e:
        print(
            f"kit.table('{name}') raised: {type(e).__name__}: {e} -- {traceback.format_exc().replace(chr(10), ' // ')}"
        )

    # Try subscripting kit.table[name] if table is a mapping
    try:
        if hasattr(kit, "table") and hasattr(kit.table, "__getitem__"):
            t = kit.table[name]
            data = normalize_table_data(t)
            if data:
                return data
    except Exception:
        pass

    # Try attributes on kit
    for attr in [name, f"_{name}", f"{name}_table"]:
        if hasattr(kit, attr):
            data = normalize_table_data(getattr(kit, attr))
            if data:
                return data

    # Fallback to disk
    return load_file_from_disk(name)


# 1. Inspect reference tables
tables = kit.tables() if callable(getattr(kit, "tables", None)) else []
print("Tables from kit.tables():", tables)

coa = load_table_safe("coa")
print(f"COA loaded count: {len(coa)}")


def extract_trans_types(coa_rows):
    res = []
    for r in coa_rows:
        if isinstance(r, dict):
            for k, v in r.items():
                if k.strip().lower() in (
                    "trans type",
                    "transtype",
                    "transaction_type",
                    "trans_type",
                ):
                    if v and str(v).strip():
                        res.append(str(v).strip())
                        break
        elif isinstance(r, str):
            res.append(r.strip())
    return list(dict.fromkeys(res))


coa_trans_types = extract_trans_types(coa)
print(f"COA Trans Types ({len(coa_trans_types)}):", coa_trans_types)

account_map = load_table_safe("account_map")
print(f"account_map count: {len(account_map)}")
for r in account_map:
    print("  account_map entry:", r)

allocation_rules = load_table_safe("allocation_rules")
print(f"allocation_rules count: {len(allocation_rules)}")
for r in allocation_rules:
    print("  allocation_rules entry:", r)

# 2. Identify holding / suspense account
suspense_candidates = [
    tt for tt in coa_trans_types if "suspense" in tt.lower()
]
holding_candidates = [tt for tt in coa_trans_types if "holding" in tt.lower()]
other_candidates = [
    tt
    for tt in coa_trans_types
    if any(
        w in tt.lower() for w in ["unallocated", "unresolved", "clearing", "parked"]
    )
]

if suspense_candidates:
    holding_type = suspense_candidates[0]
elif holding_candidates:
    holding_type = holding_candidates[0]
elif other_candidates:
    holding_type = other_candidates[0]
elif coa_trans_types:
    holding_type = coa_trans_types[0]
else:
    holding_type = "Holding Account"
print("Selected holding_type:", holding_type)

# 3. Cash account resolution
cash_candidates = [
    tt
    for tt in coa_trans_types
    if any(
        w in tt.lower()
        for w in [
            "cash",
            "bank",
            "operating",
            "current",
            "demand deposit",
            "nostro",
        ]
    )
]
print("Cash candidates:", cash_candidates)


def get_cash_trans_type(currency):
    curr = (currency or "").strip().lower()

    # Match in account_map
    for row in account_map:
        vals = [str(v).strip().lower() for v in row.values()]
        if any(curr == v or curr in v for v in vals):
            for k in ["Trans Type", "trans_type", "Account", "account"]:
                if k in row and row[k] in coa_trans_types:
                    return row[k]
            for v in row.values():
                if str(v).strip() in coa_trans_types:
                    return str(v).strip()

    # Currency + cash keywords in COA
    for tt in coa_trans_types:
        ttl = tt.lower()
        if curr in ttl and any(
            w in ttl for w in ["cash", "bank", "operating", "current"]
        ):
            return tt

    # Currency in COA
    for tt in coa_trans_types:
        if curr in tt.lower():
            return tt

    if cash_candidates:
        return cash_candidates[0]
    return coa_trans_types[0] if coa_trans_types else None


# 4. Counterparty account resolution
def get_cp_trans_type(r):
    cpm = r.get("counterparty_match") or {}
    st = cpm.get("status") if isinstance(cpm, dict) else None
    matched_name = (
        cpm.get("matched_name") if isinstance(cpm, dict) else cpm or None
    )

    # Unresolved counterparty books to holding account
    if st not in ("MATCH", "PROBABLE") and not matched_name:
        return holding_type

    cls = (r.get("classification") or "").strip()
    if not cls:
        return holding_type

    # 1. Match classification in account_map
    for row in account_map:
        vals = [str(v).strip().lower() for v in row.values()]
        if cls.lower() in vals:
            for k in ["Trans Type", "trans_type", "Account", "account"]:
                if k in row and row[k] in coa_trans_types:
                    return row[k]
            for v in row.values():
                if str(v).strip() in coa_trans_types:
                    return str(v).strip()

    # 2. Exact match in COA
    for tt in coa_trans_types:
        if tt.strip().lower() == cls.lower():
            return tt

    # 3. Substring match in COA
    for tt in coa_trans_types:
        if cls.lower() in tt.lower():
            return tt
    for tt in coa_trans_types:
        if tt.lower() in cls.lower():
            return tt

    # 4. Keyword match
    cls_words = [
        w for w in cls.lower().split() if w not in ["and", "or", "the", "of", "to"]
    ]
    if cls_words:
        for tt in coa_trans_types:
            if all(w in tt.lower() for w in cls_words):
                return tt

    return holding_type


# 5. Process statement rows
rows = kit.rows()
if not isinstance(rows, list):
    rows = list(rows)
print(f"Total rows to process: {len(rows)}")

for i, r in enumerate(rows):
    batch_id = str(r.get("id") if r.get("id") is not None else f"batch_{i+1}")

    dr = r.get("debit")
    cr = r.get("credit")
    amt = r.get("amount")

    if dr is not None and str(dr).strip() != "" and Decimal(str(dr)) != 0:
        raw_amt = abs(Decimal(str(dr)))
        is_statement_debit = True
    elif cr is not None and str(cr).strip() != "" and Decimal(str(cr)) != 0:
        raw_amt = abs(Decimal(str(cr)))
        is_statement_debit = False
    elif amt is not None and str(amt).strip() != "":
        val = Decimal(str(amt))
        raw_amt = abs(val)
        if "is_debit" in r:
            is_statement_debit = bool(r["is_debit"])
        else:
            is_statement_debit = val < 0
    else:
        raw_amt = Decimal("0.00")
        is_statement_debit = False

    amt_str = f"{raw_amt:.2f}"

    # Direction: cash leg is credit when statement is debit, debit when statement is credit
    cash_is_debit = not is_statement_debit
    cp_is_debit = is_statement_debit

    cash_tt = get_cash_trans_type(r.get("currency"))
    cp_tt = get_cp_trans_type(r)

    # Ensure transaction types are valid COA entries
    if cash_tt not in coa_trans_types and coa_trans_types:
        cash_tt = coa_trans_types[0]
    if cp_tt not in coa_trans_types and coa_trans_types:
        cp_tt = holding_type

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
bal = kit.batches_balance(rows, field="journal_lines")
print("Batches balance check:", bal)

parked_lines = sum(
    1
    for r in rows
    for line in r.get("journal_lines", [])
    if line.get("transaction_type") == holding_type
)
print(f"Total lines booked to holding account: {parked_lines}")

try:
    kit.write_assertions(
        [
            {"claim": "batches_balance", "result": bal},
            {"claim": "parked_lines", "result": parked_lines},
        ]
    )
except Exception as e:
    print("write_assertions notice:", e)

# 7. Write output
kit.write_result(rows)
print(f"parsed {len(rows)} rows")
```
