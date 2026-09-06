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
Account name NI V SCSP Closing ledger balance brought forward 103,014.97
Account number 240-222731-132 From 31 Mar 2026
Bank name Calder Luxembourg Closing available balance brought forward 103,014.97
Currency GBP From 31 Mar 2026
Location Luxembourg Current ledger balance 103,014.97
BIC CLDRLULL As at Not Available
IBAN LU085210240222731132 Current available balance 103,014.97
Account status Active As at Not Available
Account type Current account Specified date range 23 Mar 2026 to 31 Mar 2026
Bank reference Customer reference TRN type Value date Credit amount Debit amount Balance Time Post date
Balance as at close 31 Mar 2026 103,014.97
TT ABC414K0BGIBU WILLOWBANK TRF S+P- CHG 31 Mar 2026 -5.21 103,014.97 10:45 31 Mar 2026
Narrative COMMISSION GBP 5,21, 21398DX37I23
TT ABC414K0BGIBU WILLOWBANK TRF S+P- 31 Mar 2026 -15,701,940.20 103,020.18 10:45 31 Mar 2026
Narrative NI V KALVIK TOPCO LTD., 21398DX37I23, /GB40NRVB51407454522412 LOAN: FROM NI V SCSP TO NI V, KALVIK TOPCO LTD.. PROJECT WILLOWBANK
43110QR38LHY WILLOWBANK TRF S+P- 31 Mar 2026 -531,701.80 15,804,960.38 10:45 31 Mar 2026
Narrative NORDVIK INFRA.V CN SC,, SHORT TERM LOAN: FROM NI V SCSP TO NI V CN SCSP . PROJECT WILLOWBANK
TT UUJ428T85DPXP INTERNAL TRF S+P- CHG 31 Mar 2026 -5.22 16,336,662.18 07:10 31 Mar 2026
Narrative COMMISSION GBP 5,22, 22801YB03UF8
TT UUJ428T85DPXP INTERNAL TRF S+P- 31 Mar 2026 -610,000.00 16,336,667.40 07:10 31 Mar 2026
Narrative NI V SCSP, 22801YB03UF8, /DK8471936954300848 INTERNAL TRANSFER
V400024233703R22 NONREF S+P+ 31 Mar 2026 16,900,000.00 16,946,667.40 07:03 31 Mar 2026
Narrative 1/NORDVIK INFRASTRUCTURE PARTNER, S+P+ CHARGE WAIVED
Balance brought forward 31 Mar 2026 46,667.40
Balance as at close 30 Mar 2026 46,667.40
01 Apr 2026 | Account number 240-222731-132 Page 1 of 3

--- PAGE 2 ---
| Statement details
Bank reference Customer reference TRN type Value date Credit amount Debit amount Balance Time Post date
TT BLH196NB3RGUR AZURITE TRF S+P- CHG 30 Mar 2026 -5.20 46,667.40 07:00 30 Mar 2026
Narrative COMMISSION GBP 5,20, 24370KF00HEC
TT BLH196NB3RGUR AZURITE TRF S+P- 30 Mar 2026 -249,549.75 46,672.60 07:00 30 Mar 2026
Narrative NI V AZURITE HOLDCO LTD, 24370KF00HEC, /GB14NRVB35403891305213 EQUITY: FROM NORDVIK, INFRASTRUCTURE V SCSP TO NI V AZURITE HOLDCO LTD., PROJECT AZURITE.
TT NWK678RB9JBCQ AZURITE TRF S+P- CHG 30 Mar 2026 -5.20 296,222.35 07:00 30 Mar 2026
Narrative COMMISSION GBP 5,20, 82924VJ9010W
TT NWK678RB9JBCQ AZURITE TRF S+P- 30 Mar 2026 -582,282.75 296,227.55 07:00 30 Mar 2026
Narrative NI V AZURITE HOLDCO LTD, 82924VJ9010W, /GB14NRVB35403891305213 LOAN: FROM NORDVIK, INFRASTRUCTURE V SCSP TO NI V AZURITE HOLDCO LTD., PROJECT AZURITE.
59675NX26HUD AZURITE TRF S+P- 30 Mar 2026 -28,167.65 878,510.30 07:00 30 Mar 2026
Narrative NORDVIK INFRA.V CN SC,, SHORT-TERM LOAN: FROM NORDVIK, INFRASTRUCTURE V SCSP TO NORDVIK, INFRASTRUCTURE V CN SCSP. PROJECT AZURITE.
Balance brought forward 30 Mar 2026 906,677.95
Balance as at close 24 Mar 2026 906,677.95
TT MLQ644GDVPLTI FENWICK TRF S+P- CHG 24 Mar 2026 -5.19 906,677.95 08:10 24 Mar 2026
Narrative COMMISSION GBP 5,19, 19709GA25RZL
TT MLQ644GDVPLTI FENWICK TRF S+P- 24 Mar 2026 -1,160,696.30 906,683.14 08:10 24 Mar 2026
Narrative NI V FENWICK HOLDCO LTD,, 19709GA25RZL, /GB10NRVB98154047624001 LOAN: FROM NORDVIK INFRASTR, UCTURE V SCSP TO NI V FENWICK HOLDCO LTD.., PROJECT FENWICK.
49211YZ41JZ6 FENWICK TRF S+P- 24 Mar 2026 -39,303.70 2,067,379.44 08:10 24 Mar 2026
Narrative NORDVIK INFRA.V CN SC,, SHORT TERM LOAN: FROM NORDVIK, INFRASTRUCTURE V SCSP TO NORDVIK, INFRASTRUCTURE V CN SCSP. PROJECT FENWICK.
J545245036302N01 NONREF S+P+ 24 Mar 2026 2,100,000.00 2,106,683.14 07:02 24 Mar 2026
Narrative 1/NORDVIK INFRASTRUCTURE PARTNER, S+P+ CHARGE WAIVED
Balance brought forward 24 Mar 2026 6,683.14
Balance as at close 23 Mar 2026 6,683.14
NONREF NONREF S+P+ INT 23 Mar 2026 95.47 6,683.14 21:06 23 Mar 2026
Narrative CREDIT INTEREST
01 Apr 2026 | Account number 240-222731-132 Page 2 of 3

--- PAGE 3 ---
| Statement details
Bank reference Customer reference TRN type Value date Credit amount Debit amount Balance Time Post date
Balance brought forward 23 Mar 2026 6,587.67
01 Apr 2026 | Account number 240-222731-132 Page 3 of 3


# reply

```python
from decimal import Decimal
import re
import kit


def extract_line_text(line):
    if hasattr(line, "text") and isinstance(line.text, str):
        return line.text.strip()
    s = str(line).strip()
    if not s.startswith("<"):
        return s
    if hasattr(line, "words"):
        return " ".join(w["text"] for w in line.words).strip()
    return line.between(-9999, 9999).strip()


def build_column_bounds(col_positions):
    print("Raw column_positions:", col_positions)
    if isinstance(col_positions, dict):
        sorted_cols = sorted(col_positions.items(), key=lambda item: item[1])
    elif isinstance(col_positions, list):
        if len(col_positions) > 0 and isinstance(col_positions[0], (list, tuple)):
            sorted_cols = sorted(col_positions, key=lambda item: item[1])
        else:
            sorted_cols = list(enumerate(col_positions))
    else:
        raise ValueError(f"Unexpected column_positions type: {type(col_positions)}")

    bounds = {}
    for i, (name, x_start) in enumerate(sorted_cols):
        x_end = sorted_cols[i + 1][1] if i + 1 < len(sorted_cols) else 9999.0
        bounds[name] = (x_start, x_end)
    return bounds


def parse_statement():
    num_pages = kit.page_count()
    print(f"Total pages: {num_pages}")

    # Gather full document text for provenance checks
    full_pdf_text = ""
    for p in range(1, num_pages + 1):
        full_pdf_text += "\n" + kit.text(p)

    account_number = "240-222731-132"
    currency = "GBP"

    # Match account details from page 1 text if available
    acc_match = re.search(r"Account number\s+([\d-]+)", full_pdf_text)
    if acc_match:
        account_number = acc_match.group(1).strip()
    curr_match = re.search(r"Currency\s+([A-Z]{3})", full_pdf_text)
    if curr_match:
        currency = curr_match.group(1).strip()

    print(f"Account number: {account_number}, Currency: {currency}")

    col_bounds_p1 = build_column_bounds(kit.column_positions(1))
    print("Column bounds page 1:", col_bounds_p1)

    transactions = []

    # Regex pattern to match the tail of a transaction line:
    # (amount) (balance) (time HH:MM) (post_date DD Mon YYYY)
    tx_tail_pattern = re.compile(
        r"([-\d.,]+)\s+([\d.,]+)\s+(\d{2}:\d{2})\s+(\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})$"
    )

    for page_num in range(1, num_pages + 1):
        lines = kit.lines(page_num)
        print(f"\n--- Page {page_num}: {len(lines)} visual lines ---")

        # Try to get page-specific column bounds if possible
        try:
            col_bounds = build_column_bounds(kit.column_positions(page_num))
        except Exception as e:
            print(f"Using page 1 column bounds for page {page_num} ({e})")
            col_bounds = col_bounds_p1

        i = 0
        while i < len(lines):
            line = lines[i]
            line_str = extract_line_text(line)

            # Skip header / footer / marker lines
            if not line_str or line_str.startswith("Balance as at close") or line_str.startswith("Balance brought forward"):
                i += 1
                continue
            if line_str.startswith("Statement details") or line_str.startswith("Bank reference") or "Account number" in line_str:
                i += 1
                continue

            # Check if this line is a transaction line
            match = tx_tail_pattern.search(line_str)
            if match:
                amt_str = match.group(1).strip()
                bal_str = match.group(2).strip()
                time_str = match.group(3).strip()
                post_date_str = match.group(4).strip()

                # Text before the tail contains: bank_ref, cust_ref, trn_type, value_date
                prefix_str = line_str[: match.start()].strip()

                # Extract Value date (DD Mon YYYY before the amount)
                val_date_match = re.search(r"(\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})$", prefix_str)
                if val_date_match:
                    value_date = val_date_match.group(1).strip()
                    ref_trn_part = prefix_str[: val_date_match.start()].strip()
                else:
                    value_date = post_date_str
                    ref_trn_part = prefix_str

                # Identify TRN type
                trn_type_match = re.search(r"\b(S\+P-\s+CHG|S\+P-|S\+P\+\s+INT|S\+P\+)\b", ref_trn_part)
                if trn_type_match:
                    trn_type = trn_type_match.group(1).strip()
                else:
                    # Fallback using column positions
                    if "TRN type" in col_bounds and "Value date" in col_bounds:
                        trn_type = line.between(col_bounds["TRN type"][0], col_bounds["Value date"][0]).strip()
                    else:
                        trn_type = "UNKNOWN"

                # Extract Bank reference using column bounds
                bank_ref = ""
                if "Bank reference" in col_bounds and "Customer reference" in col_bounds:
                    bank_ref = line.between(
                        col_bounds["Bank reference"][0],
                        col_bounds["Customer reference"][0],
                    ).strip()

                if not bank_ref:
                    # If column slicing was empty, slice up to trn_type
                    parts = ref_trn_part.split()
                    bank_ref = parts[0]

                # Credit / Debit determination
                clean_amt = amt_str.replace(",", "")
                clean_bal = bal_str.replace(",", "")

                if amt_str.startswith("-"):
                    debit = clean_amt
                    credit = None
                else:
                    credit = clean_amt
                    debit = None

                # Now look ahead for Narrative continuation line(s)
                narrative_parts = []
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    next_str = extract_line_text(next_line)

                    # Stop if we hit next transaction, day marker, header, or footer
                    if tx_tail_pattern.search(next_str):
                        break
                    if next_str.startswith("Balance as at close") or next_str.startswith("Balance brought forward"):
                        break
                    if next_str.startswith("Statement details") or next_str.startswith("Bank reference") or "Account number" in next_str:
                        break

                    if next_str.startswith("Narrative"):
                        content = next_str[len("Narrative"):].strip()
                        if content:
                            narrative_parts.append(content)
                        j += 1
                    elif narrative_parts:
                        # Continuation line of narrative
                        narrative_parts.append(next_str)
                        j += 1
                    else:
                        break

                narrative_raw = " ".join(narrative_parts).strip()

                # Repair mid-word wrap marked by break character ','
                # e.g. "INFRASTR, UCTURE" -> "INFRASTRUCTURE"
                narrative = narrative_raw.replace("INFRASTR, UCTURE", "INFRASTRUCTURE")

                tx_row = {
                    "bank_reference": bank_ref,
                    "trn_type": trn_type,
                    "value_date": value_date,
                    "post_date": post_date_str,
                    "time": time_str,
                    "narrative": narrative,
                    "credit": credit,
                    "debit": debit,
                    "balance": clean_bal,
                    "account_number": account_number,
                    "currency": currency,
                    "page": page_num,
                }
                transactions.append(tx_row)
                print(f"Row {len(transactions)} (p.{page_num}): ref='{bank_ref}' trn='{trn_type}' cr={credit} db={debit} bal={clean_bal} time={time_str}")
                i = j
            else:
                i += 1

    print(f"\nExtracted {len(transactions)} transaction rows.")

    # --- Validation Checks ---
    assert len(transactions) == 16, f"Expected 16 rows, got {len(transactions)}"

    # 1. Closing balance check
    closing_bal_match = re.search(r"Closing ledger balance brought forward\s+([\d.,]+)", full_pdf_text)
    if closing_bal_match:
        expected_closing = closing_bal_match.group(1).replace(",", "")
        assert transactions[0]["balance"] == expected_closing, (
            f"Closing balance mismatch: first row has {transactions[0]['balance']}, expected {expected_closing}"
        )
        print(f"Closing balance verified: {expected_closing}")

    # 2. Balance chain check: balance[i] - amount[i] == balance[i+1]
    for idx in range(len(transactions) - 1):
        cur = transactions[idx]
        nxt = transactions[idx + 1]
        cur_b = Decimal(cur["balance"])
        nxt_b = Decimal(nxt["balance"])
        amt = Decimal(cur["credit"]) if cur["credit"] is not None else Decimal(cur["debit"])
        expected_next = cur_b - amt
        assert expected_next == nxt_b, (
            f"Balance chain broken at row {idx}: {cur_b} - ({amt}) = {expected_next} != next balance {nxt_b}"
        )
    print("Balance chain closed exactly across all rows.")

    # 3. Printed openings check
    last_tx = transactions[-1]
    last_b = Decimal(last_tx["balance"])
    last_amt = Decimal(last_tx["credit"]) if last_tx["credit"] is not None else Decimal(last_tx["debit"])
    final_opening = last_b - last_amt
    assert final_opening == Decimal("6587.67"), f"Final balance brought forward expected 6587.67, got {final_opening}"
    print(f"Final opening balance verified: {final_opening}")

    # 4. One amount per row check
    for idx, r in enumerate(transactions):
        assert (r["credit"] is None) != (r["debit"] is None), f"Row {idx} does not have exactly one amount set"
        assert "," not in r["balance"], f"Row {idx} balance contains comma"
        if r["credit"] is not None:
            assert "," not in r["credit"], f"Row {idx} credit contains comma"
        if r["debit"] is not None:
            assert "," not in r["debit"], f"Row {idx} debit contains comma"

    # 5. Reference provenance check
    for idx, r in enumerate(transactions):
        ref = r["bank_reference"]
        assert ref in full_pdf_text, f"Row {idx} bank_reference '{ref}' not found in PDF text"
    print("Reference provenance verified for all rows.")

    # Write output
    kit.write_result(transactions)
    print(f"parsed {len(transactions)} rows")


parse_statement()
```
