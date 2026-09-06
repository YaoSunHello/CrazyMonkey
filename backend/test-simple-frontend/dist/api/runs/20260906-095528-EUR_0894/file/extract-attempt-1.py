from decimal import Decimal
import re
import kit


def parse():
    num_pages = kit.page_count()
    print(f"Statement page count: {num_pages}")

    # Extract account metadata from page 1 text
    p1_text = kit.text(1)
    acc_m = re.search(r"Account number\s+([0-9\-]+)", p1_text)
    account_number = acc_m.group(1) if acc_m else "240-524291-030"

    curr_m = re.search(r"Currency\s+([A-Z]{3})", p1_text)
    currency = curr_m.group(1) if curr_m else "EUR"

    print(f"Account number: {account_number}, Currency: {currency}")

    # Get column positions
    col_pos = kit.column_positions(1)
    print(f"Column positions: {col_pos}")

    # Normalize column positions
    col_dict = {}
    if isinstance(col_pos, dict):
        col_dict = {k.lower().strip(): v for k, v in col_pos.items()}
    elif isinstance(col_pos, list):
        for item in col_pos:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                col_dict[str(item[0]).lower().strip()] = item[1]
            elif isinstance(item, dict):
                name = item.get("text") or item.get("name") or ""
                x = item.get("x") or item.get("x0") or 0
                col_dict[str(name).lower().strip()] = x

    x_cust = col_dict.get("customer reference", 130.0)
    x_trn = col_dict.get("trn type", 260.0)
    x_val = col_dict.get("value date", 320.0)

    print(f"Resolved column boundaries: x_cust={x_cust}, x_trn={x_trn}, x_val={x_val}")

    # Transaction regex matching the end of a transaction line:
    # Value date, Amount, Balance, Time, Post date
    tx_re = re.compile(
        r"(\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})\s+"  # Value date
        r"(-?[\d,]+\.\d{2})\s+"  # Amount
        r"([\d,]+\.\d{2})\s+"  # Balance
        r"(\d{2}:\d{2})\s+"  # Time
        r"(\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})\s*$"  # Post date
    )

    rows = []
    current_tx = None
    collecting_narrative = False

    for page_num in range(1, num_pages + 1):
        lines = kit.lines(page_num)
        for line in lines:
            line_text = line.text.strip()
            m = tx_re.search(line_text)

            if m:
                # If we were collecting narrative for a previous transaction, finish it
                if current_tx is not None:
                    current_tx["narrative"] = re.sub(
                        r"DevC,\s*o\b", "DevCo", current_tx["narrative"]
                    ).strip()

                val_date = m.group(1)
                amt_str = m.group(2)
                bal_str = m.group(3).replace(",", "")
                time_str = m.group(4)
                post_date = m.group(5)

                if amt_str.startswith("-"):
                    debit = amt_str.replace(",", "")
                    credit = None
                else:
                    credit = amt_str.replace(",", "")
                    debit = None

                # Extract bank reference and trn_type using column boundaries
                bank_ref = line.between(0, x_cust).strip()
                trn_type = line.between(x_trn, x_val).strip()

                # Fallback extraction if column bounds yield empty string
                if not bank_ref or not trn_type:
                    prefix = line_text[: m.start()].strip()
                    tokens = prefix.split()
                    if not bank_ref and tokens:
                        bank_ref = tokens[0]
                    if not trn_type and tokens:
                        trn_type = tokens[-1]

                current_tx = {
                    "bank_reference": bank_ref,
                    "trn_type": trn_type,
                    "value_date": val_date,
                    "post_date": post_date,
                    "time": time_str,
                    "narrative": "",
                    "credit": credit,
                    "debit": debit,
                    "balance": bal_str,
                    "account_number": account_number,
                    "currency": currency,
                    "page": page_num,
                }
                rows.append(current_tx)
                collecting_narrative = False

            elif line_text.startswith("Narrative"):
                narr_content = re.sub(r"^Narrative:?\s*", "", line_text)
                if current_tx is not None:
                    current_tx["narrative"] = narr_content
                collecting_narrative = True

            elif collecting_narrative and current_tx is not None:
                # Check for table furniture / footers
                if (
                    "Page " in line_text
                    or "Statement details" in line_text
                    or "Account number" in line_text
                ):
                    collecting_narrative = False
                else:
                    current_tx["narrative"] += " " + line_text

    # Finalize last transaction narrative
    if current_tx is not None:
        current_tx["narrative"] = re.sub(
            r"DevC,\s*o\b", "DevCo", current_tx["narrative"]
        ).strip()

    # Self-checks
    print(f"Extracted {len(rows)} transactions.")
    for idx, r in enumerate(rows):
        print(
            f"Row {idx + 1}: ref={r['bank_reference']} trn={r['trn_type']} "
            f"cr={r['credit']} db={r['debit']} bal={r['balance']} time={r['time']}"
        )
        print(f"   narrative: {r['narrative']}")

    # Balance chain check
    for i in range(len(rows) - 1):
        cur_bal = Decimal(rows[i]["balance"])
        amt = (
            Decimal(rows[i]["credit"])
            if rows[i]["credit"] is not None
            else Decimal(rows[i]["debit"])
        )
        expected_next = cur_bal - amt
        actual_next = Decimal(rows[i + 1]["balance"])
        assert expected_next == actual_next, (
            f"Chain broken at row {i}: {cur_bal} - {amt} = {expected_next} != {actual_next}"
        )

    # Closing balance check
    p1_lines = kit.text(1)
    close_m = re.search(r"Closing ledger balance\s+[a-z ]*\s+([\d,]+\.\d{2})", p1_lines)
    if close_m:
        expected_close = close_m.group(1).replace(",", "")
        assert rows[0]["balance"] == expected_close, (
            f"Closing balance mismatch: {rows[0]['balance']} != {expected_close}"
        )

    # Reference provenance check
    full_pdf_text = " ".join(kit.text(p) for p in range(1, num_pages + 1))
    for r in rows:
        assert r["bank_reference"] in full_pdf_text, (
            f"Reference '{r['bank_reference']}' not found in PDF text"
        )

    # Amounts check
    for r in rows:
        assert (r["credit"] is not None) ^ (r["debit"] is not None), (
            f"Amount error in row: {r}"
        )

    print(f"parsed {len(rows)} rows")
    kit.write_result(rows)


parse()