import re
import kit


def get_narrative(row):
    for k in ["narrative", "description", "narrative_raw", "details"]:
        if k in row and row[k]:
            return str(row[k])
    for k, v in row.items():
        if isinstance(v, str) and len(v) > 10 and k != "account_number":
            return v
    return ""


def normalize(s):
    if not s:
        return ""
    # Unwrap mid-word commas (e.g. INFRASTR, UCTURE -> INFRASTRUCTURE)
    s = re.sub(r"(?<=[A-Za-z]),\s*(?=[A-Za-z])", "", s)
    s = re.sub(r"[^A-Za-z0-9\s]", " ", s)
    return " ".join(s.lower().split())


def clean_candidates(raw):
    if not raw:
        return []
    cands = []
    c1 = raw.strip(" -:;,/")
    if c1:
        cands.append(c1)
    # Mid-word comma unwrapping
    c2 = re.sub(r"(?<=[A-Za-z]),\s*(?=[A-Za-z])", "", c1).strip()
    if c2 and c2 not in cands:
        cands.append(c2)
    # Comma removed
    c3 = c1.replace(",", "").strip()
    if c3 and c3 not in cands:
        cands.append(c3)
    # Normalized whitespace
    c4 = " ".join(c1.split())
    if c4 and c4 not in cands:
        cands.append(c4)
    c5 = " ".join(c2.split())
    if c5 and c5 not in cands:
        cands.append(c5)
    return cands


def find_account_owners(rows):
    account_owners = {}
    accounts = set(r.get("account_number") for r in rows if r.get("account_number"))

    # Gather entity names from platform master lists
    candidate_entities = []
    for tbl_name in ["legal_entities", "related_parties"]:
        if tbl_name in kit.tables():
            t = kit.table(tbl_name)
            for col in t.columns:
                for v in t.values(col):
                    if v and len(v.strip()) > 3:
                        candidate_entities.append(v.strip())

    for acc in accounts:
        acc_rows = [r for r in rows if r.get("account_number") == acc]
        entity_counts = {}

        # Also extract candidate parties from FROM/TO in this account's narratives
        for r in acc_rows:
            nar = get_narrative(r)
            m = re.search(
                r"\bFROM\s+([A-Za-z0-9,.\s&\'\-_/]+?)\s+TO\s+([A-Za-z0-9,.\s&\'\-_/]+)",
                nar,
                re.IGNORECASE,
            )
            if m:
                for grp in [m.group(1), m.group(2)]:
                    cleaned = grp.strip(" -:;,/")
                    if len(cleaned) > 3 and cleaned not in candidate_entities:
                        candidate_entities.append(cleaned)

        for ent in candidate_entities:
            ent_norm = normalize(ent)
            if not ent_norm:
                continue
            count = 0
            for r in acc_rows:
                nar_norm = normalize(get_narrative(r))
                if ent_norm in nar_norm:
                    count += 1
            if count > 0:
                entity_counts[ent] = count

        if entity_counts:
            best_ent = max(entity_counts, key=entity_counts.get)
            if entity_counts[best_ent] >= max(2, int(len(acc_rows) * 0.3)):
                account_owners[acc] = best_ent

    return account_owners


STOP_PATTERN = (
    r"(?:\bPROJECT\b|\bPROJ\b|\bPRJ\b|\bREF\b|\bREFERENCE\b|\bINV\b|\bINVOICE\b|"
    r"\bVAL(?:UE)?\b|\bDATE\b|\bPERIOD\b|\bIBAN\b|\bACC(?:OUNT)?\b|;|\n|\|)"
)


def extract_counterparty_raw(narrative, acc_owner):
    if not narrative:
        return None

    # Pattern 1: FROM <A> TO <B>
    m1 = re.search(
        r"\bFROM\s+([A-Za-z0-9,.\s&\'\-_/]+?)\s+TO\s+([A-Za-z0-9,.\s&\'\-_/]+?)(?="
        + STOP_PATTERN
        + r"|$)",
        narrative,
        re.IGNORECASE,
    )
    if m1:
        start_a, end_a = m1.span(1)
        raw_a = narrative[start_a:end_a].strip(" -:;,/")
        start_b, end_b = m1.span(2)
        raw_b = narrative[start_b:end_b].strip(" -:;,/")

        owner_norm = normalize(acc_owner) if acc_owner else ""
        norm_a = normalize(raw_a)
        norm_b = normalize(raw_b)

        if owner_norm and (norm_a == owner_norm or norm_a in owner_norm or owner_norm in norm_a):
            return raw_b if raw_b else None
        elif owner_norm and (norm_b == owner_norm or norm_b in owner_norm or owner_norm in norm_b):
            return raw_a if raw_a else None
        else:
            return raw_b if raw_b else None

    # Pattern 2: TO <B> FROM <A>
    m2 = re.search(
        r"\bTO\s+([A-Za-z0-9,.\s&\'\-_/]+?)\s+FROM\s+([A-Za-z0-9,.\s&\'\-_/]+?)(?="
        + STOP_PATTERN
        + r"|$)",
        narrative,
        re.IGNORECASE,
    )
    if m2:
        start_b, end_b = m2.span(1)
        raw_b = narrative[start_b:end_b].strip(" -:;,/")
        start_a, end_a = m2.span(2)
        raw_a = narrative[start_a:end_a].strip(" -:;,/")

        owner_norm = normalize(acc_owner) if acc_owner else ""
        norm_a = normalize(raw_a)
        norm_b = normalize(raw_b)

        if owner_norm and (norm_b == owner_norm or norm_b in owner_norm or owner_norm in norm_b):
            return raw_a if raw_a else None
        elif owner_norm and (norm_a == owner_norm or norm_a in owner_norm or owner_norm in norm_a):
            return raw_b if raw_b else None
        else:
            return raw_b if raw_b else None

    # Pattern 3: Beneficiary
    m3 = re.search(
        r"(?:BENEFICIARY|/BEN/|B/O)\s*[:]?\s*([A-Za-z0-9,.\s&\'\-_/]+?)(?="
        + STOP_PATTERN
        + r"|$)",
        narrative,
        re.IGNORECASE,
    )
    if m3:
        start, end = m3.span(1)
        raw = narrative[start:end].strip(" -:;,/")
        if normalize(raw) != normalize(acc_owner):
            return raw if raw else None

    # Pattern 4: Ordering Customer
    m4 = re.search(
        r"(?:ORDERING(?:\s+CUSTOMER)?|/ORDP?/|ORD)\s*[:]?\s*([A-Za-z0-9,.\s&\'\-_/]+?)(?="
        + STOP_PATTERN
        + r"|$)",
        narrative,
        re.IGNORECASE,
    )
    if m4:
        start, end = m4.span(1)
        raw = narrative[start:end].strip(" -:;,/")
        if normalize(raw) != normalize(acc_owner):
            return raw if raw else None

    # Pattern 5: Single TO
    m5 = re.search(
        r"\bTO\s+([A-Za-z0-9,.\s&\'\-_/]+?)(?=" + STOP_PATTERN + r"|$)",
        narrative,
        re.IGNORECASE,
    )
    if m5:
        start, end = m5.span(1)
        raw = narrative[start:end].strip(" -:;,/")
        if normalize(raw) != normalize(acc_owner) and len(raw) > 2:
            return raw

    # Pattern 6: Single FROM
    m6 = re.search(
        r"\bFROM\s+([A-Za-z0-9,.\s&\'\-_/]+?)(?=" + STOP_PATTERN + r"|$)",
        narrative,
        re.IGNORECASE,
    )
    if m6:
        start, end = m6.span(1)
        raw = narrative[start:end].strip(" -:;,/")
        if normalize(raw) != normalize(acc_owner) and len(raw) > 2:
            return raw

    # Check for known reference entities appearing in narrative
    order = ["related_parties", "vendors", "investors", "legal_entities", "deals_positions"]
    for tbl_name in order:
        if tbl_name not in kit.tables():
            continue
        t = kit.table(tbl_name)
        for col in t.columns:
            for val in t.values(col):
                if not val or len(val.strip()) < 4:
                    continue
                v_clean = val.strip()
                if acc_owner and normalize(v_clean) == normalize(acc_owner):
                    continue
                idx = narrative.upper().find(v_clean.upper())
                if idx != -1:
                    raw_sub = narrative[idx : idx + len(v_clean)]
                    return raw_sub

    return None


def match_counterparty(cp_raw):
    if not cp_raw:
        return {"status": "CANNOT_VERIFY", "matched_name": None, "table": None}

    order = ["related_parties", "vendors", "investors", "legal_entities", "deals_positions"]
    cands = clean_candidates(cp_raw)

    for tbl_name in order:
        if tbl_name not in kit.tables():
            continue
        t = kit.table(tbl_name)
        for cand in cands:
            for col in t.columns:
                if t.contains(col, cand):
                    row = t.find(col, cand)
                    if row is not None and col in row:
                        return {
                            "status": "MATCH",
                            "matched_name": row[col],
                            "table": tbl_name,
                        }
                    for val in t.values(col):
                        if val and val.strip().lower() == cand.strip().lower():
                            return {
                                "status": "MATCH",
                                "matched_name": val,
                                "table": tbl_name,
                            }
        # Fallback exact normalized match
        for cand in cands:
            cand_norm = normalize(cand)
            for col in t.columns:
                for val in t.values(col):
                    if val and normalize(val) == cand_norm:
                        return {
                            "status": "MATCH",
                            "matched_name": val,
                            "table": tbl_name,
                        }

    return {"status": "UNRESOLVED", "matched_name": None, "table": None}


def extract_project_code_raw(narrative):
    if not narrative:
        return None

    # Check for PROJECT keyword
    m = re.search(r"\bPROJECT\b\s*[:#-]?\s*([A-Za-z0-9_-]+)", narrative, re.IGNORECASE)
    if m:
        start, end = m.span(1)
        return narrative[start:end]

    m_alt = re.search(r"\b(?:PROJ|PRJ)\b\s*[:#-]?\s*([A-Za-z0-9_-]+)", narrative, re.IGNORECASE)
    if m_alt:
        start, end = m_alt.span(1)
        return narrative[start:end]

    # Check against known project codes
    if "project_codes" in kit.tables():
        t = kit.table("project_codes")
        for col in t.columns:
            for val in t.values(col):
                if val and len(val.strip()) > 2:
                    p = re.compile(r"\b" + re.escape(val.strip()) + r"\b", re.IGNORECASE)
                    m_val = p.search(narrative)
                    if m_val:
                        start, end = m_val.span()
                        return narrative[start:end]

    return None


def match_project_code(proj_raw):
    if not proj_raw:
        return {"status": "CANNOT_VERIFY", "matched_name": None, "table": None}

    if "project_codes" not in kit.tables():
        return {"status": "UNRESOLVED", "matched_name": None, "table": None}

    t = kit.table("project_codes")
    cands = clean_candidates(proj_raw)

    for cand in cands:
        for col in t.columns:
            if t.contains(col, cand):
                row = t.find(col, cand)
                if row is not None and col in row:
                    return {
                        "status": "MATCH",
                        "matched_name": row[col],
                        "table": "project_codes",
                    }
                for val in t.values(col):
                    if val and val.strip().lower() == cand.strip().lower():
                        return {
                            "status": "MATCH",
                            "matched_name": val,
                            "table": "project_codes",
                        }

    for cand in cands:
        cand_norm = normalize(cand)
        for col in t.columns:
            for val in t.values(col):
                if val and normalize(val) == cand_norm:
                    return {
                        "status": "MATCH",
                        "matched_name": val,
                        "table": "project_codes",
                    }

    return {"status": "UNRESOLVED", "matched_name": None, "table": None}


def classify_row(row, narrative, cp_raw, cp_match, proj_raw, proj_match):
    nar_upper = narrative.upper()
    cp_table = cp_match.get("table")
    has_project = proj_raw is not None
    has_from_to = "FROM" in nar_upper and "TO" in nar_upper

    # Routine bank charges, interest, fees with no counterparty
    if cp_raw is None:
        if any(
            w in nar_upper
            for w in [
                "BANK CHARGE",
                "SERVICE CHARGE",
                "ACCOUNT FEE",
                "MAINTENANCE FEE",
                "COMMISSION",
                "CREDIT INTEREST",
                "DEBIT INTEREST",
                "INTEREST PAID",
                "CHRG",
                "INTEREST",
                "FEE",
            ]
        ):
            return "Other"
        if any(w in nar_upper for w in ["SWEEP", "INTERNAL TRANSFER", "TRANSFER BETWEEN"]):
            return "Internal"

    # Investor activity
    if cp_table == "investors" or any(
        w in nar_upper
        for w in [
            "CAPITAL CALL",
            "DISTRIBUTION",
            "DIVIDEND TO INVESTOR",
            "INVESTOR DRAWDOWN",
            "REDEMPTION",
        ]
    ):
        return "Investor"

    # Vendor activity
    if cp_table == "vendors" or any(
        w in nar_upper
        for w in [
            "AUDIT",
            "LEGAL FEES",
            "ADVISORY",
            "CONSULTING",
            "TAX SERVICES",
            "INVOICE",
            "SUPPLIER",
            "SERVICES",
        ]
    ):
        return "Vendor"

    # Explicit Investment Transfer
    if "INVESTMENT TRANSFER" in nar_upper:
        return "Investment Transfer"

    # Deal positions
    if cp_table == "deals_positions":
        return "Investment"

    # Direct investment SPVs/HoldCos
    if cp_raw and any(
        w in cp_raw.upper() for w in ["HOLDCO", "TOPCO", "MIDCO", "FINCO", "PORTFOLIO", "ASSETCO"]
    ):
        return "Investment"

    # Movements between platform entities funding an investment
    is_platform_entity = cp_table in ["related_parties", "legal_entities"]
    if is_platform_entity and has_project and has_from_to:
        return "Investment Transfer"

    # Direct investment loans or equity
    if any(
        w in nar_upper
        for w in [
            "LOAN",
            "EQUITY",
            "SHARES",
            "DRAWDOWN",
            "PRINCIPAL",
            "INVESTMENT",
            "SUBSCRIPTION",
            "PROMISSORY",
        ]
    ):
        return "Investment"

    # Related Party movements
    if cp_table in ["related_parties", "legal_entities"]:
        if any(
            w in nar_upper
            for w in [
                "FEE",
                "REBATE",
                "RECHARGE",
                "SETTLEMENT",
                "BALANCE",
                "EXPENSE",
                "MANAGEMENT FEE",
            ]
        ):
            return "Related Party"
        if not has_project:
            if any(w in nar_upper for w in ["TRANSFER", "INTERNAL", "LIQUIDITY", "TREASURY"]):
                return "Internal"
            return "Related Party"

    # Internal platform transfers
    if any(w in nar_upper for w in ["INTERNAL", "SWEEP", "TRANSFER TO ACC", "TRANSFER FROM ACC"]):
        return "Internal"

    if any(w in nar_upper for w in ["CHARGE", "FEE", "INTEREST"]):
        return "Other"

    return "Review"


def main():
    rows = kit.rows()
    account_owners = find_account_owners(rows)
    results = []

    for row in rows:
        nar = get_narrative(row)
        acc = row.get("account_number")
        owner = account_owners.get(acc)

        cp_raw = extract_counterparty_raw(nar, owner)
        if cp_raw and cp_raw not in nar:
            idx = nar.upper().find(cp_raw.upper())
            if idx != -1:
                cp_raw = nar[idx : idx + len(cp_raw)]
            else:
                cp_raw = None

        cp_match = match_counterparty(cp_raw)

        proj_raw = extract_project_code_raw(nar)
        if proj_raw and proj_raw not in nar:
            idx = nar.upper().find(proj_raw.upper())
            if idx != -1:
                proj_raw = nar[idx : idx + len(proj_raw)]
            else:
                proj_raw = None

        proj_match = match_project_code(proj_raw)

        classification = classify_row(row, nar, cp_raw, cp_match, proj_raw, proj_match)

        out_row = dict(row)
        out_row["counterparty_raw"] = cp_raw
        out_row["counterparty_match"] = cp_match
        out_row["project_code_raw"] = proj_raw
        out_row["project_code_match"] = proj_match
        out_row["classification"] = classification

        results.append(out_row)

    kit.write_result(results)
    print(f"parsed {len(results)} rows")


if __name__ == "__main__":
    main()