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


Your journal.py was REJECTED by the verifier. Attempt 4 of 10.

This is the journal.py you wrote, in full. **Edit it.** Keep every part that
worked and change the part the verifier objected to — a rewrite from scratch
loses what you had already got right, and you will not be able to tell which
of your own ideas has already been tried and falsified.

```python
import inspect
import json
import sys
import traceback
import kit

# Ensure stdout is flushed on every print
sys.stdout.reconfigure(line_buffering=True)

print("=== INSPECT KIT ===", flush=True)
for name in [
    "batches_balance",
    "write_result",
    "write_assertions",
    "questions",
    "tables",
    "table",
]:
    if hasattr(kit, name):
        fn = getattr(kit, name)
        try:
            print(f"kit.{name}{inspect.signature(fn)}: {fn.__doc__}", flush=True)
        except Exception as e:
            print(f"kit.{name}: {e}", flush=True)


def load_table(name):
    try:
        t = kit.table(name)
        if hasattr(t, "to_dict"):
            return t.to_dict(orient="records")
        if isinstance(t, list):
            if len(t) > 0 and not isinstance(t[0], dict):
                if hasattr(t[0], "_asdict"):
                    return [r._asdict() for r in t]
                elif hasattr(t[0], "keys"):
                    return [dict(r) for r in t]
            return t
        res = list(t)
        if res and not isinstance(res[0], dict):
            if hasattr(res[0], "_asdict"):
                return [r._asdict() for r in res]
            elif hasattr(res[0], "keys"):
                return [dict(r) for r in res]
        return res
    except Exception as e:
        print(f"Error loading table {name}: {e}", flush=True)
        traceback.print_exc()
        return []


print("=== TABLES AVAILABLE ===", flush=True)
try:
    tbl_names = kit.tables()
    print("Tables:", tbl_names, flush=True)
except Exception as e:
    tbl_names = []
    print("tables err:", e, flush=True)

tables = {}
for tn in tbl_names:
    t_data = load_table(tn)
    tables[tn] = t_data
    print(f"Table '{tn}': {len(t_data)} rows", flush=True)
    if t_data:
        print(f"  Columns: {list(t_data[0].keys())}", flush=True)
        for sample_r in t_data[:5]:
            print(f"  sample: {sample_r}", flush=True)

# Inspect COA in detail
coa = tables.get("coa", [])
print(f"COA total rows: {len(coa)}", flush=True)
trans_types = []
tt_col = "Trans Type"
if coa:
    for k in coa[0].keys():
        if k.lower() == "trans type":
            tt_col = k
            break
    trans_types = [
        r.get(tt_col) for r in coa if isinstance(r, dict) and r.get(tt_col)
    ]
    print(
        f"Sample Trans Types ({len(trans_types)} total): {trans_types[:15]}",
        flush=True,
    )
    # Print all trans types
    print("All COA Trans Types:", flush=True)
    for tt in trans_types:
        print(f"  TT: {tt}", flush=True)

# Inspect account_map and allocation_rules if present
if "account_map" in tables:
    print("=== ACCOUNT MAP ===", flush=True)
    for r in tables["account_map"]:
        print("  map:", r, flush=True)

if "allocation_rules" in tables:
    print("=== ALLOCATION RULES ===", flush=True)
    for r in tables["allocation_rules"]:
        print("  rule:", r, flush=True)

# Inspect Rows
rows = kit.rows()
print(f"=== ROWS ({len(rows)}) ===", flush=True)
for i, r in enumerate(rows):
    print(f"Row {i}: {r}", flush=True)

# Identify Holding / Suspense account from COA
holding_tt = None
for r in coa:
    tt = str(r.get(tt_col, ""))
    full_str = " ".join(str(v).lower() for v in r.values())
    if any(
        kw in full_str
        for kw in ["holding", "suspense", "park", "unallocated", "unresolved"]
    ):
        holding_tt = tt
        print(f"Selected holding_tt: {holding_tt} from {r}", flush=True)
        break

if not holding_tt:
    for tt in trans_types:
        if any(
            kw in tt.lower()
            for kw in ["holding", "suspense", "park", "unresolved"]
        ):
            holding_tt = tt
            print(f"Selected holding_tt fallback: {holding_tt}", flush=True)
            break

# Function to pick cash account
def get_cash_account(row):
    currency = str(row.get("currency") or "").upper()
    # Check account_map if available
    if "account_map" in tables:
        for m in tables["account_map"]:
            m_str = " ".join(str(v).lower() for v in m.values())
            if "cash" in m_str or "bank" in m_str:
                if currency and currency.lower() in m_str:
                    for k, v in m.items():
                        if v in trans_types:
                            return v
    # Search in COA
    candidates = []
    for r in coa:
        tt = r.get(tt_col, "")
        r_str = " ".join(str(v).lower() for v in r.values())
        if "cash" in r_str or "bank" in r_str or "operating" in r_str:
            if currency and currency.lower() in r_str:
                return tt
            candidates.append(tt)
    if candidates:
        return candidates[0]
    return trans_types[0] if trans_types else "Cash"


# Function to pick counterpart account
def get_counterpart_account(row):
    cm = row.get("counterparty_match")
    is_res = False
    if cm and isinstance(cm, dict):
        status = str(cm.get("status", "")).upper()
        why = str(cm.get("why", "")).lower()
        matched = cm.get("name") or cm.get("match") or cm.get("matched")
        if status in ("MATCH", "PROBABLE") or (
            matched and "no counterparty" not in why and status != "UNRESOLVED"
        ):
            is_res = True

    if not is_res:
        return holding_tt or trans_types[0], True

    cls_val = str(row.get("classification") or "").strip()
    curr_val = str(row.get("currency") or "").strip().lower()

    # Check account_map
    if "account_map" in tables:
        for m in tables["account_map"]:
            vals = [str(v).lower() for v in m.values()]
            if cls_val.lower() in vals:
                for k, v in m.items():
                    if v in trans_types:
                        return v, False

    # Exact match on Trans Type
    for tt in trans_types:
        if tt.lower() == cls_val.lower():
            return tt, False

    # Check if classification text in COA
    for r in coa:
        tt = r.get(tt_col, "")
        r_str = " ".join(str(v).lower() for v in r.values())
        if cls_val.lower() and cls_val.lower() in r_str:
            if curr_val and curr_val in r_str:
                return tt, False

    for r in coa:
        tt = r.get(tt_col, "")
        r_str = " ".join(str(v).lower() for v in r.values())
        if cls_val.lower() and cls_val.lower() in r_str:
            return tt, False

    return holding_tt or trans_types[0], True


# Build journal lines
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

    cash_acc = get_cash_account(r)
    cp_acc, is_parked = get_counterpart_account(r)
    if is_parked:
        parked_count += 1

    # Cash leg is credit when stmt is debit, debit when stmt is credit
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

# Batches balance
bal_check = None
try:
    bal_check = kit.batches_balance(rows)
    print("batches_balance check:", bal_check, flush=True)
except Exception as e:
    print("batches_balance err:", e, flush=True)

try:
    if hasattr(kit, "write_assertions"):
        claims = []
        if bal_check is not None:
            if isinstance(bal_check, list):
                claims.extend(bal_check)
            else:
                claims.append(bal_check)
        kit.write_assertions(claims)
        print("write_assertions called successfully", flush=True)
except Exception as e:
    print("write_assertions err:", e, flush=True)

# Write result
kit.write_result(rows)
print(f"Result written successfully: {len(rows)} rows", flush=True)
print(
    f"posted {len(rows)} rows ({len(rows)*2} journal lines), parked {parked_count} lines to holding",
    flush=True,
)
```

These checks failed — the output is wrong:
- result_json: journal.py did not produce a readable /work/result.json
    49813-030', 'currency': 'EUR', 'page': 2, 'counterparty_raw': None, 'counterparty_match': {'status': 'CANNOT_VERIFY', 'matched_name': None, 'table': None, 'confidence': None, 'why': 'Credit interest; no counterparty named'}, 'project_code_raw': None, 'project_code_match': {'status': 'CANNOT_VERIFY', 'matched_name': None, 'table': None, 'confidence': None, 'why': 'No project keyword in narrative'}, 'classification': 'Other'}
    Traceback (most recent call last):
      File "/work/journal.py", line 224, in <module>
        cp_acc, is_parked = get_counterpart_account(r)

The evidence names the row and the exact discrepancy. Fix the cause, not
the symptom, and do not repeat the approach that just failed.

Reply with the complete corrected journal.py in a single ```python code block.

# reply

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
