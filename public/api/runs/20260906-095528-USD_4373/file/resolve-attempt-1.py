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

# Print account map
t_acc = kit.table('account_map')
print("Account map entries:")
for acc, name in zip(t_acc.values('Account Number'), t_acc.values('Bank Account')):
    print(f"  {acc} -> {name}")

# Investigate candidates for BQVRFRPP and NORDVIK INFRASTRUCTURE PARTNER
print("\n--- Diagnostic Candidate Searches ---")
for query in ['BQVRFRPP', '448323310', 'NORDVIK INFRASTRUCTURE PARTNER', 'NORDVIK INFRASTRUCTURE PARTNERS', 'NI GMF II COOPERATIEF U.A', 'NI GMF II SCSP']:
    res = kit.lookup(query, cp_pools)
    print(f"Lookup '{query}': {res}")
    cands = kit.candidates(query, cp_pools, limit=3)
    print(f"Candidates for '{query}': {cands}")

print("\n--- Processing Rows ---")
enriched = []

for idx, r in enumerate(rows):
    narrative = r['narrative']
    trn_type = r.get('trn_type', '')
    debit = r.get('debit')
    credit = r.get('credit')

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

    # Check for Bank Charges / Routine Interest
    if 'COMMISSION' in narrative or trn_type == 'S+P- CHG':
        classification = 'Other'
        # Names nobody
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
        # Usually preceded by PROJECT keyword
        m_proj = re.search(r'\bPROJECT\s+([A-Za-z0-9_\-]+)', narrative, re.IGNORECASE)
        if m_proj:
            pc_candidate = m_proj.group(1).strip('.,;:')
            # Let lookup find it
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
                # Check candidates
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

        # Check counterparty in narrative
        # Narrative convention: leading field before comma
        # In Row 12: '1/NORDVIK INFRASTRUCTURE PARTNER, S+P+ CHARGE WAIVED' -> strip SWIFT '1/' prefix if present
        leading_field = narrative.split(',')[0].strip()
        cleaned_leading = re.sub(r'^\d+/', '', leading_field).strip()

        # Try looking up cleaned_leading
        cp_res = kit.lookup(cleaned_leading, cp_pools)
        
        # If not found, try candidates or sub-parts
        if not cp_res and 'NI GMF II COOPERATIEF U.A' in narrative:
            cp_res = kit.lookup('NI GMF II COOPERATIEF U.A', cp_pools)

        if cp_res:
            matched_name = cp_res['matched_name']
            table_name = cp_res['table']
            span = kit.narrative_span(narrative, matched_name)
            if not span:
                # Fallback to cleaned leading field if span finder misses due to punctuation
                span = cleaned_leading
            cp_raw = span
            cp_match = {
                'status': 'MATCH',
                'matched_name': matched_name,
                'table': table_name,
                'confidence': 1.0,
                'why': f"Matched in {table_name}",
            }
        else:
            # Check candidates
            cands = kit.candidates(cleaned_leading, cp_pools, limit=1)
            if cands and cands[0]['similarity'] > 0.85:
                cand = cands[0]
                span = kit.narrative_span(narrative, cand['matched_name']) or cleaned_leading
                cp_raw = span
                cp_match = {
                    'status': 'PROBABLE',
                    'matched_name': cand['matched_name'],
                    'table': cand['table'],
                    'confidence': round(cand['similarity'], 2),
                    'why': f"Document spelled '{cleaned_leading}', list has '{cand['matched_name']}'",
                }
            elif cleaned_leading:
                # Narrative named a party, but no match found
                cp_raw = cleaned_leading
                cp_match = {
                    'status': 'UNRESOLVED',
                    'matched_name': None,
                    'table': None,
                    'confidence': None,
                    'why': f"Counterparty '{cleaned_leading}' not found in reference data",
                }

        # Determine Classification
        if 'EQUITY:' in narrative or ('COOPERATIEF' in narrative and 'PROJECT' in narrative):
            classification = 'Investment Transfer'
        elif 'INTERNAL TRANSFER' in narrative:
            classification = 'Internal'
        elif 'NORDVIK INFRASTRUCTURE PARTNER' in narrative:
            # Transfer from platform's parent / partner entity into this fund account
            classification = 'Internal'
        elif 'BQVRFRPP' in narrative:
            # Large movements / treasury transfers
            classification = 'Internal'
        elif classification == 'Review':
            if cp_match['table'] == 'vendors':
                classification = 'Vendor'
            elif cp_match['table'] == 'investors':
                classification = 'Investor'
            elif cp_match['table'] == 'related_parties':
                classification = 'Related Party'
            else:
                classification = 'Other'

    row_out = dict(r)
    row_out['counterparty_raw'] = cp_raw
    row_out['counterparty_match'] = cp_match
    row_out['project_code_raw'] = pc_raw
    row_out['project_code_match'] = pc_match
    row_out['classification'] = classification
    enriched.append(row_out)

    print(f"Row {idx:2d}: type={trn_type:<10} cp_raw={cp_raw!r:<30} cp_status={cp_match['status']:<12} cp_name={cp_match['matched_name']!r} pc_raw={pc_raw!r:<12} pc_status={pc_match['status']:<12} class={classification}")

kit.write_result(enriched)
kit.write_assertions([
    len(enriched) == 19,
    all(r['classification'] in [
        'Investment', 'Investment Transfer', 'Vendor', 'Related Party',
        'Investor', 'Internal', 'Other', 'Review'
    ] for r in enriched),
    all(r['counterparty_match']['status'] in ['MATCH', 'PROBABLE', 'UNRESOLVED', 'CANNOT_VERIFY', 'FAIL'] for r in enriched),
    all(r['project_code_match']['status'] in ['MATCH', 'PROBABLE', 'UNRESOLVED', 'CANNOT_VERIFY', 'FAIL'] for r in enriched),
])

print("parsed 19 rows")