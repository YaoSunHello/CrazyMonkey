from decimal import Decimal
import re
import kit


def is_furniture(text):
    t = text.strip()
    if not t or t == "|":
        return True
    if t.startswith("| Statement details") or t.startswith("Statement details"):
        return True
    if any(
        t.startswith(prefix)
        for prefix in [
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
        ]
    ):
        return True
    if "Page " in t and " of " in t:
        return True
    if "Balance as at close" in t or "Balance brought forward" in t:
        return True
    return False


def is_transaction_line(line, cols):
    time_val = line.between(cols["time"], cols["post_date"]).strip()
    post_date_val = line.between(cols["post_date"], 10000).strip()
    balance_val = line.between(cols["balance"], cols["time"]).strip()

    if not re.search(r"^\d{2}:\d{2}$", time_val):
        return False
    if not re.search(r"^\d{1,2}\s+[A-Za-z]{3}\s+\d{4}$", post_date_val):
        return False
    if not re.search(r"^-?[\d,]+\.\d{2}$", balance_val):
        return False
    return True


def parse_statement():
    cols = kit.column_positions()

    account_number = "240-644826-130"
    currency = "USD"

    # Extract account metadata from statement details
    for page_num in range(1, kit.page_count() + 1):
        for line in kit.lines(page_num):
            t = line.text.strip()
            m_acc = re.search(r"Account number\s+([0-9-]+)", t)
            if m_acc:
                account_number = m_acc.group(1).strip()
            m_curr = re.search(r"Currency\s+([A-Z]{3})", t)
            if m_curr:
                currency = m_curr.group(1).strip()

    rows = []
    current_row = None

    for page_num in range(1, kit.page_count() + 1):
        for line in kit.lines(page_num):
            if is_transaction_line(line, cols):
                time_val = line.between(cols["time"], cols["post_date"]).strip()
                post_date_val = line.between(cols["post_date"], 10000).strip()
                balance_val = (
                    line.between(cols["balance"], cols["time"])
                    .replace(",", "")
                    .strip()
                )
                value_date_val = line.between(
                    cols["value_date"], cols["credit"]
                ).strip()
                trn_type_val = line.between(
                    cols["trn_type"], cols["value_date"]
                ).strip()

                bank_ref = line.between(0, cols["customer_reference"]).strip()

                credit_raw = line.between(cols["credit"], cols["debit"]).strip()
                debit_raw = line.between(
                    cols["debit"], cols["balance"]
                ).strip()

                if credit_raw and not debit_raw:
                    cleaned = credit_raw.replace(",", "").strip()
                    if cleaned.startswith("-"):
                        credit, debit = None, cleaned
                    else:
                        credit, debit = cleaned, None
                elif debit_raw and not credit_raw:
                    cleaned = debit_raw.replace(",", "").strip()
                    if cleaned.startswith("-"):
                        credit, debit = None, cleaned
                    else:
                        credit, debit = None, cleaned
                else:
                    combined = (
                        credit_raw
                        or debit_raw
                        or line.between(cols["credit"], cols["balance"])
                    ).strip()
                    cleaned = combined.replace(",", "").strip()
                    if cleaned.startswith("-"):
                        credit, debit = None, cleaned
                    else:
                        credit, debit = cleaned, None

                row = {
                    "bank_reference": bank_ref,
                    "trn_type": trn_type_val,
                    "value_date": value_date_val,
                    "post_date": post_date_val,
                    "time": time_val,
                    "narrative": "",
                    "credit": credit,
                    "debit": debit,
                    "balance": balance_val,
                    "account_number": account_number,
                    "currency": currency,
                    "page": page_num,
                }
                rows.append(row)
                current_row = row
            else:
                text = line.text.strip()
                if is_furniture(text):
                    continue
                if text.startswith("Narrative"):
                    narrative_text = text[len("Narrative") :].lstrip(": ")
                    if current_row is not None:
                        current_row["narrative"] = narrative_text
                elif current_row is not None and current_row["narrative"]:
                    current_row["narrative"] += " " + text

    # Verify chain integrity
    for i in range(len(rows) - 1):
        b_curr = Decimal(rows[i]["balance"])
        amt_curr = Decimal(rows[i]["credit"] or rows[i]["debit"])
        b_next = Decimal(rows[i + 1]["balance"])
        assert b_curr - amt_curr == b_next, (
            f"Chain broken at index {i}: {b_curr} - {amt_curr} != {b_next}"
        )

    for r in rows:
        assert (r["credit"] is None) ^ (r["debit"] is None)

    kit.write_result(rows)
    print(f"parsed {len(rows)} rows")


parse_statement()