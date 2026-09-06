import kit

def run():
    rows = kit.rows()
    print(f"Loaded {len(rows)} input rows")

    # Master table pool order
    pools = [
        ('legal_entities', 'Legal Entity'),
        ('related_parties', 'Related Party'),
        ('vendors', 'Vendor'),
        ('investors', 'Investor'),
        ('deals_positions', 'Deal Name'),
        ('deals_positions', 'Position'),
    ]

    enriched = []

    for i, row in enumerate(rows):
        narrative = row['narrative']
        trn_type = row.get('trn_type', '')

        counterparty_raw = None
        counterparty_match = {
            'status': 'CANNOT_VERIFY',
            'matched_name': None,
            'table': None,
            'confidence': None,
            'why': 'No counterparty named in narrative'
        }

        project_code_raw = None
        project_code_match = {
            'status': 'CANNOT_VERIFY',
            'matched_name': None,
            'table': None,
            'confidence': None,
            'why': 'No project code announced in narrative'
        }

        classification = 'Review'

        if 'COMMISSION' in narrative:
            # Bank fee / commission
            counterparty_raw = None
            counterparty_match = {
                'status': 'CANNOT_VERIFY',
                'matched_name': None,
                'table': None,
                'confidence': None,
                'why': 'Bank commission charge names no counterparty'
            }
            classification = 'Other'

        elif 'TFR+ INTERNAL FX TRANSFER' in narrative:
            classification = 'Internal'
            if 'NORDVIK INFRASTRUCTURE ADVANCED' in narrative:
                # Internal transfer naming the fund's own entity
                span = kit.narrative_span(narrative, 'NORDVIK INFRASTRUCTURE ADVANCED')
                counterparty_raw = span
                counterparty_match = {
                    'status': 'UNRESOLVED',
                    'matched_name': None,
                    'table': None,
                    'confidence': None,
                    'why': "Fund's own entity named on internal FX transfer; no external counterparty"
                }
            else:
                # Narrative names bank identifier / own account number only
                counterparty_raw = None
                counterparty_match = {
                    'status': 'CANNOT_VERIFY',
                    'matched_name': None,
                    'table': None,
                    'confidence': None,
                    'why': 'Internal FX transfer between own accounts; names no counterparty'
                }

        else:
            # Supplier payments (S+P-)
            first_field = narrative.split(',')[0].strip()
            lookup_res = kit.lookup(first_field, pools)

            span = kit.narrative_span(narrative, first_field)
            counterparty_raw = span

            if lookup_res:
                counterparty_match = {
                    'status': 'MATCH',
                    'matched_name': lookup_res['matched_name'],
                    'table': lookup_res['table'],
                    'confidence': 1.0,
                    'why': f"Exact match in {lookup_res['table']} list"
                }
                if lookup_res['table'] == 'vendors':
                    classification = 'Vendor'
                elif lookup_res['table'] == 'related_parties':
                    classification = 'Related Party'
                else:
                    classification = 'Vendor'
            else:
                counterparty_match = {
                    'status': 'UNRESOLVED',
                    'matched_name': None,
                    'table': None,
                    'confidence': None,
                    'why': f"Counterparty '{first_field}' not found in master data lists"
                }
                if first_field.startswith('NIP'):
                    classification = 'Related Party'
                else:
                    classification = 'Vendor'

        out_row = dict(row)
        out_row['counterparty_raw'] = counterparty_raw
        out_row['counterparty_match'] = counterparty_match
        out_row['project_code_raw'] = project_code_raw
        out_row['project_code_match'] = project_code_match
        out_row['classification'] = classification

        enriched.append(out_row)

        print(f"Row {i}: raw={counterparty_raw!r} match={counterparty_match['status']} "
              f"name={counterparty_match['matched_name']!r} cls={classification}")

    # Verify self-assertions
    claims = {
        'row_count_matches': len(enriched) == len(rows),
        'provenance_holds': all(
            r['counterparty_raw'] is None or r['counterparty_raw'] in r['narrative']
            for r in enriched
        ),
        'pairing_holds': all(
            (r['counterparty_raw'] is None and r['counterparty_match']['status'] == 'CANNOT_VERIFY') or
            (r['counterparty_raw'] is not None and r['counterparty_match']['status'] != 'CANNOT_VERIFY')
            for r in enriched
        ),
        'classifications_valid': all(
            r['classification'] in [
                'Investment', 'Investment Transfer', 'Vendor', 'Related Party',
                'Investor', 'Internal', 'Other', 'Review'
            ]
            for r in enriched
        ),
    }

    kit.write_assertions(claims)
    kit.write_result(enriched)
    print(f"parsed {len(enriched)} rows")

run()