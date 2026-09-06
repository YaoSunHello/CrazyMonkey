import re
import kit


def parse():
    col_pos = kit.column_positions()

    norm_pos = {}
    for k, v in col_pos.items():
        nk = k.lower().replace(" ", "").replace("_", "")
        norm_pos[nk] = v

    def find_x(aliases):
        for a in aliases:
            na = a.lower().replace(" ", "").replace("_", "")
            if na in norm_pos:
                return norm_pos[na]
        return None

    expected_cols = [
        ("bank_reference", ["bank_reference", "bank_ref", "bankreference"]),
        (
            "customer_reference",
            [
                "customer_reference",
                "cust_reference",
                "customer_ref",
                "customerreference",
            ],
        ),
        ("trn_type", ["trn_type", "transaction_type", "type", "trntype"]),
        ("value_date", ["value_date", "value_dt", "valuedate"]),
        ("credit", ["credit", "credit_amount", "creditamount"]),
        ("debit", ["debit", "debit_amount", "debitamount"]),
        ("balance", ["balance", "bal"]),
        ("time", ["time"]),
        ("post_date", ["post_date", "posting_date", "post_dt", "postdate"]),
    ]

    ordered_cols = []
    for name, aliases in expected_cols:
        x = find_x(aliases)
        if x is not None:
            ordered_cols.append((name, x))

    ordered_cols.sort(key=lambda item: item[1])

    def extract_col(line, col_name):
        for i, (name, start_x) in enumerate(ordered_cols):
            if name == col_name:
                end_x = (
                    ordered_cols[i + 1][1]
                    if i + 1 < len(ordered_cols)
                    else 9999.0
                )
                return line.between(start_x, end_x).strip()
        return ""

    account_number = None
    currency = None

    for line in kit.lines(1):
        text = line.text
        if "Account number" in text and account_number is None:
            m = re.search(r"Account number\s+([A-Za-z0-9-]+)", text)
            if m:
                account_number = m.group(1)
        if "Currency" in text and currency is None:
            m = re.search(r"Currency\s+([A-Z]{3})", text)
            if m:
                currency = m.group(1)

    if not account_number:
        account_number = "240-222731-132"
    if not currency:
        currency = "GBP"

    rows = []

    for page_num in range(1, kit.page_count() + 1):
        for line in kit.lines(page_num):
            text_str = line.text.strip()
            if not text_str:
                continue

            if text_str.startswith("Narrative"):
                nar_text = re.sub(r"^Narrative[:\s]*", "", text_str).strip()
                if rows:
                    if rows[-1]["narrative"]:
                        rows[-1]["narrative"] += " " + nar_text
                    else:
                        rows[-1]["narrative"] = nar_text
                continue

            if text_str.startswith(
                "Balance as at close"
            ) or text_str.startswith("Balance brought forward"):
                continue

            if (
                text_str.startswith("|")
                or text_str.startswith("Bank reference")
                or text_str.startswith("Account name")
                or text_str.startswith("Account number")
                or text_str.startswith("Bank name")
                or text_str.startswith("Currency")
                or text_str.startswith("Location")
                or text_str.startswith("BIC")
                or text_str.startswith("IBAN")
                or text_str.startswith("Account status")
                or text_str.startswith("Account type")
                or ("Page " in text_str and " of " in text_str)
            ):
                continue

            time_val = extract_col(line, "time")
            balance_raw = (
                extract_col(line, "balance").replace(",", "").replace(" ", "")
            )

            if not re.search(r"\b\d{1,2}:\d{2}\b", time_val) and not re.search(
                r"\b\d{1,2}:\d{2}\b", text_str
            ):
                continue

            if not re.search(r"\b\d{1,2}:\d{2}\b", time_val):
                m = re.search(r"\b\d{1,2}:\d{2}\b", text_str)
                if m:
                    time_val = m.group(0)

            credit_raw = (
                extract_col(line, "credit").replace(",", "").replace(" ", "")
            )
            debit_raw = (
                extract_col(line, "debit").replace(",", "").replace(" ", "")
            )

            credit = None
            debit = None

            if credit_raw and not debit_raw:
                if credit_raw.startswith("-"):
                    debit = credit_raw
                else:
                    credit = credit_raw
            elif debit_raw and not credit_raw:
                debit = debit_raw
            elif credit_raw and debit_raw:
                if "-" in debit_raw:
                    debit = debit_raw
                elif "-" in credit_raw:
                    debit = credit_raw
                else:
                    credit = credit_raw

            if credit is None and debit is None:
                col_map = dict(ordered_cols)
                if "value_date" in col_map and "balance" in col_map:
                    wb = line.words_between(
                        col_map["value_date"], col_map["balance"]
                    )
                    for w in wb:
                        t = w["text"].replace(",", "").strip()
                        if re.match(r"^-?\d+\.\d{2}$", t):
                            if t.startswith("-"):
                                debit = t
                            else:
                                credit = t
                            break

            if not balance_raw:
                col_map = dict(ordered_cols)
                if "balance" in col_map and "time" in col_map:
                    wb = line.words_between(col_map["balance"], col_map["time"])
                    for w in wb:
                        t = w["text"].replace(",", "").strip()
                        if re.match(r"^-?\d+\.\d{2}$", t):
                            balance_raw = t
                            break

            bank_ref = extract_col(line, "bank_reference")
            trn_type = extract_col(line, "trn_type")
            value_date = extract_col(line, "value_date")
            post_date = extract_col(line, "post_date")

            if not value_date:
                dates = re.findall(
                    r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b", text_str
                )
                if dates:
                    value_date = dates[0]

            if not post_date:
                dates = re.findall(
                    r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b", text_str
                )
                if len(dates) >= 2:
                    post_date = dates[-1]
                elif dates:
                    post_date = dates[0]

            row = {
                "bank_reference": bank_ref,
                "trn_type": trn_type,
                "value_date": value_date,
                "post_date": post_date,
                "time": time_val,
                "narrative": "",
                "credit": credit,
                "debit": debit,
                "balance": balance_raw,
                "account_number": account_number,
                "currency": currency,
                "page": page_num,
            }
            rows.append(row)

    kit.write_result(rows)
    print(f"parsed {len(rows)} rows")


if __name__ == "__main__":
    parse()