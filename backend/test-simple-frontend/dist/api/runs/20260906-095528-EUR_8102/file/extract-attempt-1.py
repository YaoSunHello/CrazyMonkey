import re
from decimal import Decimal
import kit


def get_line_text(line):
    if hasattr(line, "text"):
        return line.text
    return str(line)


def parse():
    account_number = "240-149813-030"
    currency = "EUR"

    try:
        p1_text = kit.text(1)
        m_acc = re.search(r"Account number\s+([0-9-]+)", p1_text)
        if m_acc:
            account_number = m_acc.group(1).strip()
        m_curr = re.search(r"Currency\s+([A-Z]{3})", p1_text)
        if m_curr:
            currency = m_curr.group(1).strip()
    except Exception as e:
        print(f"Header extraction note: {e}")

    print(f"Account: {account_number}, Currency: {currency}")

    num_pages = kit.page_count()
    rows = []

    tx_pattern = re.compile(
        r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+([\d,.-]+)\s+([\d,.]+)\s+(\d{2}:\d{2})\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})$"
    )

    for page_num in range(1, num_pages + 1):
        lines = kit.lines(page_num)
        col_pos = kit.column_positions(page_num)
        print(f"Page {page_num} col_pos: {col_pos}")

        if isinstance(col_pos, dict):
            cols_sorted = sorted(col_pos.items(), key=lambda x: x[1])
        elif isinstance(col_pos, list):
            if len(col_pos) > 0 and isinstance(col_pos[0], dict):
                cols_sorted = []
                for item in col_pos:
                    name = (
                        item.get("text")
                        or item.get("name")
                        or item.get("column")
                    )
                    x = item.get("x") or item.get("x0") or item.get("left")
                    cols_sorted.append((name, x))
                cols_sorted.sort(key=lambda x: x[1])
            else:
                cols_sorted = sorted(col_pos, key=lambda x: x[1])
        else:
            cols_sorted = []

        col_ranges = {}
        for i, (col_name, left) in enumerate(cols_sorted):
            right = (
                cols_sorted[i + 1][1]
                if i + 1 < len(cols_sorted)
                else 99999.0
            )
            col_ranges[col_name.strip()] = (left, right)

        def get_col_val(line_obj, name):
            for k, (left, right) in col_ranges.items():
                if k.lower() == name.lower() or name.lower() in k.lower():
                    try:
                        val = line_obj.between(left, right)
                        if isinstance(val, str):
                            return val.strip()
                    except Exception:
                        pass
            return ""

        for idx, line in enumerate(lines):
            text = get_line_text(line).strip()
            if text.startswith("Bank reference") or text.startswith("Narrative"):
                continue

            m = tx_pattern.search(text)
            if not m:
                continue

            val_date_regex = m.group(1)
            raw_amt = m.group(2)
            raw_bal = m.group(3)
            time_regex = m.group(4)
            post_date_regex = m.group(5)

            prefix = text[: m.start(1)].strip()
            prefix_tokens = prefix.split()
            fallback_bank_ref = prefix_tokens[0] if prefix_tokens else "NONREF"

            bank_ref = get_col_val(line, "Bank reference")
            if not bank_ref:
                bank_ref = fallback_bank_ref

            trn_type = get_col_val(line, "TRN type")
            if not trn_type:
                if len(prefix_tokens) >= 3:
                    trn_type = " ".join(prefix_tokens[2:])
                else:
                    trn_type = prefix_tokens[-1]

            val_date = get_col_val(line, "Value date") or val_date_regex
            time_str = get_col_val(line, "Time") or time_regex
            post_date = get_col_val(line, "Post date") or post_date_regex

            cred_val = get_col_val(line, "Credit amount")
            deb_val = get_col_val(line, "Debit amount")

            if cred_val:
                credit = cred_val.replace(",", "")
                debit = None
            elif deb_val:
                debit = deb_val.replace(",", "")
                credit = None
            else:
                if raw_amt.startswith("-"):
                    debit = raw_amt.replace(",", "")
                    credit = None
                else:
                    credit = raw_amt.replace(",", "")
                    debit = None

            bal_val = get_col_val(line, "Balance")
            balance = (bal_val if bal_val else raw_bal).replace(",", "")

            narrative = ""
            for next_idx in range(idx + 1, len(lines)):
                next_text = get_line_text(lines[next_idx]).strip()
                if tx_pattern.search(next_text) and not next_text.startswith(
                    "Narrative"
                ):
                    break
                if next_text.startswith("01 Apr") or "Page " in next_text:
                    break
                if re.match(r"^\s*Narrative\b", next_text):
                    narrative = re.sub(
                        r"^\s*Narrative\s*:?\s*", "", next_text
                    ).strip()
                    break

            row = {
                "bank_reference": bank_ref,
                "trn_type": trn_type,
                "value_date": val_date,
                "post_date": post_date,
                "time": time_str,
                "narrative": narrative,
                "credit": credit,
                "debit": debit,
                "balance": balance,
                "account_number": account_number,
                "currency": currency,
                "page": page_num,
            }
            rows.append(row)

    print(f"Parsed {len(rows)} raw rows across {num_pages} pages.")

    for i in range(len(rows) - 1):
        c_bal = Decimal(rows[i]["balance"])
        amt = Decimal(
            rows[i]["credit"]
            if rows[i]["credit"] is not None
            else rows[i]["debit"]
        )
        exp_next = c_bal - amt
        act_next = Decimal(rows[i + 1]["balance"])
        if exp_next != act_next:
            print(
                f"CHAIN ERROR at {i}: bal={c_bal}, amt={amt}, exp={exp_next}, act={act_next}"
            )
        else:
            print(f"Row {i} -> {i+1} chained correctly: {exp_next}")

    kit.write_result(rows)
    print(f"parsed {len(rows)} rows")


if __name__ == "__main__":
    parse()