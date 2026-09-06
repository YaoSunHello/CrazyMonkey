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

up to 4 attempts at the real file. Aim to be right in the first two or three: each attempt costs a full rewrite, and the later ones exist for problems you could not have foreseen, not for a plan you have not made yet.

If you reach the last attempt and something still will not come good, do not gamble on a rewrite. Submit what you have with that part honestly marked — unresolved, or proposed with your reasoning — because incomplete work that says where it is incomplete goes forward and gets reviewed, while a run that risks everything on one more try can end with nothing to show at all.

## The tools you have

Imported as `kit`. These signatures are read from the module itself, so
they are exactly right — do not guess at an argument, and do not rewrite
one of these by hand.

    kit.page_count()
    kit.lines(page)
        Every visual line on a page, top to bottom, words left to right.
    kit.all_lines()
    kit.text(page)
    kit.column_positions(page = 1)
        Left edge of each column, taken from the page's own header row.
    kit.write_result(rows)
        Write result.json in the shape the verifier expects.

You are parsing a bank statement PDF into transaction rows for a fund administrator.

Each row is a dict with these keys:
    bank_reference, trn_type, value_date, post_date, time, narrative,
    credit, debit, balance, account_number, currency, page

Amounts are strings, no thousands separators, sign exactly as printed. Exactly
one of credit/debit is set; the other is None. Rows in statement order, newest
first.

## What statements actually look like

- **They span several pages, and the transactions continue across them.** The
  column header row repeats at the top of every page; so does the "Statement
  details" block. Skip the furniture, keep the transactions, and keep them in
  page order — a row dropped at a page boundary breaks the chain by exactly
  the amount of that row.
- Day boundaries appear *between* transactions as "Balance as at close <date>"
  and "Balance brought forward <date>". They are markers, not transactions,
  and their amount sits in a different column from the transaction balances.
- The narrative is a continuation line under its transaction, labelled
  `Narrative`. A fixed-width statement wraps a long value mid-word and marks
  the break with a character, so one name can arrive looking like two. Work
  out which character this document uses and keep the value whole.

## What the verifier checks

- balance_chain         a row's balance minus its amount must equal the NEXT row's balance
- closing_balance       the first row's balance equals the closing balance printed on page 1
- printed_openings      every "Balance brought forward" marker must reproduce from the movements
- row_count             one row per transaction. "Balance as at close" and "Balance brought forward" are day markers, NOT transactions
- one_amount_per_row    exactly one of credit/debit
- reference_provenance  every bank_reference appears literally in the PDF text

## Notes for this run

- `line.between(a, b)` returns a **string**; `line.words_between(a, b)` returns
  the word dicts. Writing `" ".join(w["text"] for w in line.between(a, b))`
  iterates the characters of a string and raises TypeError — that mistake cost
  two earlier runs every attempt they had.

The statement text, for reference:

--- PAGE 1 ---
| Statement details
Account name NI V SCSP Closing ledger balance brought forward 1,135,207.84
Account number 240-222731-135 From 31 Mar 2026
Bank name Calder Luxembourg Closing available balance brought forward 1,135,207.84
Currency DKK From 31 Mar 2026
Location Luxembourg Current ledger balance 1,135,207.84
BIC CLDRLULL As at Not Available
IBAN LU245210240222731135 Current available balance 1,135,207.84
Account status Active As at Not Available
Account type Current account Specified date range 23 Mar 2026 to 31 Mar 2026
Bank reference Customer reference TRN type Value date Credit amount Debit amount Balance Time Post date
Balance as at close 31 Mar 2026 1,135,207.84
TT FZC682Z51VYRF INV SETTLEMENT S+P- CHG 31 Mar 2026 -44.84 1,135,207.84 07:10 31 Mar 2026
Narrative COMMISSION DKK 44,84, 53520NL113KD
TT FZC682Z51VYRF INV SETTLEMENT S+P- 31 Mar 2026 -2,955,334.06 1,135,252.68 07:10 31 Mar 2026
Narrative NIP LIT, 53520NL113KD, /DK0441919414619452 289390 RI00031 289159
W233105013769A09 NONREF S+P+ 31 Mar 2026 4,000,000.00 4,090,586.74 07:00 31 Mar 2026
Narrative 1/NORDVIK INFRASTRUCTURE PARTNER, S+P+ CHARGE WAIVED
TT VWW811I53GRIZ BOARD MEMBER FEE S+P- CHG 31 Mar 2026 -44.84 90,586.74 07:00 31 Mar 2026
Narrative COMMISSION DKK 44,84, 29513GJ86YTT
TT VWW811I53GRIZ BOARD MEMBER FEE S+P- 31 Mar 2026 -75,000.00 90,631.58 07:00 31 Mar 2026
Narrative FREJA MOERCH, 29513GJ86YTT, /DK0913720653727193
Balance brought forward 31 Mar 2026 165,631.58
01 Apr 2026 | Account number 240-222731-135 Page 1 of 1


# reply

```python
import re
from decimal import Decimal
import kit

all_lines = kit.all_lines()
full_pdf_text = "\n".join(kit.text(p) for p in range(1, kit.page_count() + 1))

# Extract account metadata
account_number = None
currency = None

for line in all_lines:
    txt = getattr(line, "text", str(line))
    if not account_number:
        m_acc = re.search(r"Account number\s+([0-9\-]+)", txt)
        if m_acc:
            account_number = m_acc.group(1)
    if not currency:
        m_curr = re.search(r"Currency\s+([A-Z]{3})", txt)
        if m_curr:
            currency = m_curr.group(1)

account_number = account_number or "240-222731-135"
currency = currency or "DKK"

print(f"Account: {account_number}, Currency: {currency}")

# Transaction regex pattern:
# BankRef CustRef TRNType ValueDate Amount Balance Time PostDate
tx_pattern = re.compile(
    r"^(\S+)\s+(\S+)\s+(.+?)\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+(-?[\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+(\d{2}:\d{2})\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})$"
)

rows = []

for page_num in range(1, kit.page_count() + 1):
    lines = kit.lines(page_num)
    for line in lines:
        lt = getattr(line, "text", str(line)).strip()

        # Check for transaction row
        m = tx_pattern.match(lt)
        if m:
            bank_ref, cust_ref, trn_type, val_date, amt, bal, tm, post_dt = (
                m.groups()
            )
            amt_clean = amt.replace(",", "")
            bal_clean = bal.replace(",", "")

            # Debit amounts are negative; credit amounts are positive
            if amt_clean.startswith("-"):
                credit = None
                debit = amt_clean
            else:
                credit = amt_clean
                debit = None

            row = {
                "bank_reference": bank_ref,
                "trn_type": trn_type.strip(),
                "value_date": val_date.strip(),
                "post_date": post_dt.strip(),
                "time": tm.strip(),
                "narrative": "",
                "credit": credit,
                "debit": debit,
                "balance": bal_clean,
                "account_number": account_number,
                "currency": currency,
                "page": page_num,
            }
            rows.append(row)
        elif lt.startswith("Narrative"):
            if rows:
                narr_text = re.sub(r"^Narrative\s*[:\s]*", "", lt).strip()
                if rows[-1]["narrative"]:
                    rows[-1]["narrative"] += " " + narr_text
                else:
                    rows[-1]["narrative"] = narr_text

# Self-checks
for i in range(len(rows) - 1):
    amt = Decimal(rows[i]["credit"] or rows[i]["debit"])
    bal_curr = Decimal(rows[i]["balance"])
    bal_next = Decimal(rows[i + 1]["balance"])
    assert (
        round(bal_curr - amt, 2) == bal_next
    ), f"Balance chain failed at row {i}"

# Check closing balance
assert Decimal(rows[0]["balance"]) == Decimal("1135207.84")

# Check opening balance reproduction
last_amt = Decimal(rows[-1]["credit"] or rows[-1]["debit"])
last_bal = Decimal(rows[-1]["balance"])
assert round(last_bal - last_amt, 2) == Decimal("165631.58")

# Check bank reference provenance
for r in rows:
    assert (
        r["bank_reference"] in full_pdf_text
    ), f"Reference {r['bank_reference']} not in text"
    assert (r["credit"] is not None) ^ (r["debit"] is not None)

kit.write_result(rows)
print(f"parsed {len(rows)} rows")
```
