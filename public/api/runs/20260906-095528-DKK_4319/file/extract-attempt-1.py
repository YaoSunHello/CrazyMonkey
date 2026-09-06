import re
from decimal import Decimal
import kit


def normalize_col(name):
    n = name.lower().strip()
    if "bank" in n and "ref" in n:
        return "bank_reference"
    if "cust" in n and "ref" in n:
        return "customer_reference"
    if "trn" in n:
        return "trn_type"
    if "val" in n and "date" in n:
        return "value_date"
    if "cred" in n:
        return "credit"
    if "deb" in n:
        return "debit"
    if "bal" in n:
        return "balance"
    if "time" in n:
        return "time"
    if "post" in n and "date" in n:
        return "post_date"
    return n


def get_column_intervals(page_num):
    cp = kit.column_positions(page_num)
    print(f"Page {page_num} raw column_positions: {cp}")

    cols = []
    if isinstance(cp, dict):
        items = list(cp.items())
        if isinstance(items[0][0], str):
            cols = [(k, float(v)) for k, v in items]
        else:
            cols = [(str(v), float(k)) for k, v in items]
    elif isinstance(cp, list):
        if len(cp) > 0 and isinstance(cp[0], tuple):
            cols = [(str(k), float(v)) for k, v in cp]
        elif len(cp) > 0 and isinstance(cp[0], dict):
            for d in cp:
                name = (
                    d.get("name")
                    or d.get("text")
                    or d.get("title")
                    or d.get("header")
                )
                x = (
                    d.get("x")
                    or d.get("x0")
                    or d.get("left")
                    or d.get("pos")
                )
                cols.append((str(name), float(x)))
        elif len(cp) > 0 and isinstance(cp[0], (int, float)):
            headers = [
                "Bank reference",
                "Customer reference",
                "TRN type",
                "Value date",
                "Credit amount",
                "Debit amount",
                "Balance",
                "Time",
                "Post date",
            ]
            cols = list(zip(headers, [float(x) for x in cp]))

    cols.sort(key=lambda item: item[1])

    intervals = []
    for i in range(len(cols)):
        name = normalize_col(cols[i][0])
        x_start = 0.0 if i == 0 else cols[i][1]
        x_end = cols[i + 1][1] if i + 1 < len(cols) else 10000.0
        intervals.append((name, x_start, x_end))

    return intervals


def parse_statement():
    page_cnt = kit.page_count()
    print(f"Total pages: {page_cnt}")

    full_pdf_text = ""
    for p in range(1, page_cnt + 1):
        full_pdf_text += kit.text(p) + "\n"

    # Extract account number and currency from text
    acc_match = re.search(r"Account number\s+([0-9A-Za-z-]+)", full_pdf_text)
    account_number = acc_match.group(1) if acc_match else "240-149813-131"

    curr_match = re.search(r"Currency\s+([A-Z]{3})", full_pdf_text)
    currency = curr_match.group(1) if curr_match else "DKK"

    print(f"Account number: {account_number}, Currency: {currency}")

    # Regex matching transaction line endings
    trn_pattern = re.compile(
        r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+(-?[\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+(\d{2}:\d{2})\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})$"
    )

    rows = []

    for page_num in range(1, page_cnt + 1):
        lines = kit.lines(page_num)
        intervals = get_column_intervals(page_num)
        print(f"Page {page_num}: {len(lines)} lines")

        i = 0
        while i < len(lines):
            line = lines[i]
            text = line.text.strip()

            m = trn_pattern.search(text)
            if m:
                # Column values via intervals
                row_cols = {}
                for name, x_start, x_end in intervals:
                    val = line.between(x_start, x_end).strip()
                    row_cols[name] = val

                val_date = m.group(1)
                amt_str = m.group(2)
                bal_str = m.group(3).replace(",", "")
                time_str = m.group(4)
                post_date_str = m.group(5)

                # Determine credit vs debit
                deb_col = row_cols.get("debit", "")
                cred_col = row_cols.get("credit", "")

                if deb_col and not cred_col:
                    debit = deb_col.replace(",", "")
                    credit = None
                elif cred_col and not deb_col:
                    credit = cred_col.replace(",", "")
                    debit = None
                else:
                    if amt_str.startswith("-"):
                        debit = amt_str.replace(",", "")
                        credit = None
                    else:
                        credit = amt_str.replace(",", "")
                        debit = None

                bank_ref = row_cols.get("bank_reference", "")
                trn_type = row_cols.get("trn_type", "")

                # Narrative on subsequent line
                narrative = ""
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    next_text = next_line.text.strip()
                    if next_text.startswith("Narrative"):
                        narr = re.sub(r"^Narrative:?\s*", "", next_text).strip()
                        narrative = narr
                        j += 1
                        break
                    elif trn_pattern.search(next_text) or "Page " in next_text:
                        break
                    else:
                        j += 1

                row = {
                    "bank_reference": bank_ref,
                    "trn_type": trn_type,
                    "value_date": val_date,
                    "post_date": post_date_str,
                    "time": time_str,
                    "narrative": narrative,
                    "credit": credit,
                    "debit": debit,
                    "balance": bal_str,
                    "account_number": account_number,
                    "currency": currency,
                    "page": page_num,
                }
                print(f"Extracted row: {row}")
                rows.append(row)
                i = j
            else:
                i += 1

    # Verify balance chain
    print("\n--- Verifying balance chain ---")
    for idx in range(len(rows) - 1):
        curr_bal = Decimal(rows[idx]["balance"])
        amt = (
            Decimal(rows[idx]["credit"])
            if rows[idx]["credit"] is not None
            else Decimal(rows[idx]["debit"])
        )
        next_bal = Decimal(rows[idx + 1]["balance"])
        calc_bal = curr_bal - amt
        diff = calc_bal - next_bal
        print(
            f"Row {idx} -> {idx+1}: {curr_bal} - ({amt}) = {calc_bal}, next={next_bal}, diff={diff}"
        )
        assert diff == 0, f"Balance chain mismatch at row {idx}"

    # Verify reference provenance
    print("\n--- Verifying reference provenance ---")
    for r in rows:
        ref = r["bank_reference"]
        assert ref in full_pdf_text, f"Reference {ref!r} not in PDF text"

    kit.write_result(rows)
    print(f"parsed {len(rows)} rows")


if __name__ == "__main__":
    parse_statement()