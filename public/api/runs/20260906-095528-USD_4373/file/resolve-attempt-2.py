import re
import kit

rows = kit.rows()
print(f"Total rows: {len(rows)}")

# Reference pools for counterparty
cp_pools = [
    ('related_parties', 'Related Party'),
    ('legal_entities', 'Legal Entity'),
    ('vendors', 'Vendor'),
    ('investors', 'Investor'),
    ('deals_positions', 'Deal Name'),
    ('deals_positions', 'Position'),
]

# Reference pools for project code
pc_pools = [
    ('project_codes', 'Project Code'),
    ('project_codes', 'New Project Code'),
]

enriched = []

for idx, r in enumerate(rows):
    narrative = r['narrative']
    trn_type = r.get('trn_type', '')

    cp_raw = None
    cp_match = {
        'status': 'CANNOT_VERIFY',
        'matched_name': None,
        'table': None,
        'confidence': None,
        'why': None,
    }

    pc_raw = None
    pc_match = {
        'status': 'CANNOT_VERIFY',
        'matched_name': None,
        'table': None,
        'confidence': None,
        'why': None,
    }

    classification = 'Review'

    # 1. Routine charges / interest naming nobody
    if 'COMMISSION' in narrative or trn_type == 'S+P- CHG':
        classification = 'Other'
        cp_raw = None
        cp_match = {
            'status': 'CANNOT_VERIFY',
            'matched_name': None,
            'table': None,
            'confidence': None,
            'why': None,
        }
    elif 'CREDIT INTEREST' in narrative or trn_type == 'S+P+ INT':
        classification = 'Other'
        cp_raw = None
        cp_match = {
            'status': 'CANNOT_VERIFY',
            'matched_name': None,
            'table': None,
            'confidence': None,
            'why': None,
        }
    else:
        # Check for project code first
        m_proj = re.search(r'\bPROJECT\s+([A-Za-z0-9_\-]+)', narrative, re.IGNORECASE)
        if m_proj:
            pc_candidate = m_proj.group(1).strip('.,;:')
            pc_res = kit.lookup(pc_candidate, pc_pools)
            if pc_res:
                pc_raw = pc_candidate
                pc_match = {
                    'status': 'MATCH',
                    'matched_name': pc_res['matched_name'],
                    'table': pc_res['table'],
                    'confidence': 1.0,
                    'why': f"Project code matched in {pc_res['table']}",
                }
            else:
                pc_cands = kit.candidates(pc_candidate, pc_pools, limit=1)
                pc_raw = pc_candidate
                if pc_cands and pc_cands[0]['similarity'] > 0.8:
                    pc_match = {
                        'status': 'PROBABLE',
                        'matched_name': pc_cands[0]['matched_name'],
                        'table': pc_cands[0]['table'],
                        'confidence': round(pc_cands[0]['similarity'], 2),
                        'why': f"Close match to {pc_cands[0]['matched_name']}",
                    }
                else:
                    pc_match = {
                        'status': 'UNRESOLVED',
                        'matched_name': None,
                        'table': None,
                        'confidence': None,
                        'why': f"Project code '{pc_candidate}' not found in project code reference data",
                    }

        # Check counterparty
        leading_field = narrative.split(',')[0].strip()
        cleaned_leading = re.sub(r'^\d+/', '', leading_field).strip()

        # Try exact lookup on cleaned_leading
        cp_res = kit.lookup(cleaned_leading, cp_pools)

        if not cp_res and 'NI GMF II COOPERATIEF U.A' in narrative:
            cp_res = kit.lookup('NI GMF II COOPERATIEF U.A', cp_pools)

        if cp_res:
            matched_name = cp_res['matched_name']
            table_name = cp_res['table']
            span = None
            try:
                span = kit.narrative_span(narrative, matched_name)
            except Exception:
                span = None
            if not span or span not in narrative:
                span = cleaned_leading if cleaned_leading in narrative else leading_field
            cp_raw = span
            cp_match = {
                'status': 'MATCH',
                'matched_name': matched_name,
                'table': table_name,
                'confidence': 1.0,
                'why': f"Matched in {table_name}",
            }
        else:
            # Check candidate for possible PROBABLE proposal
            cands = kit.candidates(cleaned_leading, cp_pools, limit=3)
            # Find candidate that matches base company name
            best_cand = None
            for c in cands:
                # If similarity is high and shares leading root word
                c_name = c['matched_name']
                if c['similarity'] > 0.8 and kit.compact(cleaned_leading)[:15] in kit.compact(c_name):
                    best_cand = c
                    break

            # Span must come directly from narrative text
            span = cleaned_leading if cleaned_leading in narrative else leading_field
            cp_raw = span

            if best_cand:
                cp_match = {
                    'status': 'PROBABLE',
                    'matched_name': best_cand['matched_name'],
                    'table': best_cand['table'],
                    'confidence': 0.8,
                    'why': f"Document wrote '{cleaned_leading}'; list holds '{best_cand['matched_name']}'",
                }
            else:
                cp_match = {
                    'status': 'UNRESOLVED',
                    'matched_name': None,
                    'table': None,
                    'confidence': None,
                    'why': f"Counterparty '{cleaned_leading}' not found in reference data",
                }

        # Classify the movement based on narrative intent and parties
        if 'EQUITY:' in narrative or ('COOPERATIEF' in narrative and 'PROJECT' in narrative):
            classification = 'Investment Transfer'
        elif 'INTERNAL TRANSFER' in narrative:
            classification = 'Internal'
        elif 'NORDVIK INFRASTRUCTURE PARTNER' in narrative:
            classification = 'Internal'
        elif 'BQVRFRPP' in narrative:
            classification = 'Internal'
        else:
            classification = 'Other'

    # Safety assertions on provenance
    if cp_raw is not None:
        assert cp_raw in narrative, f"Counterparty span {cp_raw!r} not found in narrative {narrative!r}"
    if pc_raw is not None:
        assert pc_raw in narrative, f"Project code span {pc_raw!r} not found in narrative {narrative!r}"

    row_out = dict(r)
    row_out['counterparty_raw'] = cp_raw
    row_out['counterparty_match'] = cp_match
    row_out['project_code_raw'] = pc_raw
    row_out['project_code_match'] = pc_match
    row_out['classification'] = classification
    enriched.append(row_out)

    print(f"Row {idx:2d}: type={trn_type:<10} cp_raw={cp_raw!r:<32} cp_status={cp_match['status']:<12} cp_name={cp_match['matched_name']!r} pc_raw={pc_raw!r:<12} pc_status={pc_match['status']:<12} class={classification}")

kit.write_result(enriched)
kit.write_assertions([
    len(enriched) == 19,
    all(
        r['counterparty_raw'] in r['narrative']
        for r in enriched
        if r['counterparty_raw'] is not None
    ),
    all(
        r['project_code_raw'] in r['narrative']
        for r in enriched
        if r['project_code_raw'] is not None
    ),
    all(
        r['classification'] in [
            'Investment', 'Investment Transfer', 'Vendor', 'Related Party',
            'Investor', 'Internal', 'Other', 'Review'
        ]
        for r in enriched
    ),
    all(
        r['counterparty_match']['status'] in ['MATCH', 'PROBABLE', 'UNRESOLVED', 'CANNOT_VERIFY', 'FAIL']
        for r in enriched
    ),
    all(
        r['project_code_match']['status'] in ['MATCH', 'PROBABLE', 'UNRESOLVED', 'CANNOT_VERIFY', 'FAIL']
        for r in enriched
    ),
])

print("parsed 19 rows")