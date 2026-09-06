import re
import kit


def get_narrative(row):
    for k in ('narrative', 'description', 'narrative_text', 'narration', 'details', 'text'):
        if k in row and row[k] is not None:
            return str(row[k])
    return ""


def get_account_number(row):
    for k in ('account_number', 'account', 'account_no', 'acc_number', 'acc_no'):
        if k in row and row[k] is not None:
            return str(row[k])
    return "default_account"


def clean_entity_candidate(cand, nar, known_project_codes):
    if not cand:
        return None
    cand = cand.strip()

    # Strip explicit project keyword prefix in suffix
    m = re.search(r'^(.*?)(?:\s*(?:[-/;|]\s*)?\b(?:PROJECT|PRJ|PROJ)\b.*)$', cand, re.IGNORECASE)
    if m and m.group(1).strip():
        cand = m.group(1).strip()

    # Strip reference / invoice / date / account suffixes
    m = re.search(
        r'^(.*?)(?:\s*(?:[-/;|]\s*)?\b(?:REF|REFERENCE|INV|INVOICE|VALUE\s+DATE|VAL\s+DATE|DATE|ACC|ACCOUNT|IBAN)\b.*)$',
        cand,
        re.IGNORECASE,
    )
    if m and m.group(1).strip():
        cand = m.group(1).strip()

    # Strip trailing known project codes if separated
    for code in sorted(known_project_codes, key=len, reverse=True):
        if len(code) >= 3:
            m = re.search(r'^(.*?)(?:\s*[-/;|]?\s*\b' + re.escape(code) + r'\b\s*)$', cand, re.IGNORECASE)
            if m and len(m.group(1).strip()) >= 3:
                cand = m.group(1).strip()
                break

    # Strip trailing delimiters, but preserve dots if part of abbreviations like LTD. or S.A.
    while cand and cand[-1] in ' -/:;,|':
        cand = cand[:-1].strip()

    # Find the exact substring in nar to preserve exact provenance
    idx = nar.find(cand)
    if idx != -1:
        return nar[idx:idx + len(cand)]
    idx_upper = nar.upper().find(cand.upper())
    if idx_upper != -1:
        return nar[idx_upper:idx_upper + len(cand)]

    return cand if cand in nar else None


def is_valid_party(p):
    if not p:
        return False
    p_up = p.upper().strip()
    if p_up.startswith(('ACC ', 'ACCOUNT ', 'IBAN ', 'A/C ')):
        return False
    if re.match(r'^(?:ACC|ACCOUNT|IBAN|A/C)?\s*[\d\s-]+$', p_up):
        return False
    if len(p_up) < 2:
        return False
    if p_up in ('BANK CHARGES', 'INTEREST', 'COMMISSION', 'FEES', 'SWEEP'):
        return False
    return True


def extract_candidates(nar, known_project_codes):
    m = re.search(r'\bFROM\b\s+(.*?)\s+\bTO\b\s+(.*)', nar, re.IGNORECASE)
    if m:
        p1 = clean_entity_candidate(m.group(1), nar, known_project_codes)
        p2 = clean_entity_candidate(m.group(2), nar, known_project_codes)
        return (p1 if is_valid_party(p1) else None, p2 if is_valid_party(p2) else None)

    m = re.search(r'\bTO\b\s+(.*?)\s+\bFROM\b\s+(.*)', nar, re.IGNORECASE)
    if m:
        p2 = clean_entity_candidate(m.group(1), nar, known_project_codes)
        p1 = clean_entity_candidate(m.group(2), nar, known_project_codes)
        return (p1 if is_valid_party(p1) else None, p2 if is_valid_party(p2) else None)

    m = re.search(r'\bTO\b\s+(.*)', nar, re.IGNORECASE)
    if m:
        p2 = clean_entity_candidate(m.group(1), nar, known_project_codes)
        return (None, p2 if is_valid_party(p2) else None)

    m = re.search(r'\bFROM\b\s+(.*)', nar, re.IGNORECASE)
    if m:
        p1 = clean_entity_candidate(m.group(1), nar, known_project_codes)
        return (p1 if is_valid_party(p1) else None, None)

    return (None, None)


def normalize_for_comparison(text):
    if not text:
        return ""
    # Unwrap mid-word commas and collapse whitespace
    t = re.sub(r'(\b\w+),\s*(\w+\b)', r'\1\2', text)
    t = re.sub(r'[,.\s]+', ' ', t).strip().upper()
    return t


def find_in_table(t, col, val):
    res = t.find(col, val)
    if res is not None:
        return res
    val_lower = str(val).lower().strip()
    for v in t.values(col):
        if v is not None and str(v).lower().strip() == val_lower:
            res = t.find(col, v)
            if res is not None:
                return res
    return None


def resolve_counterparty(cand, available_tables):
    if not cand:
        return {"status": "CANNOT_VERIFY", "matched_name": None, "table": None}

    cand_variants = [
        cand,
        re.sub(r'(\b\w+),\s*(\w+\b)', r'\1\2', cand),
        re.sub(r'\s+', ' ', cand),
        cand.rstrip('.'),
    ]

    seen = set()
    unique_variants = []
    for v in cand_variants:
        v_clean = v.strip()
        if v_clean and v_clean not in seen:
            seen.add(v_clean)
            unique_variants.append(v_clean)

    pref_order = ['related_parties', 'vendors', 'investors', 'legal_entities', 'deals_positions']
    for table_name in pref_order:
        if table_name not in available_tables:
            continue
        t = kit.table(table_name)
        for col in t.columns:
            for variant in unique_variants:
                if t.contains(col, variant):
                    row = find_in_table(t, col, variant)
                    matched = row[col] if (row is not None and col in row) else variant
                    return {
                        "status": "MATCH",
                        "matched_name": matched,
                        "table": table_name,
                    }

    return {"status": "UNRESOLVED", "matched_name": None, "table": None}


def extract_project_word(nar, known_project_codes, counterparty_raw=None):
    # 1. Explicit keyword PROJECT / PRJ / PROJ
    m = re.search(r'\b(?:PROJECT|PRJ|PROJ)\b[:\s#-]*([A-Za-z0-9_-]+)', nar, re.IGNORECASE)
    if m:
        start, end = m.span(1)
        raw = nar[start:end]
        if raw in nar:
            return raw

    # 2. Known project code appearing outside counterparty_raw
    text_to_search = nar
    if counterparty_raw and counterparty_raw in text_to_search:
        text_to_search = text_to_search.replace(counterparty_raw, ' ' * len(counterparty_raw))

    for code in sorted(known_project_codes, key=len, reverse=True):
        if len(code) < 3:
            continue
        pattern = r'\b' + re.escape(code) + r'\b'
        match = re.search(pattern, text_to_search, re.IGNORECASE)
        if match:
            start, end = match.span()
            return nar[start:end]

    return None


def resolve_project_code(raw_code, available_tables):
    if not raw_code:
        return {"status": "CANNOT_VERIFY", "matched_name": None, "table": None}

    if 'project_codes' not in available_tables:
        return {"status": "UNRESOLVED", "matched_name": None, "table": None}

    t_proj = kit.table('project_codes')
    for col in t_proj.columns:
        if t_proj.contains(col, raw_code):
            row = find_in_table(t_proj, col, raw_code)
            matched = row[col] if (row is not None and col in row) else raw_code
            return {
                "status": "MATCH",
                "matched_name": matched,
                "table": "project_codes",
            }

    return {"status": "UNRESOLVED", "matched_name": None, "table": None}


def classify_row(nar, cp_raw, cp_match, proj_raw, proj_match):
    nar_upper = nar.upper()

    # 1. Other: bank charges, fees, interest
    if any(k in nar_upper for k in [
        'BANK CHARGE', 'BANK CHARGES', 'ACCOUNT MAINTENANCE', 'MONTHLY FEE',
        'COMMISSION', 'CUSTODY FEE', 'WIRE FEE', 'SWIFT CHARGE', 'TRANSFER FEE'
    ]):
        return 'Other'
    if 'INTEREST' in nar_upper and not any(k in nar_upper for k in ['LOAN', 'FACILITY']):
        if any(k in nar_upper for k in ['CREDIT INTEREST', 'DEBIT INTEREST', 'INTEREST PAID', 'INTEREST RECEIVED']) or cp_raw is None:
            return 'Other'

    # 2. Investor: capital call or distribution
    if any(k in nar_upper for k in ['CAPITAL CALL', 'CAP CALL', 'DRAWDOWN', 'DISTRIBUTION', 'EQUALISATION', 'RETURN OF CAPITAL']):
        return 'Investor'
    if cp_match['table'] == 'investors':
        return 'Investor'

    # 3. Vendor: paying a supplier
    if cp_match['table'] == 'vendors':
        return 'Vendor'
    if any(k in nar_upper for k in [
        'INVOICE', 'INV ', 'AUDIT', 'LEGAL FEE', 'TAX SERVICES',
        'DIRECTOR FEE', 'CONSULTING SERVICES', 'ADVISORY SERVICES'
    ]):
        return 'Vendor'

    # 4. Internal: transfer between platform's own accounts
    if any(k in nar_upper for k in ['INTERNAL TRANSFER', 'TRANSFER BETWEEN ACCOUNTS', 'SWEEP']):
        return 'Internal'
    if cp_raw is None and any(k in nar_upper for k in ['TRF TO ACC', 'TRANSFER TO ACC', 'TRANSFER TO ACCOUNT']):
        return 'Internal'

    # 5. Related Party: fees, rebates, balance settling
    if any(k in nar_upper for k in [
        'MANAGEMENT FEE', 'ADVISORY FEE', 'REBATE',
        'SETTLING OF BALANCES', 'SETTLEMENT OF BALANCES',
        'EXPENSE REIMBURSEMENT', 'REIMBURSEMENT'
    ]):
        return 'Related Party'

    # 6. Investment / Investment Transfer
    is_loan_or_equity = any(k in nar_upper for k in [
        'LOAN', 'EQUITY', 'SUBSCRIPTION', 'PURCHASE OF SHARES',
        'SHARE PURCHASE', 'DISPOSAL', 'ACQUISITION'
    ])
    has_from_to = bool(re.search(r'\bFROM\b.*?\bTO\b', nar, re.IGNORECASE))
    has_project = (proj_raw is not None)
    is_platform_entity = (cp_match['table'] == 'legal_entities')

    if has_from_to and has_project:
        if any(k in nar_upper for k in ['TRANSFER', 'TRF', 'FUNDING', 'INV TRF', 'INVESTMENT TRF']):
            return 'Investment Transfer'
        if is_platform_entity or (cp_match['table'] == 'related_parties' and 'SCSP' in str(cp_raw).upper()):
            return 'Investment Transfer'
        if is_loan_or_equity:
            if any(term in str(cp_raw).upper() for term in ['HOLDCO', 'TOPCO', 'BIDCO', 'MIDCO', 'LIMITED', 'LTD']):
                return 'Investment'
            if cp_match['table'] == 'deals_positions':
                return 'Investment'
        return 'Investment Transfer'

    if is_loan_or_equity or cp_match['table'] == 'deals_positions':
        return 'Investment'

    if has_project and any(k in nar_upper for k in ['INVESTMENT', 'TRANSFER', 'TRF']):
        return 'Investment Transfer'

    if cp_match['table'] == 'related_parties' and 'FEE' in nar_upper:
        return 'Related Party'

    if cp_match['table'] == 'legal_entities':
        return 'Internal'

    return 'Review'


def main():
    rows = kit.rows()
    available_tables = kit.tables()

    known_project_codes = set()
    if 'project_codes' in available_tables:
        t_proj = kit.table('project_codes')
        for col in t_proj.columns:
            for val in t_proj.values(col):
                if val:
                    cleaned_val = str(val).strip()
                    if cleaned_val:
                        known_project_codes.add(cleaned_val)

    # First pass: collect entity occurrences per account to detect the account's own entity
    account_parties = {}
    for r in rows:
        acc = get_account_number(r)
        nar = get_narrative(r)
        p1, p2 = extract_candidates(nar, known_project_codes)
        account_parties.setdefault(acc, []).append((p1, p2))

    account_own_entities = {}
    for acc, party_pairs in account_parties.items():
        counts = {}
        for p1, p2 in party_pairs:
            for p in (p1, p2):
                if p:
                    norm = normalize_for_comparison(p)
                    if norm:
                        counts[norm] = counts.get(norm, 0) + 1
        if counts:
            sorted_candidates = sorted(counts.items(), key=lambda x: x[1], reverse=True)
            account_own_entities[acc] = sorted_candidates[0][0]
        else:
            account_own_entities[acc] = ""

    # Second pass: resolve each row
    legal_entities_norms = set()
    if 'legal_entities' in available_tables:
        t_leg = kit.table('legal_entities')
        for col in t_leg.columns:
            for val in t_leg.values(col):
                if val:
                    legal_entities_norms.add(normalize_for_comparison(str(val)))

    resolved_rows = []
    for r in rows:
        acc = get_account_number(r)
        nar = get_narrative(r)
        own_norm = account_own_entities.get(acc, "")

        p1, p2 = extract_candidates(nar, known_project_codes)
        counterparty_raw = None

        if p1 and p2:
            p1_norm = normalize_for_comparison(p1)
            p2_norm = normalize_for_comparison(p2)
            if p1_norm == own_norm or (own_norm and own_norm in p1_norm) or p1_norm in legal_entities_norms:
                counterparty_raw = p2
            elif p2_norm == own_norm or (own_norm and own_norm in p2_norm) or p2_norm in legal_entities_norms:
                counterparty_raw = p1
            else:
                counterparty_raw = p2
        elif p2:
            p2_norm = normalize_for_comparison(p2)
            if not (p2_norm == own_norm or (own_norm and own_norm in p2_norm) or p2_norm in legal_entities_norms):
                counterparty_raw = p2
        elif p1:
            p1_norm = normalize_for_comparison(p1)
            if not (p1_norm == own_norm or (own_norm and own_norm in p1_norm) or p1_norm in legal_entities_norms):
                counterparty_raw = p1

        # Check vendor / investor direct mentions if no candidate extracted
        if not counterparty_raw:
            for tab_name in ('vendors', 'investors'):
                if tab_name in available_tables:
                    t = kit.table(tab_name)
                    for col in t.columns:
                        for val in t.values(col):
                            if val and len(str(val)) >= 3:
                                pat = r'\b' + re.escape(str(val)) + r'\b'
                                m = re.search(pat, nar, re.IGNORECASE)
                                if m:
                                    start, end = m.span()
                                    counterparty_raw = nar[start:end]
                                    break
                        if counterparty_raw:
                            break
                if counterparty_raw:
                    break

        # Strictly enforce provenance
        if counterparty_raw and counterparty_raw not in nar:
            counterparty_raw = None

        counterparty_match = resolve_counterparty(counterparty_raw, available_tables)

        project_code_raw = extract_project_word(nar, known_project_codes, counterparty_raw)
        if project_code_raw and project_code_raw not in nar:
            project_code_raw = None

        project_code_match = resolve_project_code(project_code_raw, available_tables)

        classification = classify_row(nar, counterparty_raw, counterparty_match, project_code_raw, project_code_match)

        row_out = dict(r)
        row_out['counterparty_raw'] = counterparty_raw
        row_out['counterparty_match'] = counterparty_match
        row_out['project_code_raw'] = project_code_raw
        row_out['project_code_match'] = project_code_match
        row_out['classification'] = classification

        resolved_rows.append(row_out)

    kit.write_result(resolved_rows)
    print(f"parsed {len(resolved_rows)} rows")


if __name__ == '__main__':
    main()