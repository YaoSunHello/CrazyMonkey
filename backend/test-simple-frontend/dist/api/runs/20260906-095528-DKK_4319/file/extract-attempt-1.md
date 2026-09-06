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
Account name NI ABF II SCSP Closing ledger balance brought forward 12,887.11
Account number 240-149813-131 From 31 Mar 2026
Bank name Calder Luxembourg Closing available balance brought forward 12,887.11
Currency DKK From 31 Mar 2026
Location Luxembourg Current ledger balance 12,887.11
BIC CLDRLULL As at Not Available
IBAN LU245210240149813131 Current available balance 12,887.11
Account status Active As at Not Available
Account type Current account Specified date range 23 Mar 2026 to 31 Mar 2026
Bank reference Customer reference TRN type Value date Credit amount Debit amount Balance Time Post date
TT JSL083B50KRNM INV SETTLEMENT S+P- CHG 31 Mar 2026 -44.83 12,887.11 10:50 31 Mar 2026
Narrative COMMISSION DKK 44,83, 89732SV16BGK
TT JSL083B50KRNM INV SETTLEMENT S+P- 31 Mar 2026 -24,750.00 12,931.94 10:50 31 Mar 2026
Narrative ULLA B. HILLEBRANDT CONSULTING, 89732SV16BGK, /DK5899030112098247 78
TT TYS581R85JJGZ INV SETTLEMENT S+P- CHG 31 Mar 2026 -44.83 37,681.94 10:50 31 Mar 2026
Narrative COMMISSION DKK 44,83, 55633BC44JQ0
TT TYS581R85JJGZ INV SETTLEMENT S+P- 31 Mar 2026 -46,608.00 37,726.77 10:50 31 Mar 2026
Narrative NIP LIT, 55633BC44JQ0, /DK0441919414619452 RI00034
IJC91823B071SK14 NONREF TFR+ 31 Mar 2026 73,602.74 84,334.77 10:46 31 Mar 2026
Narrative NORDVIK INFRASTRUCTURE ADVANCED, TFR+ INTERNAL FX TRANSFER, FX EUR 10000,00 AT 7,1620422 032424373, CHARGE WAIVED
TT EWR783W3NUPCV INV SETTLEMENT S+P- CHG 31 Mar 2026 -44.84 10,732.03 07:00 31 Mar 2026
Narrative COMMISSION DKK 44,84, 08334GU5571N
TT EWR783W3NUPCV INV SETTLEMENT S+P- 31 Mar 2026 -4,121.79 10,776.87 07:00 31 Mar 2026
Narrative NISC APS, 08334GU5571N, /DK6213128232682559 LO-DK00629
01 Apr 2026 | Account number 240-149813-131 Page 1 of 2

--- PAGE 2 ---
| Statement details
Bank reference Customer reference TRN type Value date Credit amount Debit amount Balance Time Post date
TT VJW022TY4REJT INV SETTLEMENT S+P- CHG 24 Mar 2026 -44.84 14,898.66 08:22 24 Mar 2026
Narrative COMMISSION DKK 44,84, 44008EZ203K5
TT VJW022TY4REJT INV SETTLEMENT S+P- 24 Mar 2026 -23,800.00 14,943.50 08:22 24 Mar 2026
Narrative RAQ MARBECK COMMUNICATIONS, 44008EZ203K5, /DK0503692241454564 499
33411WL46TRZ INTERNALTRANSFER TFR+ 24 Mar 2026 36,796.90 38,743.50 08:19 24 Mar 2026
Narrative LU HBEU 240-149813-030, TFR+ INTERNAL FX TRANSFER TO COVER INVOICES, FX EUR 5000,00 AT 7,0193998 524830540
01 Apr 2026 | Account number 240-149813-131 Page 2 of 2


# reply

```python
import re
from decimal import Decimal
import kit


def normalize_col(name):
    n = name.lower().strip()
    if "bank" in n and "ref" in n:
        return "bank_reference"
    if "cust" in n and "ref" in n:
        return "customer_reference"
    if "trn" in n:
        return "trn_type"
    if "val" in n and "date" in n:
        return "value_date"
    if "cred" in n:
        return "credit"
    if "deb" in n:
        return "debit"
    if "bal" in n:
        return "balance"
    if "time" in n:
        return "time"
    if "post" in n and "date" in n:
        return "post_date"
    return n


def get_column_intervals(page_num):
    cp = kit.column_positions(page_num)
    print(f"Page {page_num} raw column_positions: {cp}")

    cols = []
    if isinstance(cp, dict):
        items = list(cp.items())
        if isinstance(items[0][0], str):
            cols = [(k, float(v)) for k, v in items]
        else:
            cols = [(str(v), float(k)) for k, v in items]
    elif isinstance(cp, list):
        if len(cp) > 0 and isinstance(cp[0], tuple):
            cols = [(str(k), float(v)) for k, v in cp]
        elif len(cp) > 0 and isinstance(cp[0], dict):
            for d in cp:
                name = (
                    d.get("name")
                    or d.get("text")
                    or d.get("title")
                    or d.get("header")
                )
                x = (
                    d.get("x")
                    or d.get("x0")
                    or d.get("left")
                    or d.get("pos")
                )
                cols.append((str(name), float(x)))
        elif len(cp) > 0 and isinstance(cp[0], (int, float)):
            headers = [
                "Bank reference",
                "Customer reference",
                "TRN type",
                "Value date",
                "Credit amount",
                "Debit amount",
                "Balance",
                "Time",
                "Post date",
            ]
            cols = list(zip(headers, [float(x) for x in cp]))

    cols.sort(key=lambda item: item[1])

    intervals = []
    for i in range(len(cols)):
        name = normalize_col(cols[i][0])
        x_start = 0.0 if i == 0 else cols[i][1]
        x_end = cols[i + 1][1] if i + 1 < len(cols) else 10000.0
        intervals.append((name, x_start, x_end))

    return intervals


def parse_statement():
    page_cnt = kit.page_count()
    print(f"Total pages: {page_cnt}")

    full_pdf_text = ""
    for p in range(1, page_cnt + 1):
        full_pdf_text += kit.text(p) + "\n"

    # Extract account number and currency from text
    acc_match = re.search(r"Account number\s+([0-9A-Za-z-]+)", full_pdf_text)
    account_number = acc_match.group(1) if acc_match else "240-149813-131"

    curr_match = re.search(r"Currency\s+([A-Z]{3})", full_pdf_text)
    currency = curr_match.group(1) if curr_match else "DKK"

    print(f"Account number: {account_number}, Currency: {currency}")

    # Regex matching transaction line endings
    trn_pattern = re.compile(
        r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+(-?[\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+(\d{2}:\d{2})\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})$"
    )

    rows = []

    for page_num in range(1, page_cnt + 1):
        lines = kit.lines(page_num)
        intervals = get_column_intervals(page_num)
        print(f"Page {page_num}: {len(lines)} lines")

        i = 0
        while i < len(lines):
            line = lines[i]
            text = line.text.strip()

            m = trn_pattern.search(text)
            if m:
                # Column values via intervals
                row_cols = {}
                for name, x_start, x_end in intervals:
                    val = line.between(x_start, x_end).strip()
                    row_cols[name] = val

                val_date = m.group(1)
                amt_str = m.group(2)
                bal_str = m.group(3).replace(",", "")
                time_str = m.group(4)
                post_date_str = m.group(5)

                # Determine credit vs debit
                deb_col = row_cols.get("debit", "")
                cred_col = row_cols.get("credit", "")

                if deb_col and not cred_col:
                    debit = deb_col.replace(",", "")
                    credit = None
                elif cred_col and not deb_col:
                    credit = cred_col.replace(",", "")
                    debit = None
                else:
                    if amt_str.startswith("-"):
                        debit = amt_str.replace(",", "")
                        credit = None
                    else:
                        credit = amt_str.replace(",", "")
                        debit = None

                bank_ref = row_cols.get("bank_reference", "")
                trn_type = row_cols.get("trn_type", "")

                # Narrative on subsequent line
                narrative = ""
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    next_text = next_line.text.strip()
                    if next_text.startswith("Narrative"):
                        narr = re.sub(r"^Narrative:?\s*", "", next_text).strip()
                        narrative = narr
                        j += 1
                        break
                    elif trn_pattern.search(next_text) or "Page " in next_text:
                        break
                    else:
                        j += 1

                row = {
                    "bank_reference": bank_ref,
                    "trn_type": trn_type,
                    "value_date": val_date,
                    "post_date": post_date_str,
                    "time": time_str,
                    "narrative": narrative,
                    "credit": credit,
                    "debit": debit,
                    "balance": bal_str,
                    "account_number": account_number,
                    "currency": currency,
                    "page": page_num,
                }
                print(f"Extracted row: {row}")
                rows.append(row)
                i = j
            else:
                i += 1

    # Verify balance chain
    print("\n--- Verifying balance chain ---")
    for idx in range(len(rows) - 1):
        curr_bal = Decimal(rows[idx]["balance"])
        amt = (
            Decimal(rows[idx]["credit"])
            if rows[idx]["credit"] is not None
            else Decimal(rows[idx]["debit"])
        )
        next_bal = Decimal(rows[idx + 1]["balance"])
        calc_bal = curr_bal - amt
        diff = calc_bal - next_bal
        print(
            f"Row {idx} -> {idx+1}: {curr_bal} - ({amt}) = {calc_bal}, next={next_bal}, diff={diff}"
        )
        assert diff == 0, f"Balance chain mismatch at row {idx}"

    # Verify reference provenance
    print("\n--- Verifying reference provenance ---")
    for r in rows:
        ref = r["bank_reference"]
        assert ref in full_pdf_text, f"Reference {ref!r} not in PDF text"

    kit.write_result(rows)
    print(f"parsed {len(rows)} rows")


if __name__ == "__main__":
    parse_statement()
```
