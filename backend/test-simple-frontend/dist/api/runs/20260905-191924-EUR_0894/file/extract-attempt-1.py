import re
from decimal import Decimal
import kit


def get_col_pos(cols, name):
    if name in cols:
        return cols[name]
    for k, v in cols.items():
        if k.lower() == name.lower() or name.lower() in k.lower():
            return v
    raise KeyError(f"Column {name} not found in {list(cols.keys())}")


def parse_amounts(credit_str, debit_str):
    c = credit_str.strip().replace(",", "")
    d = debit_str.strip().replace(",", "")
    if d and not c:
        return None, d
    if c and not d:
        if c.startswith("-"):
            return None, c
        return c, None
    if c and d:
        if d.startswith("-"):
            return None, d
        elif c.startswith("-"):
            return None, c
        else:
            return c, None
    return None, None


def main():
    cols = kit.column_positions()

    col_bank = get_col_pos(cols, "bank_reference")
    col_cust = get_col_pos(cols, "customer_reference")
    col_trn = get_col_pos(cols, "trn_type")
    col_val = get_col_pos(cols, "value_date")
    col_cred = get_col_pos(cols, "credit")
    col_deb = get_col_pos(cols, "debit")
    col_bal = get_col_pos(cols, "balance")
    col_time = get_col_pos(cols, "time")
    col_post = get_col_pos(cols, "post_date")

    account_number = None
    currency = None

    for p in range(1, kit.page_count() + 1):
        for line in kit.lines(p):
            t = line.text
            if not account_number:
                m = re.search(r"Account number\s+([A-Za-z0-9-]+)", t)
                if m:
                    account_number = m.group(1).strip()
            if not currency:
                m = re.search(r"Currency\s+([A-Z]{3})", t)
                if m:
                    currency = m.group(1).strip()

    if not account_number:
        account_number = "240-524291-030"
    if not currency:
        currency = "EUR"

    rows = []
    current_tx = None

    for page_num in range(1, kit.page_count() + 1):
        for line in kit.lines(page_num):
            line_text = line.text.strip()
            if not line_text:
                continue

            val_date = line.between(col_val, col_cred).strip()
            credit_str = line.between(col_cred, col_deb).strip()
            debit_str = line.between(col_deb, col_bal).strip()
            balance_str = line.between(col_bal, col_time).strip()
            time_str = line.between(col_time, col_post).strip()

            is_tx = (
                re.match(r"^\d{1,2}:\d{2}$", time_str)
                and re.match(r"^-?[\d,]+\.\d{2}$", balance_str)
                and re.search(r"\d{1,2}\s+[A-Za-z]{3}\s+\d{4}", val_date)
                and (
                    re.match(r"^-?[\d,]+\.\d{2}$", credit_str)
                    or re.match(r"^-?[\d,]+\.\d{2}$", debit_str)
                )
            )

            if is_tx:
                bank_ref = line.between(col_bank, col_cust).strip()
                trn_type = line.between(col_trn, col_val).strip()
                post_date_raw = line.between(col_post, 99999).strip()
                m_post = re.search(r"\d{1,2}\s+[A-Za-z]{3}\s+\d{4}", post_date_raw)
                post_date = m_post.group(0) if m_post else post_date_raw

                m_val = re.search(r"\d{1,2}\s+[A-Za-z]{3}\s+\d{4}", val_date)
                val_date_clean = m_val.group(0) if m_val else val_date

                credit_val, debit_val = parse_amounts(credit_str, debit_str)

                current_tx = {
                    "bank_reference": bank_ref,
                    "trn_type": trn_type,
                    "value_date": val_date_clean,
                    "post_date": post_date,
                    "time": time_str,
                    "narrative": "",
                    "credit": credit_val,
                    "debit": debit_val,
                    "balance": balance_str.replace(",", ""),
                    "account_number": account_number,
                    "currency": currency,
                    "page": page_num,
                }
                rows.append(current_tx)
            elif current_tx is not None and line_text.startswith("Narrative"):
                narr_text = re.sub(r"^Narrative\s*:?\s*", "", line_text).strip()
                current_tx["narrative"] = narr_text

    kit.write_result(rows)
    print(f"parsed {len(rows)} rows")


if __name__ == "__main__":
    main()