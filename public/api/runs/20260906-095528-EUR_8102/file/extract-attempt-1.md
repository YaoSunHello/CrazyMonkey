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
Account name NI ABF II SCSP Closing ledger balance brought forward 20,088.32
Account number 240-149813-030 From 31 Mar 2026
Bank name Calder Luxembourg Closing available balance brought forward 20,088.32
Currency EUR From 31 Mar 2026
Location Luxembourg Current ledger balance 20,088.32
BIC CLDRLULL As at Not Available
IBAN LU355210240149813030 Current available balance 20,088.32
Account status Active As at Not Available
Account type Current account Specified date range 23 Mar 2026 to 31 Mar 2026
Bank reference Customer reference TRN type Value date Credit amount Debit amount Balance Time Post date
NONREF NONREF TFR- 31 Mar 2026 -0.44 20,088.32 17:46 31 Mar 2026
Narrative CHARGES FOR 2, OUTWARD SEPA PAYMENT
10716RS62GWQ CEPHALUS TRF TFR- 31 Mar 2026 -301,908.70 20,088.76 11:01 31 Mar 2026
Narrative NI ABF I SCSP, PMT FRM NI ABF II SCSP TO NI ABF I, SCSP FOR PURCHASE 100PER OF ACC INT, IN CEPHALUS BIOGAS 001 LTD PREMIUM, ACCRUED INTEREST PROJECT CEPHALUS
85720JS23WNK CEPHALUS TRF TFR- 31 Mar 2026 -2,013,809.89 321,997.46 11:01 31 Mar 2026
Narrative NI ABF I SCSP, PMT FRM NI ABF II SCSP TO NI ABF I, SCSP FOR ACQ 100PER OF SHARES IN, CEPHALUS BIOGAS 001 LTD REL TOTAL, PREMIUM (EQUITY) PROJECT CEPHALUS)
24381JR11YY3 CEPHALUS TRF TFR- 31 Mar 2026 -4,232,000.00 2,335,807.35 11:01 31 Mar 2026
Narrative NI ABF I SCSP, PMT FRM NI ABF II SCSP TO NI ABF I, SCSP FOR PURCHAS 100PER OF LOAN, PRINCIP IN CEPHALUS BIOGAS 001 LTD, TOTAL COST LOAN PROJECT CEPHALUS
WQX04328RE10ADP4 NONREF TFR+ 31 Mar 2026 6,550,000.00 6,567,807.35 10:58 31 Mar 2026
Narrative NORDVIK INFRASTRUCTURE ADVANCED, TFR+ INTERNAL TRANSFER, CHARGE WAIVED
WW43092242598430 29000231,84819265 SCT 31 Mar 2026 -1,041.13 17,807.35 10:18 31 Mar 2026
Narrative 29000231,84819265, NIP PLATFORM SOLUTIONS APS
YP03586039037340 52443473437109-4000 SCT 31 Mar 2026 -5,085.23 18,848.48 10:18 31 Mar 2026
051656
Narrative 52443473437109-3528152584, TRENTBECK AUDIT LUXEMBOURG
01 Apr 2026 | Account number 240-149813-030 Page 1 of 2

--- PAGE 2 ---
| Statement details
Bank reference Customer reference TRN type Value date Credit amount Debit amount Balance Time Post date
55051QC31ZHZ CEPHALUS TRF TFR- 31 Mar 2026 -1.62 23,933.71 23:04 31 Mar 2026
Narrative NI ABF I SCSP, OBO PMT FRM NI ABF II SCSP ON BEHALF OF NI ABF II CO-INVEST SCSP, TO NI ABF I SCSP FOR ACQ OF 1 SHARE, IN CEPHALUS BIOGAS 001 LTD (EQUITY
85202DA174BN CEPHALUS TRF TFR- 31 Mar 2026 -1.62 23,935.33 23:04 31 Mar 2026
Narrative NI ABF I SCSP, OBO PMT FRM NI ABF II SCSP ON BEHALF OF NI ABF II QFPF BLOC. SCSP, TO NI ABF I SCSP FOR ACQ OF 1 SHARE, IN CEPHALUS BIOGAS 001 LTD (EQUITY
26623WD49U68 CEPHALUS TRF TFR- 31 Mar 2026 -46,272.93 23,936.95 23:04 31 Mar 2026
Narrative NI ABF I SCSP, PMT FRM NI ABF II SCSP TO NI ABF I, SCSP FOR ACQ 100PER OF SHARE IN, CEPHALUS BIOGAS 001 LTD REL COST (EQUITY) (PROJECT CEPHALUS)
41377TZ050XC MIZARCO TRF TFR- 25 Mar 2026 -664,295.53 70,209.88 12:46 25 Mar 2026
Narrative NI ABF II MIZARCO S.A R., PAYMENT FROM NORDVIK INFRASTRUCTURE ABF II SCSP, TO TO NI ABF II MIZARCO S.A R.L. PROJECT BOREAS. TOTAL COST (LOAN)
34487ET23F39 MIZARCO TRF TFR- 25 Mar 2026 -3,465,688.12 734,505.41 12:45 25 Mar 2026
Narrative NI ABF II MIZARCO S.A R., PAYMENT FROM NORDVIK INFRASTRUCTURE ABF II SCSP, TO TO NI ABF II MIZARCO S.A R.L. PROJECT MIZAR. TOTAL COST (LOAN)
LRP25958JG3G21PQ NONREF TFR+ 25 Mar 2026 4,200,000.00 4,200,193.53 12:29 25 Mar 2026
Narrative NORDVIK INFRASTRUCTURE ADVANCED, TFR+ INTERNAL TRANSFER TO COVER INVOICES, CHARGE WAIVED
33411WL46TRZ INTERNALTRANSFER TFR- 24 Mar 2026 -5,000.00 193.53 08:19 24 Mar 2026
Narrative LU HBEU 240-149813-131, INTERNAL FX TRANSFER TO COVER INVOICES
51300TQ48FS0 MIZARCO TRF TFR- 24 Mar 2026 -108,724.20 5,193.53 08:07 24 Mar 2026
Narrative NI ABF II MIZARCO S.A R., PAYMENT FROM NORDVIK INFRASTRUCTURE ABF II SCSP, TO TO NI ABF II MIZARCO S.A R.L., PROJECT GALENE. TOTAL COST (LOAN)
NONREF NONREF TFR+ INT 24 Mar 2026 50.54 113,917.73 07:05 24 Mar 2026
Narrative CREDIT INTEREST
01 Apr 2026 | Account number 240-149813-030 Page 2 of 2


# reply

```python
import re
from decimal import Decimal
import kit


def get_line_text(line):
    if hasattr(line, "text"):
        return line.text
    return str(line)


def parse():
    account_number = "240-149813-030"
    currency = "EUR"

    try:
        p1_text = kit.text(1)
        m_acc = re.search(r"Account number\s+([0-9-]+)", p1_text)
        if m_acc:
            account_number = m_acc.group(1).strip()
        m_curr = re.search(r"Currency\s+([A-Z]{3})", p1_text)
        if m_curr:
            currency = m_curr.group(1).strip()
    except Exception as e:
        print(f"Header extraction note: {e}")

    print(f"Account: {account_number}, Currency: {currency}")

    num_pages = kit.page_count()
    rows = []

    tx_pattern = re.compile(
        r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+([\d,.-]+)\s+([\d,.]+)\s+(\d{2}:\d{2})\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})$"
    )

    for page_num in range(1, num_pages + 1):
        lines = kit.lines(page_num)
        col_pos = kit.column_positions(page_num)
        print(f"Page {page_num} col_pos: {col_pos}")

        if isinstance(col_pos, dict):
            cols_sorted = sorted(col_pos.items(), key=lambda x: x[1])
        elif isinstance(col_pos, list):
            if len(col_pos) > 0 and isinstance(col_pos[0], dict):
                cols_sorted = []
                for item in col_pos:
                    name = (
                        item.get("text")
                        or item.get("name")
                        or item.get("column")
                    )
                    x = item.get("x") or item.get("x0") or item.get("left")
                    cols_sorted.append((name, x))
                cols_sorted.sort(key=lambda x: x[1])
            else:
                cols_sorted = sorted(col_pos, key=lambda x: x[1])
        else:
            cols_sorted = []

        col_ranges = {}
        for i, (col_name, left) in enumerate(cols_sorted):
            right = (
                cols_sorted[i + 1][1]
                if i + 1 < len(cols_sorted)
                else 99999.0
            )
            col_ranges[col_name.strip()] = (left, right)

        def get_col_val(line_obj, name):
            for k, (left, right) in col_ranges.items():
                if k.lower() == name.lower() or name.lower() in k.lower():
                    try:
                        val = line_obj.between(left, right)
                        if isinstance(val, str):
                            return val.strip()
                    except Exception:
                        pass
            return ""

        for idx, line in enumerate(lines):
            text = get_line_text(line).strip()
            if text.startswith("Bank reference") or text.startswith("Narrative"):
                continue

            m = tx_pattern.search(text)
            if not m:
                continue

            val_date_regex = m.group(1)
            raw_amt = m.group(2)
            raw_bal = m.group(3)
            time_regex = m.group(4)
            post_date_regex = m.group(5)

            prefix = text[: m.start(1)].strip()
            prefix_tokens = prefix.split()
            fallback_bank_ref = prefix_tokens[0] if prefix_tokens else "NONREF"

            bank_ref = get_col_val(line, "Bank reference")
            if not bank_ref:
                bank_ref = fallback_bank_ref

            trn_type = get_col_val(line, "TRN type")
            if not trn_type:
                if len(prefix_tokens) >= 3:
                    trn_type = " ".join(prefix_tokens[2:])
                else:
                    trn_type = prefix_tokens[-1]

            val_date = get_col_val(line, "Value date") or val_date_regex
            time_str = get_col_val(line, "Time") or time_regex
            post_date = get_col_val(line, "Post date") or post_date_regex

            cred_val = get_col_val(line, "Credit amount")
            deb_val = get_col_val(line, "Debit amount")

            if cred_val:
                credit = cred_val.replace(",", "")
                debit = None
            elif deb_val:
                debit = deb_val.replace(",", "")
                credit = None
            else:
                if raw_amt.startswith("-"):
                    debit = raw_amt.replace(",", "")
                    credit = None
                else:
                    credit = raw_amt.replace(",", "")
                    debit = None

            bal_val = get_col_val(line, "Balance")
            balance = (bal_val if bal_val else raw_bal).replace(",", "")

            narrative = ""
            for next_idx in range(idx + 1, len(lines)):
                next_text = get_line_text(lines[next_idx]).strip()
                if tx_pattern.search(next_text) and not next_text.startswith(
                    "Narrative"
                ):
                    break
                if next_text.startswith("01 Apr") or "Page " in next_text:
                    break
                if re.match(r"^\s*Narrative\b", next_text):
                    narrative = re.sub(
                        r"^\s*Narrative\s*:?\s*", "", next_text
                    ).strip()
                    break

            row = {
                "bank_reference": bank_ref,
                "trn_type": trn_type,
                "value_date": val_date,
                "post_date": post_date,
                "time": time_str,
                "narrative": narrative,
                "credit": credit,
                "debit": debit,
                "balance": balance,
                "account_number": account_number,
                "currency": currency,
                "page": page_num,
            }
            rows.append(row)

    print(f"Parsed {len(rows)} raw rows across {num_pages} pages.")

    for i in range(len(rows) - 1):
        c_bal = Decimal(rows[i]["balance"])
        amt = Decimal(
            rows[i]["credit"]
            if rows[i]["credit"] is not None
            else rows[i]["debit"]
        )
        exp_next = c_bal - amt
        act_next = Decimal(rows[i + 1]["balance"])
        if exp_next != act_next:
            print(
                f"CHAIN ERROR at {i}: bal={c_bal}, amt={amt}, exp={exp_next}, act={act_next}"
            )
        else:
            print(f"Row {i} -> {i+1} chained correctly: {exp_next}")

    kit.write_result(rows)
    print(f"parsed {len(rows)} rows")


if __name__ == "__main__":
    parse()
```
