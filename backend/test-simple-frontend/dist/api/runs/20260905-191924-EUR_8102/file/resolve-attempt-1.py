import re
import kit

def clean_text(s):
    if not s:
        return ""
    return re.sub(r'\s+', ' ', s).strip()

def unwrap_commas(s):
    if not s:
        return ""
    # Banks wrap mid-word with inserted commas: e.g. "INFRASTR, UCTURE" -> "INFRASTRUCTURE"
    return re.sub(r'([A-Za-z]+),\s*([A-Za-z]+)', r'\1\2', s)

def normalize_alphanumeric(s):
    if not s:
        return ""
    return re.sub(r'[^A-Za-z0-9]', '', s).upper()

def build_table_indices():
    tables_order = ['related_parties', 'vendors', 'investors', 'legal_entities', 'deals_positions']
    table_data = {}
    for name in tables_order + ['project_codes']:
        t = kit.table(name)
        entries = []
        for col in t.columns:
            for val in t.values(col):
                if val:
                    entries.append((col, val))
        table_data[name] = {
            'table': t,
            'entries': entries
        }
    return table_data

def lookup_entity(raw_name, table_data):
    if not raw_name:
        return None, None
    
    tables_order = ['related_parties', 'vendors', 'investors', 'legal_entities', 'deals_positions']
    
    unwrapped = unwrap_commas(raw_name)
    norm_raw = normalize_alphanumeric(raw_name)
    norm_unwrapped = normalize_alphanumeric(unwrapped)
    
    for t_name in tables_order:
        t_info = table_data[t_name]
        t = t_info['table']
        
        # 1. Direct contains check (exact or case-insensitive)
        for col in t.columns:
            if t.contains(col, raw_name):
                row = t.find(col, raw_name)
                return t_name, row[col]
            if unwrapped != raw_name and t.contains(col, unwrapped):
                row = t.find(col, unwrapped)
                return t_name, row[col]
        
        # 2. Normalized alphanumeric exact match against table values
        for col, val in t_info['entries']:
            norm_val = normalize_alphanumeric(val)
            if norm_val and (norm_val == norm_raw or norm_val == norm_unwrapped):
                return t_name, val
                
    return None, None

def lookup_project_code(raw_code, table_data):
    if not raw_code:
        return None, None
    
    unwrapped = unwrap_commas(raw_code)
    norm_raw = normalize_alphanumeric(raw_code)
    norm_unwrapped = normalize_alphanumeric(unwrapped)
    
    for t_name in ['project_codes', 'deals_positions']:
        t_info = table_data[t_name]
        t = t_info['table']
        
        for col in t.columns:
            if t.contains(col, raw_code):
                row = t.find(col, raw_code)
                return t_name, row[col]
            if unwrapped != raw_code and t.contains(col, unwrapped):
                row = t.find(col, unwrapped)
                return t_name, row[col]
                
        for col, val in t_info['entries']:
            norm_val = normalize_alphanumeric(val)
            if norm_val and (norm_val == norm_raw or norm_val == norm_unwrapped):
                return t_name, val
                
    return None, None

def extract_project_code(narrative, table_data):
    if not narrative:
        return None
    
    # Check after PROJECT / PRJ keyword
    m = re.search(r'\b(?:PROJECT|PRJ|PROJ)\b\s*[:#-]?\s*([A-Za-z0-9_-]+)', narrative, re.IGNORECASE)
    if m:
        word = m.group(1)
        # Ensure it appears verbatim in narrative
        start, end = m.span(1)
        return narrative[start:end]
    
    # Check if a known project code from the table appears as a standalone word
    pc_info = table_data['project_codes']
    for col, val in pc_info['entries']:
        pattern = r'\b' + re.escape(val) + r'\b'
        match = re.search(pattern, narrative, re.IGNORECASE)
        if match:
            start, end = match.span()
            return narrative[start:end]
            
    return None

def find_parties_in_narrative(narrative):
    if not narrative:
        return None, None
    
    # Common SWIFT / bank statement patterns: FROM ... TO ...
    # Party names may contain wrapped commas mid-word, e.g. "NORDVIK INFRASTR, UCTURE V SCSP"
    from_to = re.search(
        r'\bFROM\b\s+([A-Za-z0-9,.\s&/-]+?)\s+\bTO\b\s+([A-Za-z0-9,.\s&/-]+)',
        narrative,
        re.IGNORECASE
    )
    if from_to:
        p1_raw = from_to.group(1)
        p2_raw = from_to.group(2)
        
        # Stop p2 before trailing keywords like PROJECT, PRJ, REF, INV, VAL DATE
        p2_trimmed = re.split(r'\b(?:PROJECT|PRJ|PROJ|REF|REFERENCE|INV|INVOICE|VAL\s+DATE|VALUE\s+DATE)\b', p2_raw, flags=re.IGNORECASE)[0]
        
        # Slicing from narrative for provenance
        span1_start = narrative.find(p1_raw, from_to.start())
        span1_end = span1_start + len(p1_raw.rstrip(' -:\t'))
        
        span2_start = narrative.find(p2_trimmed, from_to.start(2))
        span2_end = span2_start + len(p2_trimmed.rstrip(' -:\t'))
        
        p1 = narrative[span1_start:span1_end].strip(' -:\t')
        p2 = narrative[span2_start:span2_end].strip(' -:\t')
        return p1, p2
    
    to_from = re.search(
        r'\bTO\b\s+([A-Za-z0-9,.\s&/-]+?)\s+\bFROM\b\s+([A-Za-z0-9,.\s&/-]+)',
        narrative,
        re.IGNORECASE
    )
    if to_from:
        p1_raw = to_from.group(1)
        p2_raw = to_from.group(2)
        p2_trimmed = re.split(r'\b(?:PROJECT|PRJ|PROJ|REF|REFERENCE|INV|INVOICE|VAL\s+DATE|VALUE\s+DATE)\b', p2_raw, flags=re.IGNORECASE)[0]
        
        span1_start = narrative.find(p1_raw, to_from.start())
        span1_end = span1_start + len(p1_raw.rstrip(' -:\t'))
        
        span2_start = narrative.find(p2_trimmed, to_from.start(2))
        span2_end = span2_start + len(p2_trimmed.rstrip(' -:\t'))
        
        p1 = narrative[span1_start:span1_end].strip(' -:\t')
        p2 = narrative[span2_start:span2_end].strip(' -:\t')
        return p2, p1  # return as from, to
        
    return None, None

def find_single_party(narrative):
    if not narrative:
        return None
    
    # Patterns naming one side: TO ..., FROM ..., BENEFICIARY ..., ORD ...
    patterns = [
        r'\b(?:PAYMENT\s+TO|PMT\s+TO|TRANSFER\s+TO|TRF\s+TO|LOAN\s+TO|PAID\s+TO|TO[:\s]+)\s*([A-Za-z0-9,.\s&/-]+)',
        r'\b(?:RECEIVED\s+FROM|PAYMENT\s+FROM|PMT\s+FROM|TRANSFER\s+FROM|TRF\s+FROM|FROM[:\s]+)\s*([A-Za-z0-9,.\s&/-]+)',
        r'\b(?:BENEFICIARY|BENE|BEN|BNF)[:\s]+([A-Za-z0-9,.\s&/-]+)',
        r'\b(?:ORDERING\s+CUSTOMER|ORDERING\s+PARTY|ORD|ORDP)[:\s]+([A-Za-z0-9,.\s&/-]+)',
        r'\bFBO[:\s]+([A-Za-z0-9,.\s&/-]+)'
    ]
    for pat in patterns:
        m = re.search(pat, narrative, re.IGNORECASE)
        if m:
            raw = m.group(1)
            trimmed = re.split(r'\b(?:PROJECT|PRJ|PROJ|REF|REFERENCE|INV|INVOICE|VAL\s+DATE|VALUE\s+DATE)\b', raw, flags=re.IGNORECASE)[0]
            start = narrative.find(trimmed, m.start(1))
            end = start + len(trimmed.rstrip(' -:\t'))
            cand = narrative[start:end].strip(' -:\t')
            if cand:
                return cand
    return None

def determine_own_entities(rows, table_data):
    # Determine the recurrent entity for each account_number
    account_candidates = {}
    for r in rows:
        acc = r.get('account_number')
        narrative = r.get('narrative', '')
        p_from, p_to = find_parties_in_narrative(narrative)
        cands = []
        if p_from:
            cands.append(p_from)
        if p_to:
            cands.append(p_to)
        if not cands:
            single = find_single_party(narrative)
            if single:
                cands.append(single)
                
        if acc not in account_candidates:
            account_candidates[acc] = []
        for c in cands:
            account_candidates[acc].append(c)
            
    own_entities = {}
    for acc, cands in account_candidates.items():
        if not cands:
            own_entities[acc] = set()
            continue
        # Group by normalized form
        counts = {}
        for c in cands:
            norm = normalize_alphanumeric(unwrap_commas(c))
            counts[norm] = counts.get(norm, 0) + 1
        
        # The entity that recurs on nearly every row of the account
        # Also check if it resolves to legal_entities or related_parties
        best_norm = max(counts.keys(), key=lambda k: counts[k])
        own_set = {best_norm}
        
        # If it's a known legal entity / related party, also add its other normalized names
        for t_name in ['legal_entities', 'related_parties']:
            for col, val in table_data[t_name]['entries']:
                if normalize_alphanumeric(val) == best_norm:
                    own_set.add(normalize_alphanumeric(val))
                    
        own_entities[acc] = own_set
        
    return own_entities

def classify_row(narrative, cp_raw, cp_table, cp_match_name, prj_raw, prj_table):
    upper = narrative.upper()
    
    # Other: bank charges, interest, routine fees
    if any(k in upper for k in ['BANK CHARGES', 'BANK CHARGE', 'MONTHLY FEE', 'ACCOUNT FEE', 'SERVICE CHARGE', 
                                'CREDIT INTEREST', 'DEBIT INTEREST', 'INTEREST CHARGE', 'INTEREST PAID', 
                                'COMMISSION', 'SWIFT FEE', 'CABLE EXPENSE']):
        if not cp_raw or cp_table is None:
            return "Other"
            
    # Internal: transfer between platform's own accounts
    if any(k in upper for k in ['INTERNAL TRANSFER', 'BETWEEN ACCOUNTS', 'CASH SWEEP', 'SWEEP', 'ZERO BALANCE SWEEP']):
        return "Internal"
        
    # Investor: capital calls, distributions
    if cp_table == 'investors' or any(k in upper for k in ['CAPITAL CALL', 'CALL #', 'LP CONTRIBUTION', 'DISTRIBUTION', 'EQUALISATION']):
        return "Investor"
        
    # Investment Transfer: money moved between platform's own entities to fund an investment
    has_from_to = bool(re.search(r'\bFROM\b.+\bTO\b', narrative, re.IGNORECASE))
    if has_from_to and (prj_raw is not None or 'LOAN' in upper or 'FUNDING' in upper or 'TRANSFER' in upper):
        return "Investment Transfer"
    if 'INVESTMENT TRANSFER' in upper:
        return "Investment Transfer"
        
    # Vendor: paying a supplier
    if cp_table == 'vendors' or any(k in upper for k in ['INVOICE', 'INV ', 'AUDIT', 'LEGAL FEES', 'ADVISORY', 'SERVICES']):
        return "Vendor"
        
    # Related Party: movement with a related party not funding an investment
    if cp_table == 'related_parties':
        return "Related Party"
        
    # Investment: buying/selling a position or funding one directly
    if cp_table == 'deals_positions' or any(k in upper for k in ['SHARE PURCHASE', 'EQUITY', 'DIRECT LOAN', 'SUBSCRIPTION', 'ACQUISITION', 'POSITION']):
        return "Investment"
        
    if has_from_to:
        return "Investment Transfer"
        
    return "Review"

def main():
    table_data = build_table_indices()
    rows = kit.rows()
    own_entities = determine_own_entities(rows, table_data)
    
    output_rows = []
    
    for row in rows:
        r = dict(row)
        narrative = r.get('narrative', '')
        acc = r.get('account_number')
        own_set = own_entities.get(acc, set())
        
        # 1. Project Code Extraction & Matching
        prj_raw = extract_project_code(narrative, table_data)
        if prj_raw:
            p_table, p_match = lookup_project_code(prj_raw, table_data)
            if p_table and p_match:
                prj_match = {
                    "status": "MATCH",
                    "matched_name": p_match,
                    "table": p_table
                }
            else:
                prj_match = {
                    "status": "UNRESOLVED",
                    "matched_name": None,
                    "table": None
                }
        else:
            prj_match = {
                "status": "CANNOT_VERIFY",
                "matched_name": None,
                "table": None
            }
            
        # 2. Counterparty Extraction
        p_from, p_to = find_parties_in_narrative(narrative)
        cp_raw = None
        
        if p_from and p_to:
            norm_from = normalize_alphanumeric(unwrap_commas(p_from))
            norm_to = normalize_alphanumeric(unwrap_commas(p_to))
            
            # The statement's own entity is the one that recurs; counterparty is the other
            if norm_from in own_set and norm_to not in own_set:
                cp_raw = p_to
            elif norm_to in own_set and norm_from not in own_set:
                cp_raw = p_from
            elif norm_from in own_set and norm_to in own_set:
                # Internal transfer between own entities/accounts
                cp_raw = None
            else:
                # Default to beneficiary (to)
                cp_raw = p_to
        else:
            single = find_single_party(narrative)
            if single:
                norm_single = normalize_alphanumeric(unwrap_commas(single))
                if norm_single not in own_set:
                    cp_raw = single
            else:
                # Check direct mention of vendors or investors in narrative
                for t_name in ['vendors', 'investors', 'related_parties']:
                    for col, val in table_data[t_name]['entries']:
                        pat = r'\b' + re.escape(val) + r'\b'
                        m = re.search(pat, narrative, re.IGNORECASE)
                        if m:
                            norm_val = normalize_alphanumeric(val)
                            if norm_val not in own_set:
                                cp_raw = narrative[m.start():m.end()]
                                break
                    if cp_raw:
                        break

        # Slicing check for counterparty provenance
        if cp_raw:
            # Must appear verbatim in narrative
            if cp_raw not in narrative:
                # Try finding exact position
                idx = narrative.upper().find(cp_raw.upper())
                if idx != -1:
                    cp_raw = narrative[idx:idx + len(cp_raw)]
                else:
                    cp_raw = None
                    
        # 3. Counterparty Matching
        if cp_raw:
            c_table, c_match = lookup_entity(cp_raw, table_data)
            if c_table and c_match:
                cp_match = {
                    "status": "MATCH",
                    "matched_name": c_match,
                    "table": c_table
                }
            else:
                cp_match = {
                    "status": "UNRESOLVED",
                    "matched_name": None,
                    "table": None
                }
        else:
            cp_match = {
                "status": "CANNOT_VERIFY",
                "matched_name": None,
                "table": None
            }
            
        # 4. Classification
        classification = classify_row(
            narrative, 
            cp_raw, 
            cp_match.get('table'), 
            cp_match.get('matched_name'), 
            prj_raw, 
            prj_match.get('table')
        )
        
        r['counterparty_raw'] = cp_raw
        r['counterparty_match'] = cp_match
        r['project_code_raw'] = prj_raw
        r['project_code_match'] = prj_match
        r['classification'] = classification
        
        output_rows.append(r)
        
    kit.write_result(output_rows)
    print(f"parsed {len(output_rows)} rows")

if __name__ == '__main__':
    main()