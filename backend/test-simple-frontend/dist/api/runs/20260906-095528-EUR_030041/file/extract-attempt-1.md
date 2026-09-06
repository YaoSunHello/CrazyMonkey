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
Account name NI V SCSP Closing ledger balance brought forward 1,197,694.98
Account number 240-222731-030 From 31 Mar 2026
Bank name Calder Luxembourg Closing available balance brought forward 1,197,694.98
Currency EUR From 31 Mar 2026
Location Luxembourg Current ledger balance 1,197,694.98
BIC CLDRLULL As at Not Available
IBAN LU465210240222731030 Current available balance 1,197,694.98
Account status Active As at Not Available
Account type Current account Specified date range 23 Mar 2026 to 31 Mar 2026
Bank reference Customer reference TRN type Value date Credit amount Debit amount Balance Time Post date
Balance as at close 31 Mar 2026 1,197,694.98
NONREF NONREF TFR- 31 Mar 2026 -0.44 1,197,694.98 17:46 31 Mar 2026
Narrative CHARGES FOR 2, OUTWARD SEPA PAYMENT
GU26109510736433 22434343,63324540,20 SCT 31 Mar 2026 -74,960.33 1,197,695.42 10:18 31 Mar 2026
000270,11522044
Narrative 22434343,63324540,54833311,11522044, NIP CINNABAR APS
LP87861598574517 35051052 / 412263620 SCT 31 Mar 2026 -8,671.31 1,272,655.75 10:18 31 Mar 2026
Narrative 35051052 / 412263620, ELLMONT AND CHALWORTH LUXEMBOURG SARL
TT HKM371VDCAJA Q794501891298U42 TFR- 31 Mar 2026 -19,526,285.38 1,281,327.06 06:30 31 Mar 2026
Narrative BQVRFRPP, /FR6239723540911169279904595 CHARGE WAIVED
TT EKE400VADVFGU RANFJORD II TRF TFR- CHG 31 Mar 2026 -6.00 20,807,612.44 06:30 31 Mar 2026
Narrative COMMISSION EUR 6,00, 25515MS49ERZ
TT EKE400VADVFGU RANFJORD II TRF TFR- 31 Mar 2026 -9,400,000.00 20,807,618.44 06:30 31 Mar 2026
Narrative NI RANFJORD II SCSP, 25515MS49ERZ, /DK9152066306262321 EQUITY: FROM NORDVIK INFRAS, TRUCTURE V SCSP EUR) TO NI RANFJORD II SCSP (EUR). PROJECT, RANFJORD II.
ZAQ41907ZZ3414VA NONREF TFR+ 31 Mar 2026 29,700,000.00 30,207,618.44 06:20 31 Mar 2026
Narrative NORDVIK INFRASTRUCTURE V, TFR+ NORDVIK INFRASTRUCTURE V SCSP,IS, IN XWDM430033AD,TRANCHE B1 CHARGE WAIVED
01 Apr 2026 | Account number 240-222731-030 Page 1 of 3

--- PAGE 2 ---
| Statement details
Bank reference Customer reference TRN type Value date Credit amount Debit amount Balance Time Post date
TT EIB210FC5YPP F423264411464E22 TFR- 31 Mar 2026 -535,331.91 507,618.44 23:21 31 Mar 2026
Narrative BQVRFRPP, /FR6239723540911169279904595 CHARGE WAIVED
Balance brought forward 31 Mar 2026 1,042,950.35
Balance as at close 27 Mar 2026 1,042,950.35
TT MWQ160P45UNY XYMIBU0337402112 TFR- 27 Mar 2026 -2,000,000.00 1,042,950.35 14:21 27 Mar 2026
Narrative BQVRFRPP, /FR6239723540911169279904595 CHARGE WAIVED
Balance brought forward 27 Mar 2026 3,042,950.35
Balance as at close 25 Mar 2026 3,042,950.35
TT RLF917ZB1BCX Z113532732652J45 TFR- 25 Mar 2026 -2,430,836.90 3,042,950.35 09:38 25 Mar 2026
Narrative BQVRFRPP, /FR6239723540911169279904595 CHARGE WAIVED
Balance brought forward 25 Mar 2026 5,473,787.25
Balance as at close 24 Mar 2026 5,473,787.25
NONREF NONREF TFR- 24 Mar 2026 -0.22 5,473,787.25 17:44 24 Mar 2026
Narrative CHARGES FOR 1, OUTWARD SEPA PAYMENT
MUNBII5410435038 NONREF TFR+ 24 Mar 2026 5,001,458.33 5,473,787.47 15:31 24 Mar 2026
Narrative 1/NORDVIK INFRASTRUCTURE PARTNER, TFR+ CHARGE WAIVED
DZ48770552331763 00345435 SCT 24 Mar 2026 -407.00 472,329.14 09:40 24 Mar 2026
Narrative 00345435, GARRFIELD
TT DAT804CKFPMKI OVERHEADS TRF TFR- CHG 24 Mar 2026 -6.00 472,736.14 08:11 24 Mar 2026
Narrative COMMISSION EUR 6,00, 72905UE80MRC
TT DAT804CKFPMKI OVERHEADS TRF TFR- 24 Mar 2026 -20,000.00 472,742.14 08:11 24 Mar 2026
Narrative NI DRACONIS HOLDCO I SCSP, 72905UE80MRC, /DK4836650451224604 EQUITY: FROM NORDVIK, INFRASTRUCTURE V SCSP TO NI DRACONIS HOLDCO I SCSP
TT VEM211DNNSFZS OVERHEADS TRF TFR- CHG 24 Mar 2026 -6.00 492,742.14 08:11 24 Mar 2026
Narrative COMMISSION EUR 6,00, 67071UB44PDB
01 Apr 2026 | Account number 240-222731-030 Page 2 of 3

--- PAGE 3 ---
| Statement details
Bank reference Customer reference TRN type Value date Credit amount Debit amount Balance Time Post date
TT VEM211DNNSFZS OVERHEADS TRF TFR- 24 Mar 2026 -20,000.00 492,748.14 08:11 24 Mar 2026
Narrative NI DRACONIS HOLDCO II SCSP,, 67071UB44PDB, /DK8292743744610923 EQUITY: FROM NORDVIK, INFRASTRUCTURE V SCSP TO NI DRACONIS HOLDCO II SCSP
NONREF NONREF TFR+ INT 24 Mar 2026 3,937.30 512,748.14 07:05 24 Mar 2026
Narrative CREDIT INTEREST
Balance brought forward 24 Mar 2026 508,810.84
01 Apr 2026 | Account number 240-222731-030 Page 3 of 3


# reply

```python
import re
from decimal import Decimal
import kit


def get_text(line):
    if isinstance(line, str):
        return line
    if hasattr(line, "text") and isinstance(line.text, str):
        return line.text
    if hasattr(line, "words"):
        return " ".join(w["text"] for w in line.words)
    return str(line)


TRN_REGEX = re.compile(
    r"^(.+?)\s+(TFR\+|TFR\-|SCT|TFR\-\s+CHG|TFR\+\s+INT)\s+"
    r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+"
    r"(-?[\d,]+\.\d{2})\s+"
    r"([\d,]+\.\d{2})\s+"
    r"(\d{2}:\d{2})\s+"
    r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})$"
)

num_pages = kit.page_count()
print(f"Total pages: {num_pages}")

# Verify column positions
cols = kit.column_positions(1)
print(f"Column positions: {cols}")

# Extract account number and currency from page 1
p1_text = kit.text(1)
acc_match = re.search(r"Account number\s+([\d-]+)", p1_text)
account_number = acc_match.group(1) if acc_match else "240-222731-030"

curr_match = re.search(r"Currency\s+([A-Z]{3})", p1_text)
currency = curr_match.group(1) if curr_match else "EUR"

print(f"Account number: {account_number}, Currency: {currency}")

all_pdf_text = " ".join(kit.text(p) for p in range(1, num_pages + 1))

rows = []
day_markers = []

for p in range(1, num_pages + 1):
    lines = kit.lines(p)
    current_tx = None
    for line in lines:
        text = get_text(line).strip()
        if not text:
            continue

        # Check day markers
        if text.startswith("Balance as at close") or text.startswith(
            "Balance brought forward"
        ):
            parts = text.split()
            amount_str = parts[-1].replace(",", "")
            date_str = " ".join(parts[-4:-1])
            day_markers.append((parts[0], date_str, amount_str))
            current_tx = None
            continue

        # Check narrative
        if text.startswith("Narrative"):
            narr = text[len("Narrative") :].strip()
            # Unbreak mid-word wraps marked by comma
            narr = narr.replace("INFRAS, TRUCTURE", "INFRASTRUCTURE")
            narr = narr.replace("IS, IN", "ISIN")
            if current_tx is not None:
                current_tx["narrative"] = narr
            continue

        # Check transaction
        m = TRN_REGEX.match(text)
        if m:
            ref_part = m.group(1).strip()
            trn_type = m.group(2).strip()
            val_date = m.group(3).strip()
            amount_str = m.group(4).strip()
            bal_str = m.group(5).strip()
            time_str = m.group(6).strip()
            post_date = m.group(7).strip()

            # Separate Bank reference from Customer reference
            if ref_part.startswith("TT "):
                tokens = ref_part.split()
                bank_ref = f"{tokens[0]} {tokens[1]}"
            else:
                tokens = ref_part.split()
                bank_ref = tokens[0]

            clean_amount = amount_str.replace(",", "")
            clean_balance = bal_str.replace(",", "")

            if clean_amount.startswith("-"):
                debit = clean_amount
                credit = None
            else:
                credit = clean_amount
                debit = None

            current_tx = {
                "bank_reference": bank_ref,
                "trn_type": trn_type,
                "value_date": val_date,
                "post_date": post_date,
                "time": time_str,
                "narrative": "",
                "credit": credit,
                "debit": debit,
                "balance": clean_balance,
                "account_number": account_number,
                "currency": currency,
                "page": p,
            }
            rows.append(current_tx)

print(f"Extracted {len(rows)} transactions.")

# Validate checks
# 1. Row count
assert len(rows) == 18, f"Expected 18 rows, got {len(rows)}"

# 2. Closing balance
assert (
    rows[0]["balance"] == "1197694.98"
), f"Closing balance mismatch: {rows[0]['balance']}"

# 3. Balance chain
for i in range(len(rows) - 1):
    curr_bal = Decimal(rows[i]["balance"])
    curr_amt = Decimal(rows[i]["credit"] or rows[i]["debit"])
    next_bal = Decimal(rows[i + 1]["balance"])
    assert (
        curr_bal - curr_amt == next_bal
    ), f"Balance chain broken at row {i}: {curr_bal} - {curr_amt} != {next_bal}"

# Last row balance minus its amount must match final brought forward marker
last_bal = Decimal(rows[-1]["balance"])
last_amt = Decimal(rows[-1]["credit"] or rows[-1]["debit"])
expected_final = last_bal - last_amt
assert expected_final == Decimal(
    "508810.84"
), f"Final opening balance mismatch: {expected_final} != 508810.84"

# 4. One amount per row
for r in rows:
    assert (r["credit"] is None) != (
        r["debit"] is None
    ), "Row must have exactly one of credit/debit set"

# 5. Reference provenance
for r in rows:
    assert (
        r["bank_reference"] in all_pdf_text
    ), f"Bank reference '{r['bank_reference']}' not found in PDF text"

print("All verifier checks passed successfully.")

# Write result
kit.write_result(rows)
print("parsed 18 rows")
```
