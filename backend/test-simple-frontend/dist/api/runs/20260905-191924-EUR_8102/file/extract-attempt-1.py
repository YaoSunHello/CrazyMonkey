import re
import kit

# Extract account number and currency from statement header
account_number = None
currency = None

num_pages = kit.page_count()

for p in range(1, num_pages + 1):
    for line in kit.lines(p):
        if not account_number:
            m = re.search(r"Account number\s+([0-9\-]+)", line.text)
            if m:
                account_number = m.group(1).strip()
        if not currency:
            m = re.search(r"Currency\s+([A-Z]{3})", line.text)
            if m:
                currency = m.group(1).strip()

cols = kit.column_positions()


def clean_text(s):
    return re.sub(r"\s+", " ", s).strip()


def check_tx_line(line):
    # Time column must match HH:MM
    time_str = clean_text(line.between(cols["time"], cols["post_date"]))
    if not re.match(r"^\d{2}:\d{2}$", time_str):
        words = line.words_between(cols["time"] - 5, cols["post_date"])
        time_str = clean_text(" ".join(w["text"] for w in words))
        if not re.match(r"^\d{2}:\d{2}$", time_str):
            return False, None

    # Post date must match date pattern
    post_date_str = clean_text(line.between(cols["post_date"], 9999))
    if not re.search(r"\d{1,2}\s+[A-Za-z]{3}\s+\d{4}", post_date_str):
        return False, None

    # Balance must match amount pattern
    bal_str = clean_text(line.between(cols["balance"], cols["time"]))
    if not re.search(r"\d+\.\d{2}", bal_str):
        return False, None

    # Credit or debit must match amount pattern
    cred_str = clean_text(line.between(cols["credit"], cols["debit"]))
    deb_str = clean_text(line.between(cols["debit"], cols["balance"]))
    has_cred = bool(re.search(r"\d+\.\d{2}", cred_str))
    has_deb = bool(re.search(r"\d+\.\d{2}", deb_str))
    if not (has_cred or has_deb):
        return False, None

    return True, (time_str, post_date_str, bal_str, cred_str, deb_str)


rows = []
current_row = None

for p in range(1, num_pages + 1):
    for line in kit.lines(p):
        is_tx, tx_data = check_tx_line(line)
        if is_tx:
            time_str, post_date_str, bal_str, cred_str, deb_str = tx_data

            bank_ref = clean_text(line.between(0, cols["customer_reference"]))
            trn_type = clean_text(line.between(cols["trn_type"], cols["value_date"]))
            value_date = clean_text(line.between(cols["value_date"], cols["credit"]))

            credit = None
            debit = None
            if cred_str and re.search(r"\d+\.\d{2}", cred_str):
                credit = cred_str.replace(",", "")
            elif deb_str and re.search(r"\d+\.\d{2}", deb_str):
                debit = deb_str.replace(",", "")

            balance = bal_str.replace(",", "")

            if current_row is not None:
                rows.append(current_row)

            current_row = {
                "bank_reference": bank_ref,
                "trn_type": trn_type,
                "value_date": value_date,
                "post_date": post_date_str,
                "time": time_str,
                "narrative": "",
                "credit": credit,
                "debit": debit,
                "balance": balance,
                "account_number": account_number,
                "currency": currency,
                "page": p,
            }
        elif current_row is not None:
            text_strip = line.text.strip()
            if text_strip.startswith("Narrative"):
                narr_text = clean_text(re.sub(r"^Narrative\s*:?\s*", "", text_strip))
                if current_row["narrative"]:
                    current_row["narrative"] += " " + narr_text
                else:
                    current_row["narrative"] = narr_text

if current_row is not None:
    rows.append(current_row)

kit.write_result(rows)
print(f"parsed {len(rows)} rows")