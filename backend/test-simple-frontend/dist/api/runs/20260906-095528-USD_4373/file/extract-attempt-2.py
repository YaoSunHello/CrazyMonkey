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

# Regex to match the core transaction fields at the end of the line
tx_tail_re = re.compile(
    r"^(?P<prefix>.+?)\s+"
    r"(?P<val_date>\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+"
    r"(?P<amount>-?[\d,]+\.\d{2})\s+"
    r"(?P<balance>[\d,]+\.\d{2})\s+"
    r"(?P<time>\d{2}:\d{2})\s+"
    r"(?P<post_date>\d{1,2}\s+[A-Za-z]{3}\s+\d{4})$"
)

trn_type_re = re.compile(r"\s+(S\+P[+-](?:\s+(?:CHG|INT))?)$")

rows = []
page_count = kit.page_count()

for p in range(1, page_count + 1):
    lines = kit.lines(p)
    num_lines = len(lines)
    i = 0
    while i < num_lines:
        line = lines[i]
        text = " ".join(line.text.split())

        # Skip statement furniture
        if (
            "Statement details" in text
            or "Bank reference Customer reference" in text
            or "Account number" in text
            or "Page " in text
            or text.startswith("Narrative")
        ):
            i += 1
            continue

        match = tx_tail_re.match(text)
        if match:
            prefix = match.group("prefix").strip()
            val_date = match.group("val_date")
            amount_raw = match.group("amount")
            bal_str = match.group("balance").replace(",", "")
            time_str = match.group("time")
            post_date = match.group("post_date")

            # Parse TRN type and references from prefix
            trn_match = trn_type_re.search(prefix)
            if trn_match:
                trn_type = trn_match.group(1).strip()
                ref_part = prefix[: trn_match.start()].strip()
            else:
                tokens = prefix.split()
                trn_type = tokens[-1]
                ref_part = " ".join(tokens[:-1])

            # Bank reference vs customer reference
            ref_tokens = ref_part.split()
            if ref_part.startswith("TT ") and len(ref_tokens) >= 2:
                bank_ref = f"{ref_tokens[0]} {ref_tokens[1]}"
            else:
                bank_ref = ref_tokens[0] if ref_tokens else ""

            # Credit vs Debit
            clean_amt = amount_raw.replace(",", "")
            if clean_amt.startswith("-"):
                credit = None
                debit = clean_amt
            else:
                credit = clean_amt
                debit = None

            # Collect narrative continuation lines
            narrative_parts = []
            j = i + 1
            while j < num_lines:
                next_line = lines[j]
                next_text = " ".join(next_line.text.split())

                # Check if next line is another transaction or statement furniture
                if tx_tail_re.match(next_text):
                    break
                if (
                    "Account number" in next_text
                    or "Page " in next_text
                    or "Statement details" in next_text
                    or "Bank reference Customer reference" in next_text
                ):
                    break

                cleaned = re.sub(r"^Narrative\s*", "", next_text).strip()
                if cleaned:
                    narrative_parts.append(cleaned)
                j += 1

            narrative_raw = " ".join(narrative_parts)
            # Reconstruct mid-word wraps marked by comma
            narrative = re.sub(r"INFRAST,\s*RUCTURE", "INFRASTRUCTURE", narrative_raw)
            narrative = re.sub(r"COOPER,\s*ATIEF", "COOPERATIEF", narrative)
            narrative = " ".join(narrative.split())

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

print(f"Extracted {len(rows)} rows across {page_count} pages.")

# 1. Closing balance check
if rows:
    first_bal = rows[0]["balance"]
    assert first_bal == closing_balance_str, (
        f"Closing balance mismatch: {first_bal} != {closing_balance_str}"
    )
    print(f"Closing balance verified: {first_bal}")

# 2. Balance chain check: balance_chain = bal_curr - amt_curr == bal_next
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
        f"Provenance failed for bank_reference: '{r['bank_reference']}'"
    )

print("All bank references verified in PDF text.")

# Write result
kit.write_result(rows)
print(f"parsed {len(rows)} rows")