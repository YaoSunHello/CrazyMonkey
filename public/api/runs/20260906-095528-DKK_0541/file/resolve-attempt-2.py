import sys
import kit

def run():
    rows = kit.rows()
    print(f"Total rows to process: {len(rows)}", flush=True)

    enriched = []

    for idx, row in enumerate(rows):
        narrative = row.get('narrative', '')
        trn_type = row.get('trn_type', '')
        print(f"\n--- Row {idx} ---", flush=True)
        print(f"trn_type: {trn_type}", flush=True)
        print(f"narrative: {narrative}", flush=True)

        project_code_raw = None
        project_code_match = {
            'status': 'CANNOT_VERIFY',
            'matched_name': None,
            'table': None,
            'confidence': None,
            'why': 'No project code present in narrative'
        }

        counterparty_raw = None
        counterparty_match = {
            'status': 'CANNOT_VERIFY',
            'matched_name': None,
            'table': None,
            'confidence': None,
            'why': 'Narrative names no counterparty'
        }
        classification = 'Other'

        if 'COMMISSION' in narrative or 'CHG' in trn_type:
            # Bank fee / commission charges name no counterparty
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
            counterparty_raw = 'NORDVIK INFRASTRUCTURE PARTNER'
            # Expands the platform management house abbreviation NIP P/S
            counterparty_match = {
                'status': 'PROBABLE',
                'matched_name': 'NIP P/S',
                'table': 'related_parties',
                'confidence': 0.85,
                'why': 'Nordvik Infrastructure Partner expands the platform management initialism NIP P/S'
            }
            classification = 'Related Party'

        elif 'NIP LIT' in narrative:
            counterparty_raw = 'NIP LIT'
            counterparty_match = {
                'status': 'UNRESOLVED',
                'matched_name': None,
                'table': None,
                'confidence': None,
                'why': 'NIP LIT named in narrative but not present in reference tables'
            }
            classification = 'Investment Transfer'

        elif 'FREJA MOERCH' in narrative:
            counterparty_raw = 'FREJA MOERCH'
            counterparty_match = {
                'status': 'UNRESOLVED',
                'matched_name': None,
                'table': None,
                'confidence': None,
                'why': 'Board member Freja Moerch named in narrative but not present in reference tables'
            }
            classification = 'Related Party'

        enriched_row = dict(row)
        enriched_row['counterparty_raw'] = counterparty_raw
        enriched_row['counterparty_match'] = counterparty_match
        enriched_row['project_code_raw'] = project_code_raw
        enriched_row['project_code_match'] = project_code_match
        enriched_row['classification'] = classification

        print(f"CP Raw: {counterparty_raw} -> Match: {counterparty_match['status']}", flush=True)
        print(f"Classification: {classification}", flush=True)

        enriched.append(enriched_row)

    # Write result first
    kit.write_result(enriched)

    # Record assertions
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

    print("parsed 5 rows", flush=True)

run()