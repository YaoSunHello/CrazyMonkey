import re
import kit


def norm(s):
    """Normalize a name for robust comparison."""
    if not s:
        return ""
    s = str(s)
    # Un-wrap mid-word comma inserted by bank wrapping (e.g. INFRASTR, UCTURE -> INFRASTRUCTURE)
    s = re.sub(r"([A-Za-z]),\s*([A-Za-z])", r"\1\2", s)
    # Remove non-alphanumeric characters
    s = re.sub(r"[^A-Za-z0-9]+", " ", s)
    return s.strip().lower()


def find_table_match(name, table_names, kit_module):
    """Try to match a raw name against reference tables in preference order.

    Order: related_parties -> vendors -> investors -> legal_entities ->
    deals_positions.
    """
    if not name:
        return None, None

    norm_target = norm(name)
    if not norm_target:
        return None, None

    # Variants to try with kit's exact / case-insensitive contains
    variants = [
        name.strip(),
        re.sub(r"([A-Za-z]),\s*([A-Za-z])", r"\1\2", name).strip(),
        re.sub(
            r"\s+",
            " ",
            re.sub(r"([A-Za-z]),\s*([A-Za-z])", r"\1\2", name),
        ).strip(),
    ]
    variants = [v.rstrip(".,;:-") for v in variants if v]

    for tbl_name in table_names:
        try:
            t = kit_module.table(tbl_name)
        except Exception:
            continue

        cols = list(t.columns)

        # 1. Try t.contains on variants
        for var in variants:
            for col in cols:
                try:
                    if t.contains(col, var):
                        row = t.find(col, var)
                        if row and col in row:
                            return tbl_name, row[col]
                except Exception:
                    pass

        # 2. Try normalized exact match across values in table
        for col in cols:
            try:
                for val in t.values(col):
                    if norm(val) == norm_target:
                        return tbl_name, val
            except Exception:
                pass

    return None, None


def clean_party_candidate(cand_text, full_narrative):
    """Isolate the party name from trailing keywords/delimiters."""
    if not cand_text:
        return None

    # Split at delimiters that signify trailing project/ref/invoice or punctuation
    delim_pattern = (
        r"(\s+[-–—/]\s+|\s*;\s*|\bPROJECT\b|\bREF\b|\bINV\b|\bINVOICE\b)"
    )
    parts = re.split(delim_pattern, cand_text, flags=re.IGNORECASE)
    cleaned = parts[0].strip()

    # Avoid generic non-entity tokens
    generic_words = {
        "account",
        "our account",
        "own account",
        "ac",
        "a/c",
        "principal",
        "interest",
        "reserve",
        "fees",
        "charges",
        "commission",
    }
    if cleaned.lower() in generic_words:
        return None

    # Locate the exact slice in the narrative to preserve provenance
    start_idx = full_narrative.find(cleaned)
    if start_idx != -1:
        return full_narrative[start_idx : start_idx + len(cleaned)]
    return cleaned if cleaned in full_narrative else None


def extract_parties_from_narrative(narrative):
    """Extract candidate parties (e.g. from FROM...TO...) from the narrative."""
    if not narrative:
        return []

    candidates = []

    # Pattern: FROM <party1> TO <party2>
    m_from_to = re.search(
        r"\bFROM\s+(.+?)\s+TO\s+(.+)", narrative, re.IGNORECASE
    )
    if m_from_to:
        p1 = clean_party_candidate(m_from_to.group(1), narrative)
        p2 = clean_party_candidate(m_from_to.group(2), narrative)
        if p1:
            candidates.append(p1)
        if p2:
            candidates.append(p2)
        return candidates

    # Pattern: TO <party1> FROM <party2>
    m_to_from = re.search(
        r"\bTO\s+(.+?)\s+FROM\s+(.+)", narrative, re.IGNORECASE
    )
    if m_to_from:
        p1 = clean_party_candidate(m_to_from.group(1), narrative)
        p2 = clean_party_candidate(m_to_from.group(2), narrative)
        if p1:
            candidates.append(p1)
        if p2:
            candidates.append(p2)
        return candidates

    # Pattern: PAYMENT TO / TRANSFER TO / TO <party>
    m_to = re.search(
        r"\b(?:PAYMENT\s+TO|TRANSFER\s+TO|PAID\s+TO|TO)\s+(.+)",
        narrative,
        re.IGNORECASE,
    )
    if m_to:
        p = clean_party_candidate(m_to.group(1), narrative)
        if p:
            candidates.append(p)
            return candidates

    # Pattern: RECEIVED FROM / TRANSFER FROM / FROM <party>
    m_from = re.search(
        r"\b(?:RECEIVED\s+FROM|TRANSFER\s+FROM|FROM)\s+(.+)",
        narrative,
        re.IGNORECASE,
    )
    if m_from:
        p = clean_party_candidate(m_from.group(1), narrative)
        if p:
            candidates.append(p)
            return candidates

    # Pattern: Prefix like "LOAN: <party>" or "MGMT FEES: <party>"
    m_prefix = re.search(
        r"^(?:LOAN|EQUITY|INVESTMENT|TRANSFER|PAYMENT|MGMT\s+FEES?|FEES?|DISTRIBUTION|DRAWDOWN)\s*:\s*(.+)",
        narrative,
        re.IGNORECASE,
    )
    if m_prefix:
        p = clean_party_candidate(m_prefix.group(1), narrative)
        if p:
            candidates.append(p)
            return candidates

    return candidates


def extract_project_code(narrative, t_proj):
    """Extract project word from narrative and match against project_codes."""
    if not narrative:
        return None, {"status": "CANNOT_VERIFY", "matched_name": None, "table": None}

    proj_raw = None

    # 1. Project word often appears after PROJECT (e.g. PROJECT KALVIK)
    m_proj = re.search(
        r"\bPROJECT(?:\s+CODE)?\s*[:\-\/]?\s*([A-Za-z0-9_\-]+)",
        narrative,
        re.IGNORECASE,
    )
    if m_proj:
        # Extract the exact slice from the narrative
        proj_raw = narrative[m_proj.start(1) : m_proj.end(1)]

    # 2. If not after PROJECT keyword, check if any project code is in narrative as a standalone word
    if not proj_raw and t_proj:
        for col in t_proj.columns:
            for val in t_proj.values(col):
                if not val:
                    continue
                val_str = str(val).strip()
                # Whole word match in narrative
                m_word = re.search(
                    r"\b" + re.escape(val_str) + r"\b", narrative, re.IGNORECASE
                )
                if m_word:
                    proj_raw = narrative[m_word.start() : m_word.end()]
                    break
            if proj_raw:
                break

    if not proj_raw:
        return None, {"status": "CANNOT_VERIFY", "matched_name": None, "table": None}

    # Match proj_raw against project_codes table
    matched_name = None
    if t_proj:
        for col in t_proj.columns:
            if t_proj.contains(col, proj_raw):
                row = t_proj.find(col, proj_raw)
                if row and col in row:
                    matched_name = row[col]
                    break
            if not matched_name:
                for val in t_proj.values(col):
                    if norm(proj_raw) == norm(val):
                        matched_name = val
                        break
            if matched_name:
                break

    if matched_name:
        match_info = {
            "status": "MATCH",
            "matched_name": matched_name,
            "table": "project_codes",
        }
    else:
        match_info = {
            "status": "UNRESOLVED",
            "matched_name": None,
            "table": None,
        }

    return proj_raw, match_info


def classify_row(row, cp_raw, cp_match, proj_raw, proj_match):
    """Classify the transaction row into one of the 8 declared labels."""
    narrative = str(
        row.get("narrative") or row.get("description") or ""
    ).upper()
    table = cp_match.get("table")
    has_proj = proj_raw is not None

    # 1. Other (Bank charges, interest, routine non-party fees)
    if any(
        k in narrative
        for k in [
            "BANK CHARGE",
            "BANK FEE",
            "SWIFT FEE",
            "SERVICE CHARGE",
            "MAINTENANCE FEE",
            "COMMISSION",
        ]
    ):
        return "Other"
    if "INTEREST" in narrative and not any(
        k in narrative
        for k in ["LOAN", "INVESTMENT", "TRANCHE", "PRINCIPAL", "HOLDCO", "PROJECT"]
    ):
        return "Other"
    if cp_match["status"] == "CANNOT_VERIFY" and any(
        k in narrative for k in ["INTEREST", "CHARGE", "FEE"]
    ):
        return "Other"

    # 2. Investor
    if table == "investors":
        return "Investor"
    if any(
        k in narrative for k in ["CAPITAL CALL", "CALL NOTICE", "DISTRIBUTION"]
    ):
        return "Investor"

    # 3. Vendor
    if table == "vendors":
        return "Vendor"
    if any(
        k in narrative
        for k in [
            "INVOICE",
            "INV #",
            "INV:",
            "AUDIT FEE",
            "LEGAL FEE",
            "CONSULTING",
        ]
    ):
        return "Vendor"

    # 4. Internal
    if any(
        k in narrative
        for k in [
            "INTERNAL TRANSFER",
            "BETWEEN OWN ACCOUNTS",
            "OWN ACCOUNTS",
            "SWEEP",
            "CASH POOL",
        ]
    ):
        return "Internal"

    # 5. Investment Transfer
    # Moving money between platform entities to fund/settle an investment
    if ("FROM" in narrative and "TO" in narrative and has_proj) or (
        table in ("related_parties", "legal_entities") and has_proj
    ):
        return "Investment Transfer"

    # 6. Investment
    if any(
        k in narrative
        for k in [
            "LOAN",
            "DRAWDOWN",
            "EQUITY",
            "SHARES",
            "PRINCIPAL",
            "PURCHASE",
            "INVESTMENT",
            "TRANCHE",
            "FACILITY",
        ]
    ):
        if has_proj or ("FROM" in narrative and "TO" in narrative):
            return (
                "Investment Transfer"
                if ("FROM" in narrative and "TO" in narrative)
                else "Investment"
            )
        return "Investment"
    if table == "deals_positions":
        return "Investment"

    # 7. Related Party
    if table == "related_parties":
        return "Related Party"
    if any(
        k in narrative
        for k in [
            "MGMT FEE",
            "MANAGEMENT FEE",
            "REBATE",
            "MONITORING FEE",
            "SETTLING BALANCES",
            "INTERCOMPANY",
        ]
    ):
        return "Related Party"

    # 8. Fallback based on project or counterparty
    if has_proj:
        return "Investment Transfer"
    if cp_match["status"] == "MATCH" and table in (
        "related_parties",
        "legal_entities",
    ):
        return "Related Party"

    return "Review"


def main():
    rows = kit.rows()

    # Preference order for counterparty matching
    cp_tables = [
        "related_parties",
        "vendors",
        "investors",
        "legal_entities",
        "deals_positions",
    ]

    try:
        t_proj = kit.table("project_codes")
    except Exception:
        t_proj = None

    # 1. Identify the statement's own entity for each account_number
    # The statement's own entity is the entity that recurs on nearly every row of the account.
    account_parties = {}
    for r in rows:
        acc = r.get("account_number") or r.get("account")
        narrative = str(r.get("narrative") or r.get("description") or "")
        cands = extract_parties_from_narrative(narrative)
        if acc not in account_parties:
            account_parties[acc] = []
        account_parties[acc].append(cands)

    account_holder = {}
    for acc, list_of_cands in account_parties.items():
        counts = {}
        for cands in list_of_cands:
            for c in cands:
                nc = norm(c)
                counts[nc] = counts.get(nc, 0) + 1
        if counts:
            # The most recurring candidate across rows of this account
            dominant = max(counts.items(), key=lambda x: x[1])
            # Only consider it an account holder if it recurs across rows
            if dominant[1] >= max(2, len(list_of_cands) // 3):
                account_holder[acc] = dominant[0]

    # 2. Process each row
    output_rows = []
    for r in rows:
        out = dict(r)
        acc = r.get("account_number") or r.get("account")
        narrative = str(r.get("narrative") or r.get("description") or "")
        own_entity_norm = account_holder.get(acc)

        # Extract candidates
        candidates = extract_parties_from_narrative(narrative)

        # Filter out the account holder to get the counterparty
        cp_raw = None
        if len(candidates) >= 2:
            # If both sides named, pick the one that is NOT the account holder
            if own_entity_norm:
                non_holders = [
                    c for c in candidates if norm(c) != own_entity_norm
                ]
                if non_holders:
                    cp_raw = non_holders[0]
                else:
                    cp_raw = candidates[1]
            else:
                cp_raw = candidates[1]
        elif len(candidates) == 1:
            cand = candidates[0]
            if own_entity_norm and norm(cand) == own_entity_norm:
                cp_raw = None
            else:
                cp_raw = cand
        else:
            # If no FROM/TO structure, check if any reference list entity is directly mentioned
            for tbl_name in cp_tables:
                try:
                    t = kit.table(tbl_name)
                    for col in t.columns:
                        for val in t.values(col):
                            if not val:
                                continue
                            val_str = str(val).strip()
                            if own_entity_norm and norm(val_str) == own_entity_norm:
                                continue
                            m = re.search(
                                r"\b" + re.escape(val_str) + r"\b",
                                narrative,
                                re.IGNORECASE,
                            )
                            if m:
                                cp_raw = narrative[m.start() : m.end()]
                                break
                        if cp_raw:
                            break
                except Exception:
                    pass
                if cp_raw:
                    break

        # Ensure cp_raw strictly appears in narrative (provenance check)
        if cp_raw and cp_raw not in narrative:
            cp_raw = None

        # Resolve counterparty against reference tables
        if cp_raw:
            matched_tbl, matched_val = find_table_match(
                cp_raw, cp_tables, kit
            )
            if matched_tbl and matched_val:
                cp_match = {
                    "status": "MATCH",
                    "matched_name": matched_val,
                    "table": matched_tbl,
                }
            else:
                cp_match = {
                    "status": "UNRESOLVED",
                    "matched_name": None,
                    "table": None,
                }
        else:
            cp_match = {
                "status": "CANNOT_VERIFY",
                "matched_name": None,
                "table": None,
            }

        # Extract and resolve project code
        proj_raw, proj_match = extract_project_code(narrative, t_proj)

        # Classify row
        classification = classify_row(r, cp_raw, cp_match, proj_raw, proj_match)

        # Attach resolved attributes
        out["counterparty_raw"] = cp_raw
        out["counterparty_match"] = cp_match
        out["project_code_raw"] = proj_raw
        out["project_code_match"] = proj_match
        out["classification"] = classification

        output_rows.append(out)

    kit.write_result(output_rows)
    print(f"parsed {len(output_rows)} rows")


if __name__ == "__main__":
    main()