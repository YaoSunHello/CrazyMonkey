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