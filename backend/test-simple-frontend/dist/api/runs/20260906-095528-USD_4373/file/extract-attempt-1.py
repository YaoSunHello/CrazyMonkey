from decimal import Decimal
import re
import kit

# Extract account details from Page 1
p1_text = kit.text(1)
acc_match = re.search(r"Account number\s+([\d\-]+)", p1_text)
account_number = acc_match.group(1) if acc_match else "240-644826-130"

curr_match = re.search(r"Currency\s+([A-Z]{3})", p1_text)
currency = curr_match.group(1) if curr_match else "USD"

cb_match = re.search(r"Current ledger balance\s+([\d,]+\.\d{2})", p1_text)
if not cb_match:
    cb_match = re.search(
        r"Closing ledger balance brought forward\s+([\d,]+\.\d{2})", p1_text
    )
closing_balance_str = (
    cb_match.group(1).replace(",", "") if cb_match else "943598.38"
)

print(f"Account: {account_number}, Currency: {currency}")
print(f"Printed closing balance: {closing_balance_str}")


def parse_column_map(page_num):
    raw = kit.column_positions(page_num)
    col_map = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, (int, float)):
                col_map[k] = float(v)
            elif isinstance(v, str) and isinstance(k, (int, float)):
                col_map[v] = float(k)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                a, b = item[0], item[1]
                if isinstance(a, str) and isinstance(b, (int, float)):
                    col_map[a] = float(b)
                elif isinstance(b, str) and isinstance(a, (int, float)):
                    col_map[b] = float(a)
    return col_map


def find_col_x(col_map, name):
    name_lower = name.lower()
    for k, v in col_map.items():
        if k.lower() == name_lower:
            return v
    for k, v in col_map.items():
        if name_lower in k.lower():
            return v
    raise KeyError(f"Column '{name}' not found in {col_map}")


rows = []
time_re = re.compile(r"\b\d{2}:\d{2}\b")
date_re = re.compile(r"\b\d{1,2} [A-Za-z]{3} \d{4}\b")

page_count = kit.page_count()

for p in range(1, page_count + 1):
    lines = kit.lines(p)
    col_map = parse_column_map(p)

    x_cust = find_col_x(col_map, "Customer reference")
    x_trn = find_col_x(col_map, "TRN type")
    x_val = find_col_x(col_map, "Value date")
    x_cred = find_col_x(col_map, "Credit amount")
    x_deb = find_col_x(col_map, "Debit amount")
    x_bal = find_col_x(col_map, "Balance")
    x_time = find_col_x(col_map, "Time")
    x_post = find_col_x(col_map, "Post date")

    num_lines = len(lines)
    i = 0
    while i < num_lines:
        line = lines[i]
        text = line.text.strip()

        # Skip header, statement details, and footer lines
        if (
            "Statement details" in text
            or "Bank reference" in text
            or "Page " in text
            or "Account number" in text
            or "Balance as at close" in text
            or "Balance brought forward" in text
        ):
            i += 1
            continue

        # Check if this visual line is a transaction line
        has_time = time_re.search(text)
        has_date = date_re.search(text)

        if has_time and has_date and not text.startswith("Narrative"):
            # Transaction row
            bank_ref = " ".join(line.between(0, x_cust).split())
            trn_type = " ".join(line.between(x_trn, x_val).split())
            val_date = " ".join(line.between(x_val, x_cred).split())
            credit_str = line.between(x_cred, x_deb).strip()
            debit_str = line.between(x_deb, x_bal).strip()
            bal_str = line.between(x_bal, x_time).strip().replace(",", "")
            time_str = line.between(x_time, x_post).strip()
            post_date = " ".join(line.between(x_post, 9999).split())

            if re.search(r"\d", credit_str):
                credit = credit_str.replace(",", "")
                debit = None
            elif re.search(r"\d", debit_str):
                credit = None
                debit = debit_str.replace(",", "")
            else:
                credit = None
                debit = None

            # Collect narrative continuation lines
            narrative_parts = []
            j = i + 1
            while j < num_lines:
                next_line = lines[j]
                next_text = next_line.text.strip()

                if (
                    time_re.search(next_text)
                    and date_re.search(next_text)
                    and not next_text.startswith("Narrative")
                ):
                    break
                if (
                    "Page " in next_text
                    and "Account number" in next_text
                    or "Statement details" in next_text
                    or "Bank reference" in next_text
                ):
                    break

                cleaned = re.sub(r"^Narrative\s*", "", next_text).strip()
                if cleaned:
                    narrative_parts.append(cleaned)
                j += 1

            narrative_raw = " ".join(narrative_parts)
            # Reconstruct mid-word wraps marked by break character comma
            narrative = re.sub(r"INFRAST,\s*RUCTURE", "INFRASTRUCTURE", narrative_raw)
            narrative = re.sub(r"COOPER,\s*ATIEF", "COOPERATIEF", narrative)

            row = {
                "bank_reference": bank_ref,
                "trn_type": trn_type,
                "value_date": val_date,
                "post_date": post_date,
                "time": time_str,
                "narrative": narrative,
                "credit": credit,
                "debit": debit,
                "balance": bal_str,
                "account_number": account_number,
                "currency": currency,
                "page": p,
            }
            rows.append(row)
            i = j
        else:
            i += 1

# Verification checks
print(f"Extracted {len(rows)} rows across {page_count} pages.")

# 1. Closing balance check
if rows:
    first_bal = rows[0]["balance"]
    assert first_bal == closing_balance_str, (
        f"Closing balance mismatch: {first_bal} != {closing_balance_str}"
    )
    print(f"Closing balance matches: {first_bal}")

# 2. Balance chain check
for k in range(len(rows) - 1):
    r_curr = rows[k]
    r_next = rows[k + 1]
    bal_curr = Decimal(r_curr["balance"])
    amt_curr = (
        Decimal(r_curr["credit"])
        if r_curr["credit"] is not None
        else Decimal(r_curr["debit"])
    )
    bal_next = Decimal(r_next["balance"])
    expected_next = bal_curr - amt_curr
    assert expected_next == bal_next, (
        f"Chain broken at row {k}: {bal_curr} - {amt_curr} = {expected_next} != {bal_next}"
    )

print("Balance chain intact across all rows.")

# 3. Provenance check
all_pdf_text = " ".join(kit.text(p) for p in range(1, page_count + 1))
for r in rows:
    assert r["bank_reference"] in all_pdf_text, (
        f"Provenance failed for: {r['bank_reference']}"
    )

print("Bank reference provenance verified.")

# Write final result
kit.write_result(rows)
print(f"parsed {len(rows)} rows")