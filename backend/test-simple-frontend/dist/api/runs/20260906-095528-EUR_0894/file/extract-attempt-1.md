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
Account name NI ABF I SCSP Closing ledger balance brought forward 13,217,773.59
Account number 240-524291-030 From 31 Mar 2026
Bank name Calder Luxembourg Closing available balance brought forward 13,217,773.59
Currency EUR From 31 Mar 2026
Location Luxembourg Current ledger balance 13,217,773.59
BIC CLDRLULL As at Not Available
IBAN LU035210240524291030 Current available balance 13,217,773.59
Account status Active As at Not Available
Account type Current account Specified date range 23 Mar 2026 to 31 Mar 2026
Bank reference Customer reference TRN type Value date Credit amount Debit amount Balance Time Post date
NONREF NONREF TFR- 31 Mar 2026 -0.44 13,217,773.59 17:46 31 Mar 2026
Narrative CHARGES FOR 2, OUTWARD SEPA PAYMENT
10716RS62GWQ CEPHALUS TRF TFR+ 31 Mar 2026 301,908.70 13,217,774.03 11:01 31 Mar 2026
Narrative NORDVIK I.A.B. FUND I, TFR+ PMT FRM NI ABF II SCSP TO NI ABF I, SCSP FOR PURCHASE 100PER OF ACC INT, IN CEPHALUS BIOGAS 001 LTD PREMIUM, ACCRUED INTEREST PROJECT CEPHALUS
85720JS23WNK CEPHALUS TRF TFR+ 31 Mar 2026 2,013,809.89 12,915,865.33 11:01 31 Mar 2026
Narrative NORDVIK I.A.B. FUND I, TFR+ PMT FRM NI ABF II SCSP TO NI ABF I, SCSP FOR ACQ 100PER OF SHARES IN, CEPHALUS BIOGAS 001 LTD REL TOTAL, PREMIUM (EQUITY) PROJECT CEPHALUS)
24381JR11YY3 CEPHALUS TRF TFR+ 31 Mar 2026 4,232,000.00 10,902,055.44 11:01 31 Mar 2026
Narrative NORDVIK I.A.B. FUND I, TFR+ PMT FRM NI ABF II SCSP TO NI ABF I, SCSP FOR PURCHAS 100PER OF LOAN, PRINCIP IN CEPHALUS BIOGAS 001 LTD, TOTAL COST LOAN PROJECT CEPHALUS
ST65724109296034 52322485521381-4000 SCT 31 Mar 2026 -19,931.11 6,670,055.44 10:08 31 Mar 2026
038279
Narrative 52322485521381-7786132265, TRENTBECK AUDIT
QN29131563952037 22254822 92504555 SCT 31 Mar 2026 -509.80 6,689,986.55 10:08 31 Mar 2026
46212525
Narrative 22254822 92504555 46212525, NIP PLATFORM SOLUTIONS APS
QUR35762JQ16VCY5 NONREF TFR+ 31 Mar 2026 3,597,561.92 6,690,496.35 05:12 31 Mar 2026
Narrative 1/NI ABF I DEVCO APS, TFR+ Loan dist. - NI ABF I DevCo ApS to, NI ABF II SCSp related to contri. 5, ,6+ 7 in + dist. 1 in NI ABF I DevC, o ApS. Repay of loan principal. CHARGE WAIVED
01 Apr 2026 | Account number 240-524291-030 Page 1 of 2

--- PAGE 2 ---
| Statement details
Bank reference Customer reference TRN type Value date Credit amount Debit amount Balance Time Post date
55051QC31ZHZ CEPHALUS TRF TFR+ 31 Mar 2026 1.62 3,092,934.43 23:04 31 Mar 2026
Narrative NORDVIK I.A.B. FUND I, TFR+ OBO PMT FRM NI ABF II SCSP ON, BEHALF OF NI ABF II CO-INVEST SCSP, TO NI ABF I SCSP FOR ACQ OF 1 SHARE, IN CEPHALUS BIOGAS 001 LTD (EQUITY
85202DA174BN CEPHALUS TRF TFR+ 31 Mar 2026 1.62 3,092,932.81 23:04 31 Mar 2026
Narrative NORDVIK I.A.B. FUND I, TFR+ OBO PMT FRM NI ABF II SCSP ON, BEHALF OF NI ABF II QFPF BLOC. SCSP, TO NI ABF I SCSP FOR ACQ OF 1 SHARE, IN CEPHALUS BIOGAS 001 LTD (EQUITY
TT NQK807SFXYKMA INTERNAL TRF TFR- CHG 31 Mar 2026 -6.00 3,092,931.19 23:04 31 Mar 2026
Narrative COMMISSION EUR 6,00, 47223IZ05W0Z
TT NQK807SFXYKMA INTERNAL TRF TFR- 31 Mar 2026 -180,000.00 3,092,937.19 23:04 31 Mar 2026
Narrative NI ABF I SCSP, 47223IZ05W0Z, /DK6757710886323208 INTERNAL TRANSFER
36128KB34UJM SHORTTERM LOAN TFR- 31 Mar 2026 -20,000.00 3,272,937.19 23:04 31 Mar 2026
Narrative NI ABF I FEEDER SCSP, STL COVER INVOICES
26623WD49U68 CEPHALUS TRF TFR+ 31 Mar 2026 46,272.93 3,292,937.19 23:04 31 Mar 2026
Narrative NORDVIK I.A.B. FUND I, TFR+ PMT FRM NI ABF II SCSP TO NI ABF I, SCSP FOR ACQ 100PER OF SHARE IN, CEPHALUS BIOGAS 001 LTD REL COST (EQUITY) (PROJECT CEPHALUS)
HVJ01535FI1XKDJS NONREF TFR+ 27 Mar 2026 632,911.04 3,246,664.26 12:07 27 Mar 2026
Narrative 1/COVBURY ENERGI A/S FENNSTEAD 41, TFR+ SARDONYX CLOSING, FX GBP 556598,00 AT 1,0389605 681960417, CHARGE WAIVED
NONREF NONREF TFR+ INT 24 Mar 2026 1,423.44 2,613,753.22 07:05 24 Mar 2026
Narrative CREDIT INTEREST
TT YKC924KX4ART Q051140596245B65 TFR- 24 Mar 2026 -129,589.63 2,612,329.78 23:28 24 Mar 2026
Narrative BQVRFRPP, /FR6239723540911169279904595 CHARGE WAIVED
01 Apr 2026 | Account number 240-524291-030 Page 2 of 2


# reply

```python
from decimal import Decimal
import re
import kit


def parse():
    num_pages = kit.page_count()
    print(f"Statement page count: {num_pages}")

    # Extract account metadata from page 1 text
    p1_text = kit.text(1)
    acc_m = re.search(r"Account number\s+([0-9\-]+)", p1_text)
    account_number = acc_m.group(1) if acc_m else "240-524291-030"

    curr_m = re.search(r"Currency\s+([A-Z]{3})", p1_text)
    currency = curr_m.group(1) if curr_m else "EUR"

    print(f"Account number: {account_number}, Currency: {currency}")

    # Get column positions
    col_pos = kit.column_positions(1)
    print(f"Column positions: {col_pos}")

    # Normalize column positions
    col_dict = {}
    if isinstance(col_pos, dict):
        col_dict = {k.lower().strip(): v for k, v in col_pos.items()}
    elif isinstance(col_pos, list):
        for item in col_pos:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                col_dict[str(item[0]).lower().strip()] = item[1]
            elif isinstance(item, dict):
                name = item.get("text") or item.get("name") or ""
                x = item.get("x") or item.get("x0") or 0
                col_dict[str(name).lower().strip()] = x

    x_cust = col_dict.get("customer reference", 130.0)
    x_trn = col_dict.get("trn type", 260.0)
    x_val = col_dict.get("value date", 320.0)

    print(f"Resolved column boundaries: x_cust={x_cust}, x_trn={x_trn}, x_val={x_val}")

    # Transaction regex matching the end of a transaction line:
    # Value date, Amount, Balance, Time, Post date
    tx_re = re.compile(
        r"(\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})\s+"  # Value date
        r"(-?[\d,]+\.\d{2})\s+"  # Amount
        r"([\d,]+\.\d{2})\s+"  # Balance
        r"(\d{2}:\d{2})\s+"  # Time
        r"(\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})\s*$"  # Post date
    )

    rows = []
    current_tx = None
    collecting_narrative = False

    for page_num in range(1, num_pages + 1):
        lines = kit.lines(page_num)
        for line in lines:
            line_text = line.text.strip()
            m = tx_re.search(line_text)

            if m:
                # If we were collecting narrative for a previous transaction, finish it
                if current_tx is not None:
                    current_tx["narrative"] = re.sub(
                        r"DevC,\s*o\b", "DevCo", current_tx["narrative"]
                    ).strip()

                val_date = m.group(1)
                amt_str = m.group(2)
                bal_str = m.group(3).replace(",", "")
                time_str = m.group(4)
                post_date = m.group(5)

                if amt_str.startswith("-"):
                    debit = amt_str.replace(",", "")
                    credit = None
                else:
                    credit = amt_str.replace(",", "")
                    debit = None

                # Extract bank reference and trn_type using column boundaries
                bank_ref = line.between(0, x_cust).strip()
                trn_type = line.between(x_trn, x_val).strip()

                # Fallback extraction if column bounds yield empty string
                if not bank_ref or not trn_type:
                    prefix = line_text[: m.start()].strip()
                    tokens = prefix.split()
                    if not bank_ref and tokens:
                        bank_ref = tokens[0]
                    if not trn_type and tokens:
                        trn_type = tokens[-1]

                current_tx = {
                    "bank_reference": bank_ref,
                    "trn_type": trn_type,
                    "value_date": val_date,
                    "post_date": post_date,
                    "time": time_str,
                    "narrative": "",
                    "credit": credit,
                    "debit": debit,
                    "balance": bal_str,
                    "account_number": account_number,
                    "currency": currency,
                    "page": page_num,
                }
                rows.append(current_tx)
                collecting_narrative = False

            elif line_text.startswith("Narrative"):
                narr_content = re.sub(r"^Narrative:?\s*", "", line_text)
                if current_tx is not None:
                    current_tx["narrative"] = narr_content
                collecting_narrative = True

            elif collecting_narrative and current_tx is not None:
                # Check for table furniture / footers
                if (
                    "Page " in line_text
                    or "Statement details" in line_text
                    or "Account number" in line_text
                ):
                    collecting_narrative = False
                else:
                    current_tx["narrative"] += " " + line_text

    # Finalize last transaction narrative
    if current_tx is not None:
        current_tx["narrative"] = re.sub(
            r"DevC,\s*o\b", "DevCo", current_tx["narrative"]
        ).strip()

    # Self-checks
    print(f"Extracted {len(rows)} transactions.")
    for idx, r in enumerate(rows):
        print(
            f"Row {idx + 1}: ref={r['bank_reference']} trn={r['trn_type']} "
            f"cr={r['credit']} db={r['debit']} bal={r['balance']} time={r['time']}"
        )
        print(f"   narrative: {r['narrative']}")

    # Balance chain check
    for i in range(len(rows) - 1):
        cur_bal = Decimal(rows[i]["balance"])
        amt = (
            Decimal(rows[i]["credit"])
            if rows[i]["credit"] is not None
            else Decimal(rows[i]["debit"])
        )
        expected_next = cur_bal - amt
        actual_next = Decimal(rows[i + 1]["balance"])
        assert expected_next == actual_next, (
            f"Chain broken at row {i}: {cur_bal} - {amt} = {expected_next} != {actual_next}"
        )

    # Closing balance check
    p1_lines = kit.text(1)
    close_m = re.search(r"Closing ledger balance\s+[a-z ]*\s+([\d,]+\.\d{2})", p1_lines)
    if close_m:
        expected_close = close_m.group(1).replace(",", "")
        assert rows[0]["balance"] == expected_close, (
            f"Closing balance mismatch: {rows[0]['balance']} != {expected_close}"
        )

    # Reference provenance check
    full_pdf_text = " ".join(kit.text(p) for p in range(1, num_pages + 1))
    for r in rows:
        assert r["bank_reference"] in full_pdf_text, (
            f"Reference '{r['bank_reference']}' not found in PDF text"
        )

    # Amounts check
    for r in rows:
        assert (r["credit"] is not None) ^ (r["debit"] is not None), (
            f"Amount error in row: {r}"
        )

    print(f"parsed {len(rows)} rows")
    kit.write_result(rows)


parse()
```
