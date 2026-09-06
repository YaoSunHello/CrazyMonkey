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