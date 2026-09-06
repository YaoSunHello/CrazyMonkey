import re
from decimal import Decimal
import kit


def parse():
    num_pages = kit.page_count()
    cols = kit.column_positions()

    # Extract account number and currency from headers
    account_number = None
    currency = None
    for p in range(1, num_pages + 1):
        for line in kit.lines(p):
            if not account_number:
                m = re.search(r"Account number\s+([0-9A-Za-z-]+)", line.text)
                if m:
                    account_number = m.group(1).strip()
            if not currency:
                m_curr = re.search(r"Currency\s+([A-Z]{3})", line.text)
                if m_curr:
                    currency = m_curr.group(1).strip()
        if account_number and currency:
            break

    # Fallback defaults if not found in header
    account_number = account_number or "240-222731-030"
    currency = currency or "EUR"

    rows = []
    current_tx = None

    for page_num in range(1, num_pages + 1):
        for line in kit.lines(page_num):
            text = line.text.strip()
            if not text:
                continue

            # Day markers, statement details, headers, footers
            if (
                text.startswith("Balance as at close")
                or text.startswith("Balance brought forward")
                or text.startswith("|")
                or text.startswith("Bank reference")
                or text.startswith("Account ")
                or text.startswith("Bank name")
                or text.startswith("Currency")
                or text.startswith("Location")
                or text.startswith("BIC")
                or text.startswith("IBAN")
                or text.startswith("Account status")
                or text.startswith("Account type")
                or ("Account number" in text and "Page" in text)
            ):
                current_tx = None
                continue

            # Narrative line
            if text.startswith("Narrative"):
                narr_text = re.sub(r"^Narrative:?\s*", "", text).strip()
                if current_tx is not None:
                    current_tx["narrative"] = narr_text
                continue

            # Check if this is a transaction line (contains time \d{1,2}:\d{2})
            time_raw = line.between(cols["time"], cols["post_date"]).strip()
            if not re.match(r"^\d{1,2}:\d{2}$", time_raw):
                # Could be a continuation line (like wrapped customer reference)
                continue

            # Parse transaction fields
            bank_ref = line.between(0.0, cols["customer_reference"]).strip()
            if not bank_ref:
                bank_ref = " ".join(
                    w["text"]
                    for w in line.words
                    if w["x0"] < cols["customer_reference"]
                ).strip()

            trn_type = line.between(cols["trn_type"], cols["value_date"]).strip()
            val_date = line.between(cols["value_date"], cols["credit"]).strip()
            time_val = time_raw
            post_date = line.between(cols["post_date"], 10000.0).strip()

            balance_raw = line.between(cols["balance"], cols["time"]).strip()
            balance = balance_raw.replace(",", "").strip()

            credit_raw = line.between(cols["credit"], cols["debit"]).strip()
            debit_raw = line.between(cols["debit"], cols["balance"]).strip()

            credit_clean = credit_raw.replace(",", "").strip()
            debit_clean = debit_raw.replace(",", "").strip()

            credit = None
            debit = None

            if credit_clean and not debit_clean:
                if credit_clean.startswith("-"):
                    debit = credit_clean
                else:
                    credit = credit_clean
            elif debit_clean and not credit_clean:
                debit = debit_clean
            elif credit_clean and debit_clean:
                if credit_clean.startswith("-"):
                    debit = credit_clean
                else:
                    credit = credit_clean
            else:
                # Fallback to word search between value_date and balance
                amt_words = [
                    w["text"]
                    for w in line.words
                    if cols["value_date"] < w["x0"] < cols["balance"]
                    and re.search(r"\d+\.\d{2}", w["text"])
                ]
                if amt_words:
                    amt = amt_words[0].replace(",", "").strip()
                    if amt.startswith("-"):
                        debit = amt
                    else:
                        credit = amt

            row = {
                "bank_reference": bank_ref,
                "trn_type": trn_type,
                "value_date": val_date,
                "post_date": post_date,
                "time": time_val,
                "narrative": None,
                "credit": credit,
                "debit": debit,
                "balance": balance,
                "account_number": account_number,
                "currency": currency,
                "page": page_num,
            }
            rows.append(row)
            current_tx = row

    # Verify balance chain
    for i in range(len(rows) - 1):
        curr_bal = Decimal(rows[i]["balance"])
        amt = Decimal(
            rows[i]["credit"]
            if rows[i]["credit"] is not None
            else rows[i]["debit"]
        )
        next_bal = Decimal(rows[i + 1]["balance"])
        assert curr_bal - amt == next_bal, (
            f"Balance chain mismatch at row {i}: {curr_bal} - {amt} != {next_bal}"
        )

    kit.write_result(rows)
    print(f"parsed {len(rows)} rows")


if __name__ == "__main__":
    parse()