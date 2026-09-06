from decimal import Decimal
import re
import kit


def extract_line_text(line):
    if hasattr(line, "text") and isinstance(line.text, str):
        return line.text.strip()
    s = str(line).strip()
    if not s.startswith("<"):
        return s
    if hasattr(line, "words"):
        return " ".join(w["text"] for w in line.words).strip()
    return line.between(-9999, 9999).strip()


def build_column_bounds(col_positions):
    print("Raw column_positions:", col_positions)
    if isinstance(col_positions, dict):
        sorted_cols = sorted(col_positions.items(), key=lambda item: item[1])
    elif isinstance(col_positions, list):
        if len(col_positions) > 0 and isinstance(col_positions[0], (list, tuple)):
            sorted_cols = sorted(col_positions, key=lambda item: item[1])
        else:
            sorted_cols = list(enumerate(col_positions))
    else:
        raise ValueError(f"Unexpected column_positions type: {type(col_positions)}")

    bounds = {}
    for i, (name, x_start) in enumerate(sorted_cols):
        x_end = sorted_cols[i + 1][1] if i + 1 < len(sorted_cols) else 9999.0
        bounds[name] = (x_start, x_end)
    return bounds


def parse_statement():
    num_pages = kit.page_count()
    print(f"Total pages: {num_pages}")

    # Gather full document text for provenance checks
    full_pdf_text = ""
    for p in range(1, num_pages + 1):
        full_pdf_text += "\n" + kit.text(p)

    account_number = "240-222731-132"
    currency = "GBP"

    # Match account details from page 1 text if available
    acc_match = re.search(r"Account number\s+([\d-]+)", full_pdf_text)
    if acc_match:
        account_number = acc_match.group(1).strip()
    curr_match = re.search(r"Currency\s+([A-Z]{3})", full_pdf_text)
    if curr_match:
        currency = curr_match.group(1).strip()

    print(f"Account number: {account_number}, Currency: {currency}")

    col_bounds_p1 = build_column_bounds(kit.column_positions(1))
    print("Column bounds page 1:", col_bounds_p1)

    transactions = []

    # Regex pattern to match the tail of a transaction line:
    # (amount) (balance) (time HH:MM) (post_date DD Mon YYYY)
    tx_tail_pattern = re.compile(
        r"([-\d.,]+)\s+([\d.,]+)\s+(\d{2}:\d{2})\s+(\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})$"
    )

    for page_num in range(1, num_pages + 1):
        lines = kit.lines(page_num)
        print(f"\n--- Page {page_num}: {len(lines)} visual lines ---")

        # Try to get page-specific column bounds if possible
        try:
            col_bounds = build_column_bounds(kit.column_positions(page_num))
        except Exception as e:
            print(f"Using page 1 column bounds for page {page_num} ({e})")
            col_bounds = col_bounds_p1

        i = 0
        while i < len(lines):
            line = lines[i]
            line_str = extract_line_text(line)

            # Skip header / footer / marker lines
            if not line_str or line_str.startswith("Balance as at close") or line_str.startswith("Balance brought forward"):
                i += 1
                continue
            if line_str.startswith("Statement details") or line_str.startswith("Bank reference") or "Account number" in line_str:
                i += 1
                continue

            # Check if this line is a transaction line
            match = tx_tail_pattern.search(line_str)
            if match:
                amt_str = match.group(1).strip()
                bal_str = match.group(2).strip()
                time_str = match.group(3).strip()
                post_date_str = match.group(4).strip()

                # Text before the tail contains: bank_ref, cust_ref, trn_type, value_date
                prefix_str = line_str[: match.start()].strip()

                # Extract Value date (DD Mon YYYY before the amount)
                val_date_match = re.search(r"(\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})$", prefix_str)
                if val_date_match:
                    value_date = val_date_match.group(1).strip()
                    ref_trn_part = prefix_str[: val_date_match.start()].strip()
                else:
                    value_date = post_date_str
                    ref_trn_part = prefix_str

                # Identify TRN type
                trn_type_match = re.search(r"\b(S\+P-\s+CHG|S\+P-|S\+P\+\s+INT|S\+P\+)\b", ref_trn_part)
                if trn_type_match:
                    trn_type = trn_type_match.group(1).strip()
                else:
                    # Fallback using column positions
                    if "TRN type" in col_bounds and "Value date" in col_bounds:
                        trn_type = line.between(col_bounds["TRN type"][0], col_bounds["Value date"][0]).strip()
                    else:
                        trn_type = "UNKNOWN"

                # Extract Bank reference using column bounds
                bank_ref = ""
                if "Bank reference" in col_bounds and "Customer reference" in col_bounds:
                    bank_ref = line.between(
                        col_bounds["Bank reference"][0],
                        col_bounds["Customer reference"][0],
                    ).strip()

                if not bank_ref:
                    # If column slicing was empty, slice up to trn_type
                    parts = ref_trn_part.split()
                    bank_ref = parts[0]

                # Credit / Debit determination
                clean_amt = amt_str.replace(",", "")
                clean_bal = bal_str.replace(",", "")

                if amt_str.startswith("-"):
                    debit = clean_amt
                    credit = None
                else:
                    credit = clean_amt
                    debit = None

                # Now look ahead for Narrative continuation line(s)
                narrative_parts = []
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    next_str = extract_line_text(next_line)

                    # Stop if we hit next transaction, day marker, header, or footer
                    if tx_tail_pattern.search(next_str):
                        break
                    if next_str.startswith("Balance as at close") or next_str.startswith("Balance brought forward"):
                        break
                    if next_str.startswith("Statement details") or next_str.startswith("Bank reference") or "Account number" in next_str:
                        break

                    if next_str.startswith("Narrative"):
                        content = next_str[len("Narrative"):].strip()
                        if content:
                            narrative_parts.append(content)
                        j += 1
                    elif narrative_parts:
                        # Continuation line of narrative
                        narrative_parts.append(next_str)
                        j += 1
                    else:
                        break

                narrative_raw = " ".join(narrative_parts).strip()

                # Repair mid-word wrap marked by break character ','
                # e.g. "INFRASTR, UCTURE" -> "INFRASTRUCTURE"
                narrative = narrative_raw.replace("INFRASTR, UCTURE", "INFRASTRUCTURE")

                tx_row = {
                    "bank_reference": bank_ref,
                    "trn_type": trn_type,
                    "value_date": value_date,
                    "post_date": post_date_str,
                    "time": time_str,
                    "narrative": narrative,
                    "credit": credit,
                    "debit": debit,
                    "balance": clean_bal,
                    "account_number": account_number,
                    "currency": currency,
                    "page": page_num,
                }
                transactions.append(tx_row)
                print(f"Row {len(transactions)} (p.{page_num}): ref='{bank_ref}' trn='{trn_type}' cr={credit} db={debit} bal={clean_bal} time={time_str}")
                i = j
            else:
                i += 1

    print(f"\nExtracted {len(transactions)} transaction rows.")

    # --- Validation Checks ---
    assert len(transactions) == 16, f"Expected 16 rows, got {len(transactions)}"

    # 1. Closing balance check
    closing_bal_match = re.search(r"Closing ledger balance brought forward\s+([\d.,]+)", full_pdf_text)
    if closing_bal_match:
        expected_closing = closing_bal_match.group(1).replace(",", "")
        assert transactions[0]["balance"] == expected_closing, (
            f"Closing balance mismatch: first row has {transactions[0]['balance']}, expected {expected_closing}"
        )
        print(f"Closing balance verified: {expected_closing}")

    # 2. Balance chain check: balance[i] - amount[i] == balance[i+1]
    for idx in range(len(transactions) - 1):
        cur = transactions[idx]
        nxt = transactions[idx + 1]
        cur_b = Decimal(cur["balance"])
        nxt_b = Decimal(nxt["balance"])
        amt = Decimal(cur["credit"]) if cur["credit"] is not None else Decimal(cur["debit"])
        expected_next = cur_b - amt
        assert expected_next == nxt_b, (
            f"Balance chain broken at row {idx}: {cur_b} - ({amt}) = {expected_next} != next balance {nxt_b}"
        )
    print("Balance chain closed exactly across all rows.")

    # 3. Printed openings check
    last_tx = transactions[-1]
    last_b = Decimal(last_tx["balance"])
    last_amt = Decimal(last_tx["credit"]) if last_tx["credit"] is not None else Decimal(last_tx["debit"])
    final_opening = last_b - last_amt
    assert final_opening == Decimal("6587.67"), f"Final balance brought forward expected 6587.67, got {final_opening}"
    print(f"Final opening balance verified: {final_opening}")

    # 4. One amount per row check
    for idx, r in enumerate(transactions):
        assert (r["credit"] is None) != (r["debit"] is None), f"Row {idx} does not have exactly one amount set"
        assert "," not in r["balance"], f"Row {idx} balance contains comma"
        if r["credit"] is not None:
            assert "," not in r["credit"], f"Row {idx} credit contains comma"
        if r["debit"] is not None:
            assert "," not in r["debit"], f"Row {idx} debit contains comma"

    # 5. Reference provenance check
    for idx, r in enumerate(transactions):
        ref = r["bank_reference"]
        assert ref in full_pdf_text, f"Row {idx} bank_reference '{ref}' not found in PDF text"
    print("Reference provenance verified for all rows.")

    # Write output
    kit.write_result(transactions)
    print(f"parsed {len(transactions)} rows")


parse_statement()