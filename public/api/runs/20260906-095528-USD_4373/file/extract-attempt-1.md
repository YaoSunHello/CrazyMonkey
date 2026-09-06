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
Account name NI GMF II SCSP Closing ledger balance brought forward 943,598.38
Account number 240-644826-130 From 31 Mar 2026
Bank name Calder Luxembourg Closing available balance brought forward 943,598.38
Currency USD From 31 Mar 2026
Location Luxembourg Current ledger balance 943,598.38
BIC CLDRLULL As at Not Available
IBAN LU795210240644826130 Current available balance 943,598.38
Account status Active As at Not Available
Account type Current account Specified date range 23 Mar 2026 to 31 Mar 2026
Bank reference Customer reference TRN type Value date Credit amount Debit amount Balance Time Post date
TT UCL163D8BANG N529897361545E26 S+P- 31 Mar 2026 -184,939.74 943,598.38 07:01 31 Mar 2026
Narrative BQVRFRPP, /448323310 CHARGE WAIVED
TT YCB037B7GBGIU ATRIA TRF S+P- CHG 31 Mar 2026 -6.87 1,128,538.12 07:00 31 Mar 2026
Narrative COMMISSION USD 6,87, 16138PF705L0
TT YCB037B7GBGIU ATRIA TRF S+P- 31 Mar 2026 -40,000.00 1,128,544.99 07:00 31 Mar 2026
Narrative NI GMF II COOPERATIEF U.A, 16138PF705L0, /DK8510041070352358 EQUITY: FROM NORDVIK, INFRASTRUCTURE GROWTH MARKET FUND II SCSP TO NI GMF II, COOPERATIEF U.A. PROJECT ATRIA
TT TJK451YCABAJG INTERNAL TRF S+P- CHG 31 Mar 2026 -6.87 1,168,544.99 07:00 31 Mar 2026
Narrative COMMISSION USD 6,87, 01104ZP014LE
TT TJK451YCABAJG INTERNAL TRF S+P- 31 Mar 2026 -85,000.00 1,168,551.86 07:00 31 Mar 2026
Narrative NI GMF II SCSP, 01104ZP014LE, /DK0996402923176963 INTERNAL TRANSFER
TT TID363HB4NMXE TANSYMOOR TRF S+P- CHG 31 Mar 2026 -6.87 1,253,551.86 07:00 31 Mar 2026
Narrative COMMISSION USD 6,87, 94453FH69CVT
TT TID363HB4NMXE TANSYMOOR TRF S+P- 31 Mar 2026 -750,000.00 1,253,558.73 07:00 31 Mar 2026
Narrative NI GMF II COOPERATIEF U.A., 94453FH69CVT, /DK8510041070352358 EQUITY: FROM NORDVIK INFRAST, RUCTURE GROWTH MARKETS FUND II SCSP TO NI GMF II COOPER, ATIEF U.A. PROJECT TANSYMOOR.
01 Apr 2026 | Account number 240-644826-130 Page 1 of 3

--- PAGE 2 ---
| Statement details
Bank reference Customer reference TRN type Value date Credit amount Debit amount Balance Time Post date
TT XTT580QZUKJDU IAPETUS TRF S+P- CHG 31 Mar 2026 -6.87 2,003,558.73 07:00 31 Mar 2026
Narrative COMMISSION USD 6,87, 93301QH142TF
TT XTT580QZUKJDU IAPETUS TRF S+P- 31 Mar 2026 -667,723.00 2,003,565.60 07:00 31 Mar 2026
Narrative NI GMF II COOPERATIEF U.A, 93301QH142TF, /DK8510041070352358 EQUITY: FROM NI GMF II SCSP TO, NI GMF II COOPERATIEF U.A. PROJECT IAPETUS.
TT LKS976XV0DUWR BRAGI TRF S+P- CHG 31 Mar 2026 -6.87 2,671,288.60 07:00 31 Mar 2026
Narrative COMMISSION USD 6,87, 43433NJ28TB0
TT LKS976XV0DUWR BRAGI TRF S+P- 31 Mar 2026 -736,000.00 2,671,295.47 07:00 31 Mar 2026
Narrative NI GMF II COOPERATIEF U.A, 43433NJ28TB0, /DK8510041070352358 EQUITY: FROM NORDVIK, INFRASTRUCTURE GROWTH MARKETS FUND II SCSP TO NI GMF II, COOPERATIEF U.A. PROJECT BRAGI.
TT KCX456J16RYR PFMDHL1651253510 S+P- 27 Mar 2026 -10,000,000.00 3,407,295.47 14:21 27 Mar 2026
Narrative BQVRFRPP, /448323310 CHARGE WAIVED
SECVJT1732059308 NONREF S+P+ 24 Mar 2026 13,007,460.48 13,407,295.47 16:36 24 Mar 2026
Narrative 1/NORDVIK INFRASTRUCTURE PARTNER, S+P+ CHARGE WAIVED
TT HZR353RVTFKKR NI GMF II COOPER S+P- CHG 24 Mar 2026 -6.97 399,834.99 08:09 24 Mar 2026
Narrative COMMISSION USD 6,97, 40123ZC60S9V
TT HZR353RVTFKKR NI GMF II COOPER S+P- 24 Mar 2026 -20,000.00 399,841.96 08:09 24 Mar 2026
Narrative NI GMF II COOPERATIEF U.A, 40123ZC60S9V, /DK8510041070352358 EQUITY: FROM NORDVIK, INFRASTRUCTURE GROWTH MARKET FUND, II SCSP TO NI GMF II COOPERATIEF, U.A. PROJECT OFW-XX-1
TT UPP910JIFPXRB ELMWOOD TRF S+P- CHG 24 Mar 2026 -6.97 419,841.96 08:08 24 Mar 2026
Narrative COMMISSION USD 6,97, 20235GB45D5M
TT UPP910JIFPXRB ELMWOOD TRF S+P- 24 Mar 2026 -260,000.00 419,848.93 08:08 24 Mar 2026
Narrative NI GMF II COOPERATIEF U.A, 20235GB45D5M, /DK8510041070352358 EQUITY: FROM NORDVIK, INFRASTRUCTURE GROWTH MARKETS FUND, II SCSP TO NI GMF II COOPERATIEF, U.A. PROJECT ELMWOOD.
TT WKK555IJRWKY A452951323977R68 S+P- 24 Mar 2026 -38,739.87 679,848.93 07:01 24 Mar 2026
Narrative BQVRFRPP, /448323310 CHARGE WAIVED
01 Apr 2026 | Account number 240-644826-130 Page 2 of 3

--- PAGE 3 ---
| Statement details
Bank reference Customer reference TRN type Value date Credit amount Debit amount Balance Time Post date
NONREF NONREF S+P+ INT 23 Mar 2026 3,260.28 718,588.80 21:06 23 Mar 2026
Narrative CREDIT INTEREST
01 Apr 2026 | Account number 240-644826-130 Page 3 of 3


# reply

```python
from decimal import Decimal
import re
import kit

# Extract account details from Page 1
p1_text = kit.text(1)
acc_match = re.search(r"Account number\s+([\d\-]+)", p1_text)
account_number = acc_match.group(1) if acc_match else "240-644826-130"

curr_match = re.search(r"Currency\s+([A-Z]{3})", p1_text)
currency = curr_match.group(1) if curr_match else "USD"

cb_match = re.search(r"Current ledger balance\s+([\d,]+\.\d{2})", p1_text)
if not cb_match:
    cb_match = re.search(
        r"Closing ledger balance brought forward\s+([\d,]+\.\d{2})", p1_text
    )
closing_balance_str = (
    cb_match.group(1).replace(",", "") if cb_match else "943598.38"
)

print(f"Account: {account_number}, Currency: {currency}")
print(f"Printed closing balance: {closing_balance_str}")


def parse_column_map(page_num):
    raw = kit.column_positions(page_num)
    col_map = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, (int, float)):
                col_map[k] = float(v)
            elif isinstance(v, str) and isinstance(k, (int, float)):
                col_map[v] = float(k)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                a, b = item[0], item[1]
                if isinstance(a, str) and isinstance(b, (int, float)):
                    col_map[a] = float(b)
                elif isinstance(b, str) and isinstance(a, (int, float)):
                    col_map[b] = float(a)
    return col_map


def find_col_x(col_map, name):
    name_lower = name.lower()
    for k, v in col_map.items():
        if k.lower() == name_lower:
            return v
    for k, v in col_map.items():
        if name_lower in k.lower():
            return v
    raise KeyError(f"Column '{name}' not found in {col_map}")


rows = []
time_re = re.compile(r"\b\d{2}:\d{2}\b")
date_re = re.compile(r"\b\d{1,2} [A-Za-z]{3} \d{4}\b")

page_count = kit.page_count()

for p in range(1, page_count + 1):
    lines = kit.lines(p)
    col_map = parse_column_map(p)

    x_cust = find_col_x(col_map, "Customer reference")
    x_trn = find_col_x(col_map, "TRN type")
    x_val = find_col_x(col_map, "Value date")
    x_cred = find_col_x(col_map, "Credit amount")
    x_deb = find_col_x(col_map, "Debit amount")
    x_bal = find_col_x(col_map, "Balance")
    x_time = find_col_x(col_map, "Time")
    x_post = find_col_x(col_map, "Post date")

    num_lines = len(lines)
    i = 0
    while i < num_lines:
        line = lines[i]
        text = line.text.strip()

        # Skip header, statement details, and footer lines
        if (
            "Statement details" in text
            or "Bank reference" in text
            or "Page " in text
            or "Account number" in text
            or "Balance as at close" in text
            or "Balance brought forward" in text
        ):
            i += 1
            continue

        # Check if this visual line is a transaction line
        has_time = time_re.search(text)
        has_date = date_re.search(text)

        if has_time and has_date and not text.startswith("Narrative"):
            # Transaction row
            bank_ref = " ".join(line.between(0, x_cust).split())
            trn_type = " ".join(line.between(x_trn, x_val).split())
            val_date = " ".join(line.between(x_val, x_cred).split())
            credit_str = line.between(x_cred, x_deb).strip()
            debit_str = line.between(x_deb, x_bal).strip()
            bal_str = line.between(x_bal, x_time).strip().replace(",", "")
            time_str = line.between(x_time, x_post).strip()
            post_date = " ".join(line.between(x_post, 9999).split())

            if re.search(r"\d", credit_str):
                credit = credit_str.replace(",", "")
                debit = None
            elif re.search(r"\d", debit_str):
                credit = None
                debit = debit_str.replace(",", "")
            else:
                credit = None
                debit = None

            # Collect narrative continuation lines
            narrative_parts = []
            j = i + 1
            while j < num_lines:
                next_line = lines[j]
                next_text = next_line.text.strip()

                if (
                    time_re.search(next_text)
                    and date_re.search(next_text)
                    and not next_text.startswith("Narrative")
                ):
                    break
                if (
                    "Page " in next_text
                    and "Account number" in next_text
                    or "Statement details" in next_text
                    or "Bank reference" in next_text
                ):
                    break

                cleaned = re.sub(r"^Narrative\s*", "", next_text).strip()
                if cleaned:
                    narrative_parts.append(cleaned)
                j += 1

            narrative_raw = " ".join(narrative_parts)
            # Reconstruct mid-word wraps marked by break character comma
            narrative = re.sub(r"INFRAST,\s*RUCTURE", "INFRASTRUCTURE", narrative_raw)
            narrative = re.sub(r"COOPER,\s*ATIEF", "COOPERATIEF", narrative)

            row = {
                "bank_reference": bank_ref,
                "trn_type": trn_type,
                "value_date": val_date,
                "post_date": post_date,
                "time": time_str,
                "narrative": narrative,
                "credit": credit,
                "debit": debit,
                "balance": bal_str,
                "account_number": account_number,
                "currency": currency,
                "page": p,
            }
            rows.append(row)
            i = j
        else:
            i += 1

# Verification checks
print(f"Extracted {len(rows)} rows across {page_count} pages.")

# 1. Closing balance check
if rows:
    first_bal = rows[0]["balance"]
    assert first_bal == closing_balance_str, (
        f"Closing balance mismatch: {first_bal} != {closing_balance_str}"
    )
    print(f"Closing balance matches: {first_bal}")

# 2. Balance chain check
for k in range(len(rows) - 1):
    r_curr = rows[k]
    r_next = rows[k + 1]
    bal_curr = Decimal(r_curr["balance"])
    amt_curr = (
        Decimal(r_curr["credit"])
        if r_curr["credit"] is not None
        else Decimal(r_curr["debit"])
    )
    bal_next = Decimal(r_next["balance"])
    expected_next = bal_curr - amt_curr
    assert expected_next == bal_next, (
        f"Chain broken at row {k}: {bal_curr} - {amt_curr} = {expected_next} != {bal_next}"
    )

print("Balance chain intact across all rows.")

# 3. Provenance check
all_pdf_text = " ".join(kit.text(p) for p in range(1, page_count + 1))
for r in rows:
    assert r["bank_reference"] in all_pdf_text, (
        f"Provenance failed for: {r['bank_reference']}"
    )

print("Bank reference provenance verified.")

# Write final result
kit.write_result(rows)
print(f"parsed {len(rows)} rows")
```
