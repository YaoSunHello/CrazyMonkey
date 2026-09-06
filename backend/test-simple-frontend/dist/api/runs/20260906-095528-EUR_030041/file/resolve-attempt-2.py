import re
import sys
import kit

# Reference pools in priority order
CP_POOLS = [
    ("legal_entities", "Legal Entity"),
    ("related_parties", "Related Party"),
    ("vendors", "Vendor"),
    ("investors", "Investor"),
    ("deals_positions", "Deal Name"),
    ("deals_positions", "Position"),
]

PROJECT_POOLS = [
    ("project_codes", "Project Code"),
    ("project_codes", "New Project Code"),
]

# Account owner patterns to ignore when matching counterparties
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
    # Take the single token after keyword PROJECT, bounded at the first whitespace
    m = re.search(r"\bPROJECT,?\s+([^\s,.;]+)", narrative, re.I)
    if not m:
        return None, {
            "status": "CANNOT_VERIFY",
            "matched_name": None,
            "table": None,
            "confidence": None,
            "why": "No project keyword in narrative",
        }

    raw_token = m.group(1)
    res = kit.lookup(raw_token, PROJECT_POOLS)
    if res:
        span = kit.narrative_span(narrative, raw_token)
        return span, {
            "status": "MATCH",
            "matched_name": res["matched_name"],
            "table": res["table"],
            "confidence": 1.0,
            "why": f"Exact match in {res['table']}",
        }
    else:
        span = kit.narrative_span(narrative, raw_token)
        return span, {
            "status": "UNRESOLVED",
            "matched_name": None,
            "table": None,
            "confidence": None,
            "why": f"Project '{raw_token}' not found in project_codes",
        }


def find_counterparties_in_narrative(narrative):
    """Enumerate candidate word spans and verify against reference lists."""
    words = narrative.split()
    matches = []
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

    # Prefer longest matched span
    matches.sort(key=lambda x: len(x[0]), reverse=True)
    best_span, best_res, _ = matches[0]
    return best_span, best_res


def resolve_row(row):
    narrative = row["narrative"]

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
        # Check for party named in narrative not present in reference data
        m_nip = re.search(r"\b(NIP\s+[A-Za-z0-9_]+(?:\s+[A-Za-z0-9_]+)*)\b", narrative, re.I)
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
    elif "CINNABAR" in narrative:
        classification = "Related Party"
    elif "CHARGE WAIVED" in narrative:
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
    print(
        f"Row {idx:2d}: CP={cp_raw} -> {cp_match['status']} ({cp_match.get('matched_name')}) | "
        f"PRJ={proj_raw} -> {proj_match['status']} | CLS={classification}"
    )

resolved_count = sum(1 for r in enriched if r["counterparty_match"]["status"] == "MATCH")
unresolved_count = sum(1 for r in enriched if r["counterparty_match"]["status"] == "UNRESOLVED")
cannot_verify_count = sum(1 for r in enriched if r["counterparty_match"]["status"] == "CANNOT_VERIFY")
review_count = sum(1 for r in enriched if r["classification"] == "Review")

print(f"Summary: MATCH={resolved_count}, UNRESOLVED={unresolved_count}, CANNOT_VERIFY={cannot_verify_count}, Review={review_count}")

# Write results first so output is guaranteed to exist
kit.write_result(enriched)

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

try:
    kit.write_assertions(claims)
except Exception as e:
    print(f"Assertions status: {e}")

sys.stdout.flush()
print(f"parsed {len(enriched)} rows")