import re
import kit


def lookup_counterparty(cand_str, tables):
    """
    Search reference lists in preference order:
    related_parties -> vendors -> investors -> legal_entities -> deals_positions
    """
    if not cand_str:
        return None, None

    variants = []
    raw = cand_str.strip()
    if raw:
        variants.append(raw)

    # Mid-word comma removal: e.g. "NORDVIK INFRASTR, UCTURE" -> "NORDVIK INFRASTRUCTURE"
    mw = re.sub(r'(\b\w+),\s*(\w+\b)', r'\1\2', raw).strip()
    if mw and mw not in variants:
        variants.append(mw)

    # Remove all commas
    no_c = re.sub(r'\s+', ' ', raw.replace(',', ' ')).strip()
    if no_c and no_c not in variants:
        variants.append(no_c)

    # Remove trailing punctuation (dots, dashes)
    no_dot = re.sub(r'[.\-]+$', '', raw).strip()
    if no_dot and no_dot not in variants:
        variants.append(no_dot)
    if mw:
        mw_nodot = re.sub(r'[.\-]+$', '', mw).strip()
        if mw_nodot and mw_nodot not in variants:
            variants.append(mw_nodot)

    table_preference = [
        'related_parties',
        'vendors',
        'investors',
        'legal_entities',
        'deals_positions',
    ]

    for tbl_name in table_preference:
        if tbl_name not in tables:
            continue
        t = kit.table(tbl_name)
        for col in t.columns:
            for v in variants:
                if t.contains(col, v):
                    # Prefer exact formatted value from t.values(col)
                    for actual_val in t.values(col):
                        if actual_val.strip().lower() == v.strip().lower():
                            return tbl_name, actual_val
                    # Fallback to t.find(col, v)
                    row = t.find(col, v)
                    if row is not None:
                        if isinstance(row, dict) and col in row:
                            return tbl_name, row[col]
                        elif hasattr(row, col):
                            return tbl_name, getattr(row, col)
                    return tbl_name, v

    return None, None


def lookup_project_code(raw_proj, tables):
    """
    Check if raw_proj matches an entry in the project_codes table.
    """
    if not raw_proj or 'project_codes' not in tables:
        return None, None

    t = kit.table('project_codes')
    cand = raw_proj.strip()
    cols = ['Project Code', 'New Project Code'] + [
        c for c in t.columns if c not in ['Project Code', 'New Project Code']
    ]

    for col in cols:
        if col in t.columns and t.contains(col, cand):
            for actual_val in t.values(col):
                if actual_val.strip().lower() == cand.lower():
                    return 'project_codes', actual_val
            row = t.find(col, cand)
            if row is not None:
                if isinstance(row, dict) and col in row:
                    return 'project_codes', row[col]
                elif hasattr(row, col):
                    return 'project_codes', getattr(row, col)
            return 'project_codes', cand

    return None, None


def classify_row(row, cp_match, proj_match, cp_raw, proj_raw, narrative):
    """
    Classify the row into one of the 8 declared labels based on the narrative.
    """
    nu = narrative.upper()
    cp_table = cp_match.get('table')
    has_from_to = bool(re.search(r'\bFROM\b.+\bTO\b', narrative, re.IGNORECASE))
    has_project = (proj_raw is not None) or bool(re.search(r'\b(?:PROJECT|PRJ)\b', nu))

    # Routine bank charges or interest
    is_routine_bank = any(
        kw in nu
        for kw in [
            'BANK CHARGE',
            'BANK CHARGES',
            'SERVICE CHARGE',
            'MAINTENANCE FEE',
            'ACCOUNT FEE',
            'COMMISSION',
            'CHG',
            'POSTAGE',
        ]
    )
    is_bank_interest = any(
        kw in nu
        for kw in [
            'CREDIT INTEREST',
            'DEBIT INTEREST',
            'INTEREST PAID',
            'INTEREST RECEIVED',
        ]
    ) and ('LOAN' not in nu and 'FACILITY' not in nu)

    if (is_routine_bank or is_bank_interest) and cp_raw is None:
        return 'Other'
    if is_routine_bank and cp_table not in ['vendors', 'related_parties']:
        return 'Other'

    # Investor movements
    if cp_table == 'investors':
        return 'Investor'
    if any(
        kw in nu
        for kw in [
            'CAPITAL CALL',
            'DISTRIBUTION',
            'DRAWDOWN',
            'REDEMPTION',
            'SUBSCRIPTION',
        ]
    ):
        if not ('SHARES' in nu and 'PROJECT' in nu):
            return 'Investor'

    # Internal transfer between platform accounts
    if any(
        kw in nu
        for kw in [
            'INTERNAL TRANSFER',
            'TRANSFER BETWEEN ACCOUNTS',
            'OWN ACCOUNT TRANSFER',
            'SWEEP',
        ]
    ):
        return 'Internal'

    # Investment Transfer: moved between two platform entities to fund/settle an investment
    if has_from_to and has_project:
        return 'Investment Transfer'
    if has_from_to and any(
        kw in nu
        for kw in ['LOAN', 'INVESTMENT', 'FUNDING', 'EQUITY', 'PRINCIPAL']
    ):
        return 'Investment Transfer'
    if cp_table in ['related_parties', 'legal_entities'] and (
        has_project or 'TRANSFER' in nu
    ):
        if any(
            kw in nu
            for kw in [
                'LOAN',
                'INVESTMENT',
                'FUNDING',
                'EQUITY',
                'PRINCIPAL',
                'SETTLEMENT',
            ]
        ):
            return 'Investment Transfer'

    # Direct Investment
    if any(
        kw in nu
        for kw in [
            'INVESTMENT',
            'ACQUISITION',
            'EQUITY',
            'PURCHASE OF SHARES',
            'SHARE PURCHASE',
        ]
    ):
        return 'Investment'
    if (
        'LOAN' in nu
        or 'FACILITY' in nu
        or 'FUNDING' in nu
        or 'PRINCIPAL' in nu
    ) and (has_project or cp_raw is not None):
        return 'Investment'

    # Vendor payment
    if cp_table == 'vendors':
        return 'Vendor'
    if any(
        kw in nu
        for kw in [
            'INVOICE',
            'INV:',
            'AUDIT',
            'LEGAL FEE',
            'TAX ADVISORY',
            'CONSULTING',
            'SUPPLIER',
        ]
    ):
        return 'Vendor'

    # Related Party movements not funding an investment
    if any(
        kw in nu
        for kw in [
            'MANAGEMENT FEE',
            'MONITORING FEE',
            'EXPENSE RECHARGE',
            'REBATE',
            'DIRECTOR FEE',
            'SETTLING OF BALANCES',
            'SETTLEMENT OF BALANCES',
        ]
    ):
        return 'Related Party'
    if cp_table == 'related_parties' and any(
        kw in nu for kw in ['FEE', 'RECHARGE', 'EXPENSE', 'SETTLEMENT']
    ):
        return 'Related Party'

    if is_routine_bank or is_bank_interest or 'BANK' in nu or 'INTEREST' in nu:
        return 'Other'

    if cp_table == 'related_parties':
        return 'Related Party'

    return 'Review'


def resolve_all():
    rows = kit.rows()
    tables = kit.tables()

    sample_row = rows[0] if rows else {}
    narrative_key = (
        'narrative'
        if 'narrative' in sample_row
        else next(
            (
                k
                for k in sample_row
                if 'narr' in k.lower()
                or 'desc' in k.lower()
                or 'detail' in k.lower()
            ),
            'narrative',
        )
    )
    account_key = (
        'account_number'
        if 'account_number' in sample_row
        else next(
            (
                k
                for k in sample_row
                if 'account' in k.lower() or 'acct' in k.lower()
            ),
            'account_number',
        )
    )

    # 1. Identify account owner per account_number (the recurring statement entity)
    by_account = {}
    for r in rows:
        acc = r.get(account_key, 'default')
        by_account.setdefault(acc, []).append(r)

    account_owners = {}
    for acc, acc_rows in by_account.items():
        entity_counts = {}
        for r in acc_rows:
            narr = str(r.get(narrative_key, ''))
            m_ft = re.search(
                r'\bFROM\s+(.+?)\s+\bTO\s+(.+)', narr, re.IGNORECASE
            )
            if m_ft:
                p1 = m_ft.group(1).strip()
                p2 = m_ft.group(2).strip()
                p2 = re.sub(
                    r'\s+[-/]?\s*(?:PROJECT|PRJ)(?:\s+CODE)?\s*[:#-]?\s*[A-Za-z0-9_-]+.*$',
                    '',
                    p2,
                    flags=re.IGNORECASE,
                )
                p2 = re.sub(
                    r'\s+[-/]\s*(?:REF|INV|INVOICE|VAL|VALUE|TRN|LOAN|ACC|ACCOUNT)\b.*$',
                    '',
                    p2,
                    flags=re.IGNORECASE,
                )
                p2 = p2.strip(' -/;:,')
                for p in [p1, p2]:
                    p_norm = re.sub(
                        r'(\b\w+),\s*(\w+\b)', r'\1\2', p
                    ).strip().upper()
                    entity_counts[p_norm] = entity_counts.get(p_norm, 0) + 1
            elif 'legal_entities' in tables:
                t_le = kit.table('legal_entities')
                for col in t_le.columns:
                    for val in t_le.values(col):
                        if val and val.upper() in narr.upper():
                            entity_counts[val.upper()] = (
                                entity_counts.get(val.upper(), 0) + 1
                            )

        if entity_counts:
            sorted_entities = sorted(
                entity_counts.items(), key=lambda x: x[1], reverse=True
            )
            if sorted_entities[0][1] >= 2 or len(sorted_entities) == 1:
                account_owners[acc] = sorted_entities[0][0]

    # 2. Resolve counterparty and project code for each row
    for r in rows:
        narrative = str(r.get(narrative_key, ''))
        acc = r.get(account_key, 'default')
        owner = account_owners.get(acc, '')

        # --- Project Code Extraction ---
        proj_raw = None
        m_proj = re.search(
            r'\b(?:PROJECT|PRJ)(?:\s+CODE)?\s*[:#-]?\s*([A-Za-z0-9_-]+)',
            narrative,
            re.IGNORECASE,
        )
        if m_proj:
            proj_raw = narrative[m_proj.start(1) : m_proj.end(1)]
        elif 'project_codes' in tables:
            t_pc = kit.table('project_codes')
            known_projs = []
            for col in t_pc.columns:
                for val in t_pc.values(col):
                    if val and len(val.strip()) >= 3:
                        known_projs.append(val.strip())
            known_projs.sort(key=len, reverse=True)
            for kp in known_projs:
                m_kp = re.search(
                    r'\b' + re.escape(kp) + r'\b', narrative, re.IGNORECASE
                )
                if m_kp:
                    rest_after = narrative[m_kp.end() : m_kp.end() + 15].upper()
                    if not re.match(
                        r'^\s*(?:HOLDCO|LIMITED|LTD|CORP|INC|SCSP|GP|LP)\b',
                        rest_after,
                    ):
                        proj_raw = narrative[m_kp.start() : m_kp.end()]
                        break

        if proj_raw is not None:
            tbl_proj, matched_proj = lookup_project_code(proj_raw, tables)
            if tbl_proj is not None:
                project_code_match = {
                    'status': 'MATCH',
                    'matched_name': matched_proj,
                    'table': tbl_proj,
                }
            else:
                project_code_match = {
                    'status': 'UNRESOLVED',
                    'matched_name': None,
                    'table': None,
                }
        else:
            project_code_match = {
                'status': 'CANNOT_VERIFY',
                'matched_name': None,
                'table': None,
            }

        # --- Counterparty Extraction ---
        cp_raw = None
        m_ft = re.search(
            r'\bFROM\s+(.+?)\s+\bTO\s+(.+)', narrative, re.IGNORECASE
        )
        if m_ft:
            p1_raw = m_ft.group(1).strip()
            p2_raw = m_ft.group(2).strip()

            m_clause = re.search(
                r'\s+[-/]?\s*(?:PROJECT|PRJ)(?:\s+CODE)?\s*[:#-]?\s*[A-Za-z0-9_-]+',
                p2_raw,
                re.IGNORECASE,
            )
            if not m_clause:
                m_clause = re.search(
                    r'\s+[-/]\s*(?:REF|INV|INVOICE|VAL|VALUE|TRN|LOAN|ACC|ACCOUNT)\b',
                    p2_raw,
                    re.IGNORECASE,
                )
            if not m_clause:
                m_clause = re.search(r'\s+[-/]\s+', p2_raw)

            if m_clause:
                p2_clean = p2_raw[: m_clause.start()].strip(' -/;:,')
            else:
                p2_clean = p2_raw.strip(' -/;:,')

            p1_norm = re.sub(
                r'(\b\w+),\s*(\w+\b)', r'\1\2', p1_raw
            ).strip().upper()
            p2_norm = re.sub(
                r'(\b\w+),\s*(\w+\b)', r'\1\2', p2_clean
            ).strip().upper()

            p1_is_owner = bool(owner and (owner in p1_norm or p1_norm in owner))
            p2_is_owner = bool(owner and (owner in p2_norm or p2_norm in owner))

            if p1_is_owner and not p2_is_owner:
                cp_raw = p2_clean
            elif p2_is_owner and not p1_is_owner:
                cp_raw = p1_raw
            else:
                tbl1, _ = lookup_counterparty(p1_raw, tables)
                tbl2, _ = lookup_counterparty(p2_clean, tables)
                if tbl2 and not tbl1:
                    cp_raw = p2_clean
                elif tbl1 and not tbl2:
                    cp_raw = p1_raw
                else:
                    amt = r.get('amount', 0)
                    try:
                        amt_val = float(amt)
                    except Exception:
                        amt_val = 0
                    cp_raw = p2_clean if amt_val < 0 else p1_raw

        if cp_raw is None:
            m_to = re.search(
                r'\b(?:PAYMENT\s+TO|TRANSFER\s+TO|TRF\s+TO|LOAN\s+TO|TO)\s+([^\n\r]+)',
                narrative,
                re.IGNORECASE,
            )
            if m_to:
                cand = m_to.group(1).strip()
                m_cl = re.search(
                    r'\s+[-/]?\s*(?:PROJECT|PRJ)(?:\s+CODE)?\s*[:#-]?\s*[A-Za-z0-9_-]+',
                    cand,
                    re.IGNORECASE,
                )
                if not m_cl:
                    m_cl = re.search(
                        r'\s+[-/]\s*(?:REF|INV|INVOICE|VAL|VALUE|TRN|LOAN|ACC|ACCOUNT)\b',
                        cand,
                        re.IGNORECASE,
                    )
                if not m_cl:
                    m_cl = re.search(r'\s+[-/]\s+', cand)
                cand = (
                    cand[: m_cl.start()].strip(' -/;:,')
                    if m_cl
                    else cand.strip(' -/;:,')
                )
                cand_norm = re.sub(
                    r'(\b\w+),\s*(\w+\b)', r'\1\2', cand
                ).strip().upper()
                if not (owner and (owner in cand_norm or cand_norm in owner)):
                    cp_raw = cand

        if cp_raw is None:
            m_from = re.search(
                r'\b(?:PAYMENT\s+FROM|TRANSFER\s+FROM|TRF\s+FROM|RECEIVED\s+FROM|FROM)\s+([^\n\r]+)',
                narrative,
                re.IGNORECASE,
            )
            if m_from:
                cand = m_from.group(1).strip()
                m_cl = re.search(
                    r'\s+[-/]?\s*(?:PROJECT|PRJ)(?:\s+CODE)?\s*[:#-]?\s*[A-Za-z0-9_-]+',
                    cand,
                    re.IGNORECASE,
                )
                if not m_cl:
                    m_cl = re.search(
                        r'\s+[-/]\s*(?:REF|INV|INVOICE|VAL|VALUE|TRN|LOAN|ACC|ACCOUNT)\b',
                        cand,
                        re.IGNORECASE,
                    )
                if not m_cl:
                    m_cl = re.search(r'\s+[-/]\s+', cand)
                cand = (
                    cand[: m_cl.start()].strip(' -/;:,')
                    if m_cl
                    else cand.strip(' -/;:,')
                )
                cand_norm = re.sub(
                    r'(\b\w+),\s*(\w+\b)', r'\1\2', cand
                ).strip().upper()
                if not (owner and (owner in cand_norm or cand_norm in owner)):
                    cp_raw = cand

        if cp_raw is None:
            # Check reference tables in priority order for whole-word matches in narrative
            table_preference = [
                'related_parties',
                'vendors',
                'investors',
                'legal_entities',
                'deals_positions',
            ]
            for tbl_name in table_preference:
                if tbl_name not in tables or cp_raw is not None:
                    continue
                t = kit.table(tbl_name)
                for col in t.columns:
                    for val in t.values(col):
                        if not val or len(val.strip()) < 3:
                            continue
                        val_s = val.strip()
                        m_val = re.search(
                            r'\b' + re.escape(val_s) + r'\b',
                            narrative,
                            re.IGNORECASE,
                        )
                        if m_val:
                            matched_sub = narrative[
                                m_val.start() : m_val.end()
                            ]
                            matched_norm = matched_sub.strip().upper()
                            if not (
                                owner
                                and (
                                    owner in matched_norm
                                    or matched_norm in owner
                                )
                            ):
                                cp_raw = matched_sub
                                break
                    if cp_raw is not None:
                        break

        # Verification of provenance (must be an exact substring of narrative)
        if cp_raw is not None and cp_raw not in narrative:
            cp_raw = None
        if proj_raw is not None and proj_raw not in narrative:
            proj_raw = None

        # Build counterparty_match
        if cp_raw is not None:
            tbl_cp, matched_cp = lookup_counterparty(cp_raw, tables)
            if tbl_cp is not None:
                counterparty_match = {
                    'status': 'MATCH',
                    'matched_name': matched_cp,
                    'table': tbl_cp,
                }
            else:
                counterparty_match = {
                    'status': 'UNRESOLVED',
                    'matched_name': None,
                    'table': None,
                }
        else:
            counterparty_match = {
                'status': 'CANNOT_VERIFY',
                'matched_name': None,
                'table': None,
            }

        # Classify the row
        classification = classify_row(
            r, counterparty_match, project_code_match, cp_raw, proj_raw, narrative
        )

        r['counterparty_raw'] = cp_raw
        r['counterparty_match'] = counterparty_match
        r['project_code_raw'] = proj_raw
        r['project_code_match'] = project_code_match
        r['classification'] = classification

    kit.write_result(rows)
    print(f'parsed {len(rows)} rows')


if __name__ == '__main__':
    resolve_all()