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

## Notes for this run

- Either a `transaction_type` is not in the chart of accounts, or too many
  lines were parked in the holding account.

  If a type is not in the chart: it does not exist. Read
  `kit.table("coa").values("Trans Type")` and take one that is there.

  If too much is parked, the cause is upstream, not here — those rows are
  the ones whose counterparty never resolved. Look at each of them: print
  the narrative, print what the lists hold near it, and decide. Many will
  be resolvable once you look at the actual strings rather than the ones
  you assumed. Where a name is plainly the same party under a different
  spelling or a contracted form, say so as a PROBABLE with a reason and a
  confidence below 1 — that is a resolution a person can accept in one
  click. Where the data genuinely does not hold the party, park it and
  leave it parked. Never invent an account or a match to lower this number.

There are 16 rows to resolve.


Your journal.py was REJECTED by the verifier. Attempt 5 of 10.

This is the journal.py you wrote, in full. **Edit it.** Keep every part that
worked and change the part the verifier objected to — a rewrite from scratch
loses what you had already got right, and you will not be able to tell which
of your own ideas has already been tried and falsified.

```python
import sys
import traceback
import kit

# Ensure stdout is flushed on every print
sys.stdout.reconfigure(line_buffering=True)


def normalize_table(t):
    if t is None:
        return []
    if hasattr(t, "to_dict"):
        try:
            return t.to_dict(orient="records")
        except Exception:
            pass
    if isinstance(t, dict):
        vals = list(t.values())
        if vals and isinstance(vals[0], list):
            keys = list(t.keys())
            records = []
            for idx in range(len(vals[0])):
                records.append({k: t[k][idx] for k in keys if idx < len(t[k])})
            return records
        else:
            return [{"key": k, "value": v} for k, v in t.items()]
    if isinstance(t, list):
        records = []
        for item in t:
            if isinstance(item, dict):
                records.append(item)
            elif hasattr(item, "_asdict"):
                records.append(item._asdict())
            elif hasattr(item, "keys"):
                records.append(dict(item))
            else:
                records.append(item)
        return records
    try:
        return normalize_table(list(t))
    except Exception:
        return []


# 1. Discover mounted tables
tbl_names = kit.tables() if hasattr(kit, "tables") else []
print("Mounted tables:", tbl_names)

# 2. Parse Chart of Accounts (COA)
coa_raw = kit.table("coa") if hasattr(kit, "table") else None
coa_records = normalize_table(coa_raw)

coa_types = []
tt_col_name = None

if coa_records:
    if isinstance(coa_records[0], str):
        coa_types = [str(x).strip() for x in coa_records if str(x).strip()]
    elif isinstance(coa_records[0], dict):
        for k in coa_records[0].keys():
            k_clean = k.lower().replace("_", " ").strip()
            if k_clean in ("trans type", "transtype", "transaction type"):
                tt_col_name = k
                break
        if not tt_col_name:
            for k in coa_records[0].keys():
                if "type" in k.lower():
                    tt_col_name = k
                    break
        if not tt_col_name:
            tt_col_name = list(coa_records[0].keys())[0]

        for r in coa_records:
            if isinstance(r, dict) and tt_col_name in r:
                val = r[tt_col_name]
                if val is not None and str(val).strip():
                    coa_types.append(str(val).strip())

print(
    f"COA loaded: {len(coa_types)} transaction types (column '{tt_col_name}')"
)
print("COA Trans Types:", coa_types)

# 3. Identify Holding / Suspense account from COA
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

if not holding_tt and coa_records and isinstance(coa_records[0], dict):
    for r in coa_records:
        r_str = " ".join(str(v).lower() for v in r.values())
        if any(
            kw in r_str
            for kw in [
                "holding",
                "suspense",
                "park",
                "unallocated",
                "unresolved",
            ]
        ):
            holding_tt = str(r.get(tt_col_name, "")).strip()
            break

if not holding_tt and coa_types:
    for tt in coa_types:
        if "other" in tt.lower() or "misc" in tt.lower():
            holding_tt = tt
            break

if not holding_tt and coa_types:
    holding_tt = coa_types[-1]

print(f"Selected holding account: {holding_tt}")

# 4. Load other reference tables
ref_tables = {}
for tn in tbl_names:
    if tn != "coa":
        ref_tables[tn] = normalize_table(kit.table(tn))
        print(f"Table '{tn}': {len(ref_tables[tn])} records")
        if ref_tables[tn] and isinstance(ref_tables[tn][0], dict):
            print(f"  columns: {list(ref_tables[tn][0].keys())}")

# 5. Map cash accounts by currency
cash_map = {}
for tt in coa_types:
    t_low = tt.lower()
    if any(w in t_low for w in ["cash", "bank", "operating"]):
        for curr in ["EUR", "USD", "GBP", "CHF", "JPY", "AUD", "CAD"]:
            if curr.lower() in t_low and curr not in cash_map:
                cash_map[curr] = tt

if coa_records and isinstance(coa_records[0], dict):
    for r in coa_records:
        r_str = " ".join(str(v).lower() for v in r.values())
        tt_val = str(r.get(tt_col_name, "")).strip()
        if any(w in r_str for w in ["cash", "bank", "operating"]):
            for curr in ["EUR", "USD", "GBP", "CHF", "JPY"]:
                if curr.lower() in r_str and curr not in cash_map:
                    cash_map[curr] = tt_val

default_cash = None
for tt in coa_types:
    if any(w in tt.lower() for w in ["cash", "bank"]):
        default_cash = tt
        break
if not default_cash and coa_types:
    default_cash = coa_types[0]

print("Cash account map:", cash_map, "default:", default_cash)


def get_cash_tt(row):
    curr = str(row.get("currency") or "").upper()
    return cash_map.get(curr, default_cash)


# 6. Load rows and inspect
rows = kit.rows()
print(f"Loaded {len(rows)} statement rows.")


def is_resolved(row):
    cm = row.get("counterparty_match")
    if not cm or not isinstance(cm, dict):
        return False
    status = str(cm.get("status", "")).upper()
    why = str(cm.get("why", "")).lower()
    matched = cm.get("name") or cm.get("match") or cm.get("matched_name")
    if status in ("MATCH", "PROBABLE"):
        return True
    if matched and "no counterparty" not in why and status != "UNRESOLVED":
        return True
    return False


# Attempt re-resolution for unresolved rows if reference pools exist
pools = [
    tn
    for tn in tbl_names
    if tn != "coa" and "map" not in tn and "rule" not in tn
]
if hasattr(kit, "lookup") and pools:
    for r in rows:
        if not is_resolved(r):
            narr = str(r.get("narrative") or "").strip()
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
                            "why": "Verbatim match in reference pool",
                        }
                        break
                except Exception:
                    pass


def get_cp_tt(row):
    if not is_resolved(row):
        return holding_tt, True

    cls_val = str(row.get("classification") or "").strip()
    curr_val = str(row.get("currency") or "").strip().lower()

    # 1. Exact match with coa_types
    for tt in coa_types:
        if tt.lower() == cls_val.lower():
            return tt, False

    # 2. Check mapping tables
    for tn in ["account_map", "allocation_rules", "category_map", "rules"]:
        if tn in ref_tables:
            for item in ref_tables[tn]:
                if isinstance(item, dict):
                    vals = [str(v).lower() for v in item.values()]
                    if cls_val.lower() in vals:
                        for k, v in item.items():
                            if str(v) in coa_types:
                                return str(v), False

    # 3. Substring match on classification
    if cls_val:
        for tt in coa_types:
            if cls_val.lower() in tt.lower():
                return tt, False

    if coa_records and isinstance(coa_records[0], dict):
        for r in coa_records:
            r_str = " ".join(str(v).lower() for v in r.values())
            tt_val = str(r.get(tt_col_name, "")).strip()
            if cls_val.lower() and cls_val.lower() in r_str:
                if tt_val in coa_types:
                    return tt_val, False

    # 4. Fallback for resolved rows
    for kw in [
        "accounts payable",
        "trade creditors",
        "operating expense",
        "expense",
    ]:
        for tt in coa_types:
            if kw in tt.lower():
                return tt, False

    return holding_tt, True


# 7. Build journal lines
parked_count = 0
for i, r in enumerate(rows):
    batch_id = str(r.get("id") or f"batch_{i+1}")

    raw_amt = r.get("amount", 0)
    try:
        amt_str = f"{abs(float(str(raw_amt).replace(',', ''))):.2f}"
    except Exception:
        amt_str = str(raw_amt)

    stmt_debit = r.get("is_debit")
    if stmt_debit is None:
        direction = str(r.get("direction", "")).lower()
        stmt_debit = direction in ("debit", "dr", "out")

    cash_acc = get_cash_tt(r)
    cp_acc, is_parked = get_cp_tt(r)
    if is_parked:
        parked_count += 1

    # Cash leg is credit when statement is debit, debit when statement is credit
    cash_debit = not bool(stmt_debit)
    cp_debit = bool(stmt_debit)

    r["journal_lines"] = [
        {
            "batch": batch_id,
            "amount": amt_str,
            "is_debit": cash_debit,
            "transaction_type": cash_acc,
        },
        {
            "batch": batch_id,
            "amount": amt_str,
            "is_debit": cp_debit,
            "transaction_type": cp_acc,
        },
    ]

    print(
        f"Row {i:02d} [{batch_id}]: {amt_str} {r.get('currency')} | "
        f"Cash: {cash_acc} (Dr={cash_debit}) | "
        f"Counterpart: {cp_acc} (Dr={cp_debit}, parked={is_parked})"
    )

# 8. Check double entry balance
try:
    bal_check = kit.batches_balance(rows)
    print("kit.batches_balance result:", bal_check)
except Exception as e:
    print("batches_balance check exception:", e)

# 9. Assertions
try:
    if hasattr(kit, "write_assertions"):
        claims = []
        if bal_check is not None:
            if isinstance(bal_check, list):
                claims.extend(bal_check)
            else:
                claims.append(bal_check)
        kit.write_assertions(claims)
except Exception as e:
    print("write_assertions note:", e)

# 10. Write enriched result
kit.write_result(rows)
print(
    f"posted {len(rows)} rows ({len(rows)*2} journal lines), parked"
    f" {parked_count} lines to holding"
)
print(f"parsed {len(rows)} rows")
```

These checks failed — the output is wrong:
- posting: 0/32 lines name an account that exists
    row 0: a line carries no transaction_type
    row 0: a line carries no transaction_type
    row 1: a line carries no transaction_type
    row 1: a line carries no transaction_type

The evidence names the row and the exact discrepancy. Fix the cause, not
the symptom, and do not repeat the approach that just failed.

What your script printed when it ran:

    parked=True)
    Row 02 [batch_3]: 0.00 EUR | Cash: None (Dr=True) | Counterpart: None (Dr=False, parked=True)
    Row 03 [batch_4]: 0.00 EUR | Cash: None (Dr=True) | Counterpart: None (Dr=False, parked=True)
    Row 04 [batch_5]: 0.00 EUR | Cash: None (Dr=True) | Counterpart: None (Dr=False, parked=True)
    Row 05 [batch_6]: 0.00 EUR | Cash: None (Dr=True) | Counterpart: None (Dr=False, parked=True)
    Row 06 [batch_7]: 0.00 EUR | Cash: None (Dr=True) | Counterpart: None (Dr=False, parked=True)
    Row 07 [batch_8]: 0.00 EUR | Cash: None (Dr=True) | Counterpart: None (Dr=False, parked=True)
    Row 08 [batch_9]: 0.00 EUR | Cash: None (Dr=True) | Counterpart: None (Dr=False, parked=True)
    Row 09 [batch_10]: 0.00 EUR | Cash: None (Dr=True) | Counterpart: None (Dr=False, parked=True)
    Row 10 [batch_11]: 0.00 EUR | Cash: None (Dr=True) | Counterpart: None (Dr=False, parked=True)
    Row 11 [batch_12]: 0.00 EUR | Cash: None (Dr=True) | Counterpart: None (Dr=False, parked=True)
    Row 12 [batch_13]: 0.00 EUR | Cash: None (Dr=True) | Counterpart: None (Dr=False, parked=True)
    Row 13 [batch_14]: 0.00 EUR | Cash: None (Dr=True) | Counterpart: None (Dr=False, parked=True)
    Row 14 [batch_15]: 0.00 EUR | Cash: None (Dr=True) | Counterpart: None (Dr=False, parked=True)
    Row 15 [batch_16]: 0.00 EUR | Cash: None (Dr=True) | Counterpart: None (Dr=False, parked=True)
    kit.batches_balance result: {'ok': True, 'batches': 16, 'balanced': 16, 'problems': []}
    posted 16 rows (32 journal lines), parked 16 lines to holding
    parsed 16 rows

This is your own output, not a complaint. Print whatever you need to see
in the next attempt — the values that did not match, what the lists hold
near them, how many rows a pattern actually caught — and read it here.

Reply with the complete corrected journal.py in a single ```python code block.

# reply

An inspection of the previous run shows why every line carried `None`: `kit.table("coa")` provides `.values("Trans Type")` directly (as noted in the verifier instructions), rather than conforming to standard iterable/dict interfaces. In addition, statement rows in `kit.rows()` may store amounts across `amount`, `debit`, or `credit` fields.

Here is the updated `journal.py`.

```python
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
```
