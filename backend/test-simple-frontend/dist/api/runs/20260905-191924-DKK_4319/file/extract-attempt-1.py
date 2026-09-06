import re
import kit


def clean_amount(s):
    if s is None:
        return None
    return s.replace(",", "").replace(" ", "").strip()


def is_furniture(text):
    t = text.strip()
    if not t:
        return True
    if t.startswith("|") or "Statement details" in t:
        return True
    if "Balance as at close" in t or "Balance brought forward" in t:
        return True
    furniture_prefixes = (
        "Account name",
        "Account number",
        "Bank name",
        "Currency",
        "Location",
        "BIC",
        "IBAN",
        "Account status",
        "Account type",
        "Bank reference",
        "Closing ledger",
        "Closing available",
        "Current ledger",
        "Current available",
        "Specified date range",
    )
    if any(t.startswith(prefix) for prefix in furniture_prefixes):
        return True
    if "Page " in t and " of " in t:
        return True
    return False


def is_transaction_line(line, cols):
    if is_furniture(line.text):
        return False
    time_val = line.between(cols["time"], cols["post_date"]).strip()
    if not re.match(r"^\d{1,2}:\d{2}$", time_val):
        return False
    vdate_val = line.between(cols["value_date"], cols["credit"]).strip()
    if not re.search(r"\d{1,2}\s+[A-Za-z]{3}\s+\d{4}", vdate_val):
        return False
    bal_val = line.between(cols["balance"], cols["time"]).strip()
    if not re.search(r"\d", bal_val):
        return False
    return True


def main():
    cols = kit.column_positions()

    account_number = None
    currency = None

    for page_num in range(1, kit.page_count() + 1):
        for line in kit.lines(page_num):
            t = line.text
            if not account_number:
                m = re.search(r"Account number\s+([A-Za-z0-9-]+)", t)
                if m:
                    account_number = m.group(1).strip()
            if not currency:
                m = re.search(r"Currency\s+([A-Z]{3})\b", t)
                if m:
                    currency = m.group(1).strip()

    rows = []
    current_row = None

    for page_num in range(1, kit.page_count() + 1):
        for line in kit.lines(page_num):
            if is_furniture(line.text):
                continue

            if is_transaction_line(line, cols):
                bank_ref = " ".join(
                    line.between(0, cols["customer_reference"]).split()
                )
                trn_type = " ".join(
                    line.between(cols["trn_type"], cols["value_date"]).split()
                )
                value_date = " ".join(
                    line.between(cols["value_date"], cols["credit"]).split()
                )

                credit_raw = line.between(cols["credit"], cols["debit"]).strip()
                debit_raw = line.between(cols["debit"], cols["balance"]).strip()

                credit = None
                debit = None

                if credit_raw and not debit_raw:
                    credit = clean_amount(credit_raw)
                elif debit_raw and not credit_raw:
                    debit = clean_amount(debit_raw)
                elif credit_raw and debit_raw:
                    if any(c.isdigit() for c in credit_raw) and not any(
                        c.isdigit() for c in debit_raw
                    ):
                        credit = clean_amount(credit_raw)
                    elif any(c.isdigit() for c in debit_raw) and not any(
                        c.isdigit() for c in credit_raw
                    ):
                        debit = clean_amount(debit_raw)
                    elif debit_raw.startswith("-"):
                        debit = clean_amount(debit_raw)
                    else:
                        credit = clean_amount(credit_raw)
                else:
                    mid_raw = line.between(
                        cols["value_date"], cols["balance"]
                    ).strip()
                    amt_match = re.findall(r"-?[\d,]+\.\d{2}", mid_raw)
                    if amt_match:
                        amt = amt_match[-1]
                        if amt.startswith("-"):
                            debit = clean_amount(amt)
                        else:
                            credit = clean_amount(amt)

                balance_raw = line.between(cols["balance"], cols["time"]).strip()
                balance = clean_amount(balance_raw)

                time_val = " ".join(
                    line.between(cols["time"], cols["post_date"]).split()
                )
                post_date = " ".join(
                    line.between(cols["post_date"], 10000).split()
                )

                current_row = {
                    "bank_reference": bank_ref,
                    "trn_type": trn_type,
                    "value_date": value_date,
                    "post_date": post_date,
                    "time": time_val,
                    "narrative": "",
                    "credit": credit,
                    "debit": debit,
                    "balance": balance,
                    "account_number": account_number,
                    "currency": currency,
                    "page": page_num,
                }
                rows.append(current_row)
            else:
                line_str = line.text.strip()
                if line_str.startswith("Narrative"):
                    narr_text = re.sub(r"^Narrative\s*:?\s*", "", line_str)
                else:
                    narr_text = line_str

                if current_row is not None:
                    if current_row["narrative"]:
                        current_row["narrative"] += " " + narr_text
                    else:
                        current_row["narrative"] = narr_text

    kit.write_result(rows)
    print(f"parsed {len(rows)} rows")


if __name__ == "__main__":
    main()