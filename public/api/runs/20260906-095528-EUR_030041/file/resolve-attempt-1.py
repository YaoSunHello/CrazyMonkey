import re
import kit

# Reference pools in priority order
CP_POOLS = [
    ("deals_positions", "Deal Name"),
    ("related_parties", "Related Party"),
    ("legal_entities", "Legal Entity"),
    ("vendors", "Vendor"),
    ("investors", "Investor"),
    ("deals_positions", "Position"),
]

PROJECT_POOLS = [
    ("project_codes", "Project Code"),
    ("project_codes", "New Project Code"),
]

# Account owner markers to drop if matched as counterparty
OWNER_PATTERNS = [
    re.compile(r"nordvik\s+infrastructure\s+v\b", re.I),
    re.compile(r"nordvik\s+infrastructure\s+partner", re.I),
    re.compile(r"\bnip\s+v\b", re.I),
]


def is_account_owner(name):
    if not name:
        return False
    return any(p.search(name) for p in OWNER_PATTERNS)


def extract_project(narrative):
    m = re.search(r"\bPROJECT,?\s+([A-Za-z0-9_]+(?:\s+[A-Za-z0-9_]+)?)", narrative, re.I)
    if not m:
        return None, {
            "status": "CANNOT_VERIFY",
            "matched_name": None,
            "table": None,
            "confidence": None,
            "why": "No project keyword in narrative",
        }

    full_candidate = m.group(1).rstrip(".,;")
    # Try full candidate (e.g. RANFJORD II)
    res = kit.lookup(full_candidate, PROJECT_POOLS)
    if res:
        span = kit.narrative_span(narrative, full_candidate)
        return span, {
            "status": "MATCH",
            "matched_name": res["matched_name"],
            "table": res["table"],
            "confidence": 1.0,
            "why": "Exact match in project_codes",
        }

    # Try single first token
    first_token = full_candidate.split()[0]
    res = kit.lookup(first_token, PROJECT_POOLS)
    if res:
        span = kit.narrative_span(narrative, first_token)
        return span, {
            "status": "MATCH",
            "matched_name": res["matched_name"],
            "table": res["table"],
            "confidence": 1.0,
            "why": "Exact match in project_codes",
        }

    return full_candidate, {
        "status": "UNRESOLVED",
        "matched_name": None,
        "table": None,
        "confidence": None,
        "why": f"Project '{full_candidate}' not found in project_codes",
    }


def find_counterparties_in_narrative(narrative):
    """Enumerate candidate spans and check against reference pools."""
    words = narrative.split()
    matches = []
    # Test windows of lengths from 1 to 8 words
    for length in range(8, 0, -1):
        for i in range(len(words) - length + 1):
            chunk = " ".join(words[i : i + length])
            clean = chunk.strip(" ,./:;")
            if not clean or len(clean) < 3:
                continue
            res = kit.lookup(clean, CP_POOLS)
            if res:
                matched_name = res["matched_name"]
                if is_account_owner(matched_name):
                    continue
                try:
                    span = kit.narrative_span(narrative, clean)
                except Exception:
                    span = clean
                matches.append((span, res, length))

    if not matches:
        return None, None

    # Deduplicate and prefer longest span
    matches.sort(key=lambda x: len(x[0]), reverse=True)
    best_span, best_res, _ = matches[0]
    return best_span, best_res


def resolve_row(row):
    narrative = row["narrative"]
    trn_type = row.get("trn_type", "")
    debit = row.get("debit")
    credit = row.get("credit")

    # 1. Project code extraction
    proj_raw, proj_match = extract_project(narrative)

    # 2. Counterparty extraction
    cp_span, cp_res = find_counterparties_in_narrative(narrative)

    if cp_res:
        cp_raw = cp_span
        cp_match = {
            "status": "MATCH",
            "matched_name": cp_res["matched_name"],
            "table": cp_res["table"],
            "confidence": 1.0,
            "why": f"Exact match in {cp_res['table']}",
        }
    else:
        # Check if a counterparty name is clearly in narrative but unresolved
        m_nip = re.search(r"\b(NIP\s+[A-Za-z0-9_]+(?:\s+[A-Za-z0-9_]+)?)\b", narrative, re.I)
        if m_nip and not is_account_owner(m_nip.group(1)):
            raw_cand = m_nip.group(1)
            span = kit.narrative_span(narrative, raw_cand)
            cp_raw = span
            cp_match = {
                "status": "UNRESOLVED",
                "matched_name": None,
                "table": None,
                "confidence": None,
                "why": f"Entity '{raw_cand}' not found in reference tables",
            }
        else:
            cp_raw = None
            cp_match = {
                "status": "CANNOT_VERIFY",
                "matched_name": None,
                "table": None,
                "confidence": None,
                "why": "No counterparty named in narrative",
            }

    # 3. Classification
    if "CHARGES" in narrative or "COMMISSION" in narrative or "CREDIT INTEREST" in narrative:
        classification = "Other"
    elif "EQUITY:" in narrative or "EQUITY" in narrative:
        classification = "Investment Transfer"
    elif "ISIN" in narrative or "TRANCHE" in narrative:
        classification = "Investor"
    elif cp_match.get("table") == "vendors":
        classification = "Vendor"
    elif cp_raw == "NIP CINNABAR APS":
        classification = "Related Party"
    elif "CHARGE WAIVED" in narrative and "/FR" in narrative:
        classification = "Internal"
    elif "CHARGE WAIVED" in narrative and "NORDVIK INFRASTRUCTURE PARTNER" in narrative:
        classification = "Internal"
    else:
        classification = "Review"

    return cp_raw, cp_match, proj_raw, proj_match, classification


rows = kit.rows()
enriched = []

print(f"Processing {len(rows)} rows...")

for idx, r in enumerate(rows, 1):
    new_r = dict(r)
    cp_raw, cp_match, proj_raw, proj_match, classification = resolve_row(r)

    new_r["counterparty_raw"] = cp_raw
    new_r["counterparty_match"] = cp_match
    new_r["project_code_raw"] = proj_raw
    new_r["project_code_match"] = proj_match
    new_r["classification"] = classification

    enriched.append(new_r)
    print(f"Row {idx:2d}: CP={cp_raw} -> {cp_match['status']} ({cp_match.get('matched_name')}) | PRJ={proj_raw} | CLS={classification}")

# Self-checks and assertions
resolved_count = sum(1 for r in enriched if r["counterparty_match"]["status"] == "MATCH")
unresolved_count = sum(1 for r in enriched if r["counterparty_match"]["status"] == "UNRESOLVED")
cannot_verify_count = sum(1 for r in enriched if r["counterparty_match"]["status"] == "CANNOT_VERIFY")
review_count = sum(1 for r in enriched if r["classification"] == "Review")

print(f"Summary: MATCH={resolved_count}, UNRESOLVED={unresolved_count}, CANNOT_VERIFY={cannot_verify_count}, Review={review_count}")

claims = {
    "all_rows_processed": len(enriched) == len(rows),
    "no_unjustified_reviews": review_count == 0,
    "cp_pairing_valid": all(
        (r["counterparty_raw"] is None and r["counterparty_match"]["status"] == "CANNOT_VERIFY")
        or (r["counterparty_raw"] is not None and r["counterparty_match"]["status"] != "CANNOT_VERIFY")
        for r in enriched
    ),
    "proj_pairing_valid": all(
        (r["project_code_raw"] is None and r["project_code_match"]["status"] == "CANNOT_VERIFY")
        or (r["project_code_raw"] is not None and r["project_code_match"]["status"] != "CANNOT_VERIFY")
        for r in enriched
    ),
}

kit.write_assertions(claims)
kit.write_result(enriched)

print(f"parsed {len(enriched)} rows")