import re
import sys
import kit


def unwrap_name(s):
    if not s:
        return ""
    # Remove mid-word comma inserted by bank wrapping, e.g. 'INFRASTR, UCTURE' -> 'INFRASTRUCTURE'
    res = re.sub(r"([A-Za-z]),\s*([A-Za-z])", r"\1\2", s)
    res = re.sub(r"\s+", " ", res).strip()
    return res


def norm_key(s):
    if not s:
        return ""
    unwrapped = unwrap_name(s)
    return re.sub(r"[^A-Za-z0-9]", "", unwrapped).upper()


def get_col_val(row_obj, col):
    if isinstance(row_obj, dict):
        return row_obj.get(col)
    if hasattr(row_obj, col):
        return getattr(row_obj, col)
    if hasattr(row_obj, "__getitem__"):
        try:
            return row_obj[col]
        except Exception:
            pass
    return None


def extract_project_raw(narrative, known_projects):
    # Narrative often has PROJECT <word> or PROJ <word>
    m = re.search(
        r"\bPROJ(?:ECT)?(?:\s+CODE)?[:\s-]+([A-Za-z0-9_-]+)",
        narrative,
        re.IGNORECASE,
    )
    if m:
        raw_word = narrative[m.start(1) : m.end(1)].strip()
        # Avoid common false positives if word is just 'NO', 'NUMBER', 'ID'
        if raw_word.upper() not in {"NO", "NUMBER", "ID", "REF"}:
            return raw_word

    # Look for known project codes appearing as distinct words
    for p in known_projects:
        pattern = r"\b" + re.escape(p) + r"\b"
        m_known = re.search(pattern, narrative, re.IGNORECASE)
        if m_known:
            return narrative[m_known.start() : m_known.end()]

    return None


def clean_slice_end(narrative, start_pos):
    rest = narrative[start_pos:]
    delim = re.search(
        r"\b(PROJECT|PROJ|REF|REFERENCE|INV|INVOICE|VAL DATE|VALUE DATE|DATE)\b|;|//",
        rest,
        re.IGNORECASE,
    )
    if delim:
        end_pos = start_pos + delim.start()
    else:
        end_pos = len(narrative)

    raw = narrative[start_pos:end_pos].strip()
    while raw.endswith(("-", "/", ":", ";", " ")):
        raw = raw[:-1].strip()
    return raw


def parse_parties_from_narrative(narrative):
    # 1. Look for FROM ... TO ... or TO ... FROM ...
    from_matches = list(re.finditer(r"\bFROM\s+", narrative, re.IGNORECASE))
    to_matches = list(re.finditer(r"\s+\bTO\s+", narrative, re.IGNORECASE))

    if from_matches and to_matches:
        f = from_matches[0]
        t_candidates = [t for t in to_matches if t.start() >= f.end()]
        if t_candidates:
            t = t_candidates[0]
            p1 = narrative[f.end() : t.start()].strip()
            p2 = clean_slice_end(narrative, t.end())
            if p1 and p2:
                return p1, p2

        # Check TO ... FROM ...
        t = to_matches[0]
        f_candidates = [f for f in from_matches if f.start() >= t.end()]
        if f_candidates:
            f = f_candidates[0]
            p1 = narrative[t.end() : f.start()].strip()
            p2 = clean_slice_end(narrative, f.end())
            if p1 and p2:
                return p2, p1  # return in order (FROM_party, TO_party)

    # 2. Look for single TO ...
    if to_matches:
        t = to_matches[0]
        p = clean_slice_end(narrative, t.end())
        if p:
            return None, p

    to_start = re.search(r"^TO\s+", narrative, re.IGNORECASE)
    if to_start:
        p = clean_slice_end(narrative, to_start.end())
        if p:
            return None, p

    # 3. Look for single FROM ...
    if from_matches:
        f = from_matches[0]
        p = clean_slice_end(narrative, f.end())
        if p:
            return p, None

    # 4. Check for Beneficiary / B/O
    bo = re.search(r"\b(?:B/O|BENEFICIARY|BEN)[:\s]+", narrative, re.IGNORECASE)
    if bo:
        p = clean_slice_end(narrative, bo.end())
        if p:
            return None, p

    return None, None


def resolve_project_code(project_raw, t_proj):
    if not project_raw:
        return {"status": "CANNOT_VERIFY", "matched_name": None, "table": None}

    if t_proj:
        variants = [
            project_raw,
            unwrap_name(project_raw),
            project_raw.rstrip(".,;:- "),
        ]
        for col in t_proj.columns:
            for v in variants:
                if not v:
                    continue
                if t_proj.contains(col, v):
                    row_found = t_proj.find(col, v)
                    matched_name = None
                    if row_found:
                        matched_name = get_col_val(
                            row_found, "Project Code"
                        ) or get_col_val(row_found, col)
                    if not matched_name:
                        for val in t_proj.values(col):
                            if val and str(val).strip().lower() == v.lower():
                                matched_name = val
                                break
                    if matched_name:
                        return {
                            "status": "MATCH",
                            "matched_name": matched_name,
                            "table": "project_codes",
                        }

    return {"status": "UNRESOLVED", "matched_name": None, "table": None}


def resolve_counterparty(counterparty_raw):
    if not counterparty_raw:
        return {"status": "CANNOT_VERIFY", "matched_name": None, "table": None}

    table_preference = [
        "related_parties",
        "vendors",
        "investors",
        "legal_entities",
        "deals_positions",
    ]

    variants = [
        counterparty_raw.strip(),
        unwrap_name(counterparty_raw),
        counterparty_raw.rstrip(".,;:- ").strip(),
        unwrap_name(counterparty_raw).rstrip(".,;:- ").strip(),
        re.sub(r"\s+", " ", counterparty_raw.replace(",", " ")).strip(),
    ]
    # Remove duplicates preserving order
    seen_v = set()
    cleaned_variants = []
    for v in variants:
        if v and v not in seen_v:
            seen_v.add(v)
            cleaned_variants.append(v)

    available_tables = kit.tables()
    for t_name in table_preference:
        if t_name not in available_tables:
            continue
        t = kit.table(t_name)
        for col in t.columns:
            for v in cleaned_variants:
                if t.contains(col, v):
                    row_found = t.find(col, v)
                    matched_name = None
                    if row_found:
                        matched_name = get_col_val(row_found, col)
                    if not matched_name:
                        for val in t.values(col):
                            if val and str(val).strip().lower() == v.lower():
                                matched_name = val
                                break
                    if matched_name is None:
                        matched_name = v
                    return {
                        "status": "MATCH",
                        "matched_name": matched_name,
                        "table": t_name,
                    }

    return {"status": "UNRESOLVED", "matched_name": None, "table": None}


def classify_row(
    narrative, cp_raw, cp_match, proj_raw, proj_match, from_side, to_side
):
    text = narrative.upper()

    # 1. Other: bank charges, fees, interest, routine postings
    bank_keywords = [
        "BANK CHARGE",
        "BANK CHARGES",
        "SERVICE CHARGE",
        "ACCOUNT FEE",
        "MAINTENANCE FEE",
        "INTEREST CHARGE",
        "INTEREST PAID",
        "INTEREST RECEIVED",
        "INTEREST CREDIT",
        "CREDIT INTEREST",
        "COMMISSION",
        "COMMISSIONS",
        "FX MARGIN",
        "CABLE CHARGE",
        "SWIFT CHARGE",
        "CORRESPONDENT BANK",
    ]
    if any(k in text for k in bank_keywords) and "MANAGEMENT FEE" not in text:
        return "Other"

    if cp_raw is None and proj_raw is None:
        return "Other"

    # 2. Investor: capital calls and distributions
    investor_keywords = [
        "CAPITAL CALL",
        "DRAWDOWN",
        "DISTRIBUTION",
        "SUBSCRIPTION FOR SHARES",
    ]
    if any(k in text for k in investor_keywords):
        return "Investor"
    if cp_match.get("table") == "investors":
        return "Investor"

    # 3. Vendor: paying suppliers
    if cp_match.get("table") == "vendors":
        return "Vendor"
    vendor_service_keywords = [
        "AUDIT FEE",
        "AUDIT FEES",
        "LEGAL FEE",
        "LEGAL FEES",
        "TAX ADVISORY",
        "CONSULTING FEE",
        "ADMINISTRATION FEE",
        "ADMIN FEE",
        "INVOICE",
    ]
    if any(k in text for k in vendor_service_keywords) and (
        proj_raw is None and "LOAN" not in text
    ):
        return "Vendor"

    # 4. Investment Transfer: movement between platform's own entities to fund/settle investment
    # Most rows whose narrative says FROM one entity TO another and names a project
    if proj_raw is not None and (
        (from_side and to_side)
        or "TRANSFER" in text
        or "LOAN" in text
        or "FUNDING" in text
    ):
        return "Investment Transfer"

    # 5. Investment: buying/selling a position or funding one directly
    investment_keywords = [
        "LOAN",
        "EQUITY",
        "SHARES",
        "ACQUISITION",
        "PURCHASE",
        "INVESTMENT",
        "POSITION",
        "DISPOSAL",
    ]
    if (
        cp_match.get("table") == "deals_positions"
        or any(k in text for k in investment_keywords)
        or (proj_raw is not None)
    ):
        return "Investment"

    # 6. Related Party: movement with a related party not funding investment
    if cp_match.get("table") == "related_parties" or "MANAGEMENT FEE" in text:
        return "Related Party"

    # 7. Internal: transfer between platform's own accounts
    internal_keywords = [
        "INTERNAL TRANSFER",
        "TRANSFER BETWEEN",
        "SWEEP",
        "CASH POOLING",
        "ACCOUNT TRANSFER",
    ]
    if any(k in text for k in internal_keywords) or (
        from_side and to_side and proj_raw is None
    ):
        return "Internal"

    return "Review"


def main():
    rows = kit.rows()

    # Prepare project codes list
    known_projects = set()
    t_proj = kit.table("project_codes") if "project_codes" in kit.tables() else None
    if t_proj:
        for col in t_proj.columns:
            for val in t_proj.values(col):
                if val and str(val).strip():
                    known_projects.add(str(val).strip())

    # Pass 1: Identify the statement's own entity for each account_number
    # The statement's own entity is the name that recurs on nearly every row of the account.
    account_entity_counts = {}
    for r in rows:
        acc = r.get("account_number")
        narrative = r.get("narrative", "")
        if acc not in account_entity_counts:
            account_entity_counts[acc] = {}

        p_from, p_to = parse_parties_from_narrative(narrative)
        candidates = []
        if p_from:
            candidates.append(p_from)
        if p_to:
            candidates.append(p_to)

        for cand in candidates:
            k = norm_key(cand)
            if k:
                account_entity_counts[acc][k] = (
                    account_entity_counts[acc].get(k, 0) + 1
                )

    own_entity_per_account = {}
    for acc, counts in account_entity_counts.items():
        if counts:
            # The one with highest frequency
            best_k = max(counts.items(), key=lambda x: x[1])[0]
            own_entity_per_account[acc] = best_k

    # Pass 2: Resolve each row
    resolved_rows = []
    for r in rows:
        out_row = dict(r)
        acc = r.get("account_number")
        narrative = r.get("narrative", "")
        own_k = own_entity_per_account.get(acc)

        # 1. Project code extraction & matching
        proj_raw = extract_project_raw(narrative, known_projects)
        proj_match = resolve_project_code(proj_raw, t_proj)

        # 2. Counterparty extraction
        p_from, p_to = parse_parties_from_narrative(narrative)
        cp_raw = None

        if p_from and p_to:
            k_from = norm_key(p_from)
            k_to = norm_key(p_to)
            if k_from == own_k:
                cp_raw = p_to
            elif k_to == own_k:
                cp_raw = p_from
            else:
                # If neither exactly matched the highest-frequency key,
                # check which side recurs less in this account
                cnt_from = account_entity_counts.get(acc, {}).get(k_from, 0)
                cnt_to = account_entity_counts.get(acc, {}).get(k_to, 0)
                if cnt_from > cnt_to:
                    cp_raw = p_to
                else:
                    cp_raw = p_from
        elif p_to:
            if norm_key(p_to) != own_k:
                cp_raw = p_to
        elif p_from:
            if norm_key(p_from) != own_k:
                cp_raw = p_from

        # Check if narrative names a vendor/related party directly if no party was found yet
        if cp_raw is None:
            # Check if any known party appears in narrative
            # Check vendors, related_parties, legal_entities
            for tbl_name in [
                "vendors",
                "related_parties",
                "investors",
                "legal_entities",
            ]:
                if tbl_name in kit.tables():
                    tbl = kit.table(tbl_name)
                    for col in tbl.columns:
                        for val in tbl.values(col):
                            if val and len(str(val).strip()) > 3:
                                v_str = str(val).strip()
                                # Check if it appears in narrative
                                pattern = r"\b" + re.escape(v_str) + r"\b"
                                m_find = re.search(
                                    pattern, narrative, re.IGNORECASE
                                )
                                if m_find:
                                    found_slice = narrative[
                                        m_find.start() : m_find.end()
                                    ]
                                    if norm_key(found_slice) != own_k:
                                        cp_raw = found_slice
                                        break
                        if cp_raw is not None:
                            break
                if cp_raw is not None:
                    break

        # Verification: provenance must hold
        if cp_raw is not None:
            if cp_raw not in narrative:
                # Ensure exact substring
                cp_raw = None

        if proj_raw is not None:
            if proj_raw not in narrative:
                proj_raw = None
                proj_match = {
                    "status": "CANNOT_VERIFY",
                    "matched_name": None,
                    "table": None,
                }

        cp_match = resolve_counterparty(cp_raw)

        # 3. Classification
        classification = classify_row(
            narrative, cp_raw, cp_match, proj_raw, proj_match, p_from, p_to
        )

        out_row["counterparty_raw"] = cp_raw
        out_row["counterparty_match"] = cp_match
        out_row["project_code_raw"] = proj_raw
        out_row["project_code_match"] = proj_match
        out_row["classification"] = classification

        resolved_rows.append(out_row)

    kit.write_result(resolved_rows)
    print(f"parsed {len(resolved_rows)} rows")


if __name__ == "__main__":
    main()