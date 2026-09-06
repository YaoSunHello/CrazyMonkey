import re
import kit


def clean_amount(val):
    if not val:
        return None
    val = val.strip().replace(",", "")
    if not any(c.isdigit() for c in val):
        return None
    return val


def main():
    # 1. Extract statement-level metadata: account number and currency
    account_number = None
    currency = None

    for p in range(1, kit.page_count() + 1):
        for line in kit.lines(p):
            if not account_number:
                m = re.search(r"Account number\s+([A-Za-z0-9\-]+)", line.text)
                if m:
                    account_number = m.group(1)
            if not currency:
                m = re.search(r"Currency\s+([A-Z]{3})", line.text)
                if m:
                    currency = m.group(1)
        if account_number and currency:
            break

    # 2. Determine column boundaries from kit.column_positions()
    raw_col_positions = kit.column_positions()
    sorted_cols = sorted(raw_col_positions.items(), key=lambda x: x[1])

    col_bounds = {}
    for i, (name, x0) in enumerate(sorted_cols):
        left = 0.0 if i == 0 else x0
        right = sorted_cols[i + 1][1] if i + 1 < len(sorted_cols) else 999999.0
        col_bounds[name] = (left, right)

    def get_col(line, name):
        left, right = col_bounds[name]
        return line.between(left, right).strip()

    furniture_prefixes = (
        "| Statement details",
        "Statement details",
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
    )

    rows = []

    # 3. Iterate pages and lines
    for page_num in range(1, kit.page_count() + 1):
        for line in kit.lines(page_num):
            text_stripped = line.text.strip()
            if not text_stripped:
                continue

            # Check for narrative continuation line
            if text_stripped.startswith("Narrative"):
                narrative_text = re.sub(r"^Narrative\s*:?\s*", "", text_stripped)
                if rows:
                    if rows[-1]["narrative"]:
                        rows[-1]["narrative"] += " " + narrative_text
                    else:
                        rows[-1]["narrative"] = narrative_text
                continue

            # Day markers
            if "Balance as at close" in line.text or "Balance brought forward" in line.text:
                continue

            # Header and furniture lines
            if any(text_stripped.startswith(p) for p in furniture_prefixes):
                continue
            if re.search(r"Page\s+\d+\s+of\s+\d+", line.text):
                continue

            # Transaction columns extraction
            time_val = get_col(line, "time")
            if not re.search(r"\b\d{2}:\d{2}\b", time_val):
                continue

            balance_val = clean_amount(get_col(line, "balance"))
            if not balance_val:
                continue

            # Extract amounts
            c_val = clean_amount(get_col(line, "credit"))
            d_val = clean_amount(get_col(line, "debit"))

            if c_val and not d_val:
                if c_val.startswith("-"):
                    credit = None
                    debit = c_val
                else:
                    credit = c_val
                    debit = None
            elif d_val and not c_val:
                credit = None
                debit = d_val
            elif c_val and d_val:
                if d_val.startswith("-"):
                    credit = None
                    debit = d_val
                else:
                    credit = c_val
                    debit = None
            else:
                amt_str = clean_amount(
                    line.between(col_bounds["credit"][0], col_bounds["balance"][0])
                )
                if amt_str:
                    if amt_str.startswith("-"):
                        credit = None
                        debit = amt_str
                    else:
                        credit = amt_str
                        debit = None
                else:
                    continue

            bank_ref = " ".join(get_col(line, "bank_reference").split())
            trn_type = " ".join(get_col(line, "trn_type").split())
            value_date = " ".join(get_col(line, "value_date").split())
            post_date = " ".join(get_col(line, "post_date").split())
            time_str = " ".join(time_val.split())

            row = {
                "bank_reference": bank_ref,
                "trn_type": trn_type,
                "value_date": value_date,
                "post_date": post_date,
                "time": time_str,
                "narrative": "",
                "credit": credit,
                "debit": debit,
                "balance": balance_val,
                "account_number": account_number,
                "currency": currency,
                "page": page_num,
            }
            rows.append(row)

    kit.write_result(rows)
    print(f"parsed {len(rows)} rows")


if __name__ == "__main__":
    main()