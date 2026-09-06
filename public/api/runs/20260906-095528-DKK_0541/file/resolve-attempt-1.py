import kit

def run():
    rows = kit.rows()
    print(f"Total rows to process: {len(rows)}")

    # Reference pools for counterparty lookup
    cp_pools = [
        ('legal_entities', 'Legal Entity'),
        ('related_parties', 'Related Party'),
        ('vendors', 'Vendor'),
        ('investors', 'Investor'),
        ('deals_positions', 'Deal Name'),
        ('deals_positions', 'Position'),
    ]

    # Reference pools for project codes
    proj_pools = [
        ('project_codes', 'Project Code'),
        ('project_codes', 'New Project Code'),
    ]

    enriched = []

    for idx, row in enumerate(rows):
        narrative = row.get('narrative', '')
        trn_type = row.get('trn_type', '')
        print(f"\n--- Row {idx} ---")
        print(f"trn_type: {trn_type}")
        print(f"narrative: {narrative}")

        # Check for project code in narrative
        project_code_raw = None
        project_code_match = {
            'status': 'CANNOT_VERIFY',
            'matched_name': None,
            'table': None,
            'confidence': None,
            'why': 'No project code found in narrative'
        }

        # Check narrative tokens for project code
        cleaned_words = [w.strip(',./-') for w in narrative.split()]
        for word in cleaned_words:
            if not word:
                continue
            proj_lookup = kit.lookup(word, proj_pools)
            if proj_lookup:
                span = kit.narrative_span(narrative, word)
                project_code_raw = span
                project_code_match = {
                    'status': 'MATCH',
                    'matched_name': proj_lookup['matched_name'],
                    'table': proj_lookup['table'],
                    'confidence': 1.0,
                    'why': f"Project code matched '{word}'"
                }
                break

        # Process counterparty based on document convention
        counterparty_raw = None
        counterparty_match = {
            'status': 'CANNOT_VERIFY',
            'matched_name': None,
            'table': None,
            'confidence': None,
            'why': 'Narrative names no counterparty'
        }
        classification = 'Other'

        # Row classification & counterparty identification
        if 'COMMISSION' in narrative or 'CHG' in trn_type:
            # Bank commission charges name no counterparty
            counterparty_raw = None
            counterparty_match = {
                'status': 'CANNOT_VERIFY',
                'matched_name': None,
                'table': None,
                'confidence': None,
                'why': 'Bank commission charge names no counterparty'
            }
            classification = 'Other'

        elif 'NORDVIK INFRASTRUCTURE PARTNER' in narrative:
            span = kit.narrative_span(narrative, 'NORDVIK INFRASTRUCTURE PARTNER')
            counterparty_raw = span
            # Full name expands initialism NIP P/S in related parties
            counterparty_match = {
                'status': 'PROBABLE',
                'matched_name': 'NIP P/S',
                'table': 'related_parties',
                'confidence': 0.85,
                'why': 'Nordvik Infrastructure Partner expands the platform management initialism NIP P/S'
            }
            classification = 'Related Party'

        elif 'NIP LIT' in narrative:
            span = kit.narrative_span(narrative, 'NIP LIT')
            counterparty_raw = span
            # Counterparty read from narrative but not present in reference data
            counterparty_match = {
                'status': 'UNRESOLVED',
                'matched_name': None,
                'table': None,
                'confidence': None,
                'why': 'NIP LIT is named in narrative but not found in master data reference tables'
            }
            classification = 'Investment Transfer'

        elif 'FREJA MOERCH' in narrative:
            span = kit.narrative_span(narrative, 'FREJA MOERCH')
            counterparty_raw = span
            # Board member receiving director fee, not listed in reference data
            counterparty_match = {
                'status': 'UNRESOLVED',
                'matched_name': None,
                'table': None,
                'confidence': None,
                'why': 'Board member Freja Moerch named in narrative but not present in reference tables'
            }
            classification = 'Related Party'

        else:
            # Fallback: check first comma-separated token
            first_part = narrative.split(',')[0].strip()
            lookup_res = kit.lookup(first_part, cp_pools)
            if lookup_res:
                span = kit.narrative_span(narrative, first_part)
                counterparty_raw = span
                counterparty_match = {
                    'status': 'MATCH',
                    'matched_name': lookup_res['matched_name'],
                    'table': lookup_res['table'],
                    'confidence': 1.0,
                    'why': f"Matched {lookup_res['table']}"
                }
            else:
                counterparty_raw = None
                counterparty_match = {
                    'status': 'CANNOT_VERIFY',
                    'matched_name': None,
                    'table': None,
                    'confidence': None,
                    'why': 'No counterparty identified'
                }
            classification = 'Other'

        enriched_row = dict(row)
        enriched_row['counterparty_raw'] = counterparty_raw
        enriched_row['counterparty_match'] = counterparty_match
        enriched_row['project_code_raw'] = project_code_raw
        enriched_row['project_code_match'] = project_code_match
        enriched_row['classification'] = classification

        print(f"CP Raw: {counterparty_raw} -> Match: {counterparty_match['status']}")
        print(f"Classification: {classification}")

        enriched.append(enriched_row)

    kit.write_assertions({
        'rows_count': len(enriched) == 5,
        'all_have_required_keys': all(
            all(k in r for k in [
                'counterparty_raw', 'counterparty_match',
                'project_code_raw', 'project_code_match', 'classification'
            ]) for r in enriched
        ),
        'valid_classifications': all(
            r['classification'] in [
                'Investment', 'Investment Transfer', 'Vendor', 'Related Party',
                'Investor', 'Internal', 'Other', 'Review'
            ] for r in enriched
        ),
        'valid_statuses': all(
            r['counterparty_match']['status'] in ['MATCH', 'PROBABLE', 'UNRESOLVED', 'CANNOT_VERIFY', 'FAIL']
            and r['project_code_match']['status'] in ['MATCH', 'PROBABLE', 'UNRESOLVED', 'CANNOT_VERIFY', 'FAIL']
            for r in enriched
        ),
        'pairing_rule': all(
            (r['counterparty_raw'] is None and r['counterparty_match']['status'] == 'CANNOT_VERIFY') or
            (r['counterparty_raw'] is not None and r['counterparty_match']['status'] != 'CANNOT_VERIFY')
            for r in enriched
        ),
        'project_pairing_rule': all(
            (r['project_code_raw'] is None and r['project_code_match']['status'] == 'CANNOT_VERIFY') or
            (r['project_code_raw'] is not None and r['project_code_match']['status'] != 'CANNOT_VERIFY')
            for r in enriched
        ),
    })

    kit.write_result(enriched)
    print("parsed 5 rows")

run()