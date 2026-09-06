import re
from collections import defaultdict, Counter
import kit


def normalize_for_match(s):
    if not s:
        return ""
    # remove bank mid-word commas, e.g. "INFRASTR, UCTURE" -> "INFRASTRUCTURE"
    s = re.sub(r"([A-Za-z0-9]),\s*([A-Za-z0-9])", r"\1\2", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def build_indexes():
    search_order = [
        ("related_parties", ["Related Party"]),
        ("vendors", ["Vendor"]),
        ("investors", ["Investor"]),
        ("legal_entities", ["Legal Entity"]),
        ("deals_positions", ["Deal Name", "Position"]),
    ]

    table_data = []
    for table_name, columns in search_order:
        try:
            t = kit.table(table_name)
        except Exception:
            continue
        col_list = [c for c in columns if c in t.columns]
        for col in col_list:
            for val in t.values(col):
                if val:
                    val_str = str(val).strip()
                    if val_str:
                        table_data.append(
                            (
                                table_name,
                                col,
                                val_str,
                                normalize_for_match(val_str),
                            )
                        )

    # Project codes index
    known_projects = {}
    try:
        p_table = kit.table("project_codes")
        for col in ["Project Code", "New Project Code"]:
            if col in p_table.columns:
                for val in p_table.values(col):
                    if val:
                        v_str = str(val).strip()
                        if len(v_str) > 1:
                            known_projects[v_str.lower()] = v_str
    except Exception:
        pass

    return table_data, known_projects


def find_entity_match(candidate_raw, table_data):
    if not candidate_raw:
        return None
    c_norm = normalize_for_match(candidate_raw)
    c_nodot = c_norm.rstrip(".")

    for tbl_name, col, orig_val, v_norm in table_data:
        v_nodot = v_norm.rstrip(".")
        if c_norm == v_norm or (c_nodot and c_nodot == v_nodot):
            return {"status": "MATCH", "matched_name": orig_val, "table": tbl_name}
    return None


def get_narrative(row):
    for k in ("narrative", "description", "details", "narrative_raw", "text"):
        if k in row and row[k]:
            return str(row[k])
    return ""


def clean_party_tail(text):
    tail_patterns = [
        r"\s+-\s+PROJECT\b",
        r"\s+PROJECT\b",
        r"\s+PRJ\b",
        r"\s+-\s+REF\b",
        r"\s+REF:?",
        r"\s+/REF/",
        r"\s+-\s+INV\b",
        r"\s+INV\b",
        r"\s+INVOICE\b",
        r"\s+//",
        r"\s+;\s*",
        r"\s+-\s+ACCRUED\b",
        r"\s+-\s+INTEREST\b",
        r"\s+-\s+FEES?\b",
        r"\s+-\s+DRAWDOWN\b",
        r"\s+-\s+LOAN\b",
        r"\s+-\s+TRANSFER\b",
    ]
    trimmed = text
    for p in tail_patterns:
        m = re.search(p, trimmed, re.IGNORECASE)
        if m:
            trimmed = trimmed[: m.start()]
    return trimmed.strip()


def resolve_rows():
    rows = kit.rows()
    table_data, known_projects = build_indexes()

    # Group by account_number to find each account's statement entity
    acc_rows = defaultdict(list)
    for i, row in enumerate(rows):
        acc = row.get("account_number", "default")
        acc_rows[acc].append((i, row))

    # Identify recurring platform entity for each account
    account_own_entities = {}
    for acc, items in acc_rows.items():
        entity_counts = Counter()
        for idx, r in items:
            narr = get_narrative(r)
            m_from_to = re.search(
                r"\bFROM\b\s+([A-Za-z0-9,\.\s\&\-\/]+?)\s+\bTO\b\s+([A-Za-z0-9,\.\s\&\-\/]+)",
                narr,
                re.IGNORECASE,
            )
            if m_from_to:
                side_a = clean_party_tail(m_from_to.group(1))
                side_b = clean_party_tail(m_from_to.group(2))
                if side_a:
                    entity_counts[normalize_for_match(side_a)] += 1
                if side_b:
                    entity_counts[normalize_for_match(side_b)] += 1
            else:
                for tbl_name, col, orig_val, v_norm in table_data:
                    if tbl_name in ("legal_entities", "related_parties"):
                        if re.search(
                            r"\b" + re.escape(orig_val) + r"\b",
                            narr,
                            re.IGNORECASE,
                        ):
                            entity_counts[v_norm] += 1

        if entity_counts:
            most_common = entity_counts.most_common(1)[0]
            if most_common[1] >= 2 or len(items) == 1:
                account_own_entities[acc] = most_common[0]
            else:
                account_own_entities[acc] = most_common[0]
        else:
            account_own_entities[acc] = None

    for i, row in enumerate(rows):
        narr = get_narrative(row)
        acc = row.get("account_number", "default")
        own_entity_norm = account_own_entities.get(acc)

        # 1. Project code extraction
        project_code_raw = None
        m_proj = re.search(
            r"\b(?:PROJECT|PRJ)(?:\s+CODE)?[\s:\-]+([A-Za-z0-9_\-]+)\b",
            narr,
            re.IGNORECASE,
        )
        if m_proj:
            start_p, end_p = m_proj.span(1)
            project_code_raw = narr[start_p:end_p]
        else:
            for p_norm, orig_p in known_projects.items():
                m_known = re.search(
                    r"\b" + re.escape(orig_p) + r"\b", narr, re.IGNORECASE
                )
                if m_known:
                    project_code_raw = narr[m_known.start() : m_known.end()]
                    break

        if project_code_raw:
            p_norm = project_code_raw.strip().lower()
            if p_norm in known_projects:
                project_code_match = {
                    "status": "MATCH",
                    "matched_name": known_projects[p_norm],
                    "table": "project_codes",
                }
            else:
                project_code_match = {
                    "status": "UNRESOLVED",
                    "matched_name": None,
                    "table": None,
                }
        else:
            project_code_match = {
                "status": "CANNOT_VERIFY",
                "matched_name": None,
                "table": None,
            }

        # 2. Counterparty extraction
        counterparty_raw = None

        is_routine_charge = bool(
            re.search(
                r"\b(?:BANK CHARGES?|ACCOUNT (?:FEE|MAINTENANCE)|INTEREST (?:PAID|RECEIVED|CAPITALISED)|COMMISSION|MONTHLY FEE|SERVICE CHARGE|WIRE FEE)\b",
                narr,
                re.IGNORECASE,
            )
        )

        m_from_to = re.search(
            r"\bFROM\b\s+([A-Za-z0-9,\.\s\&\-\/]+?)\s+\bTO\b\s+([A-Za-z0-9,\.\s\&\-\/]+)",
            narr,
            re.IGNORECASE,
        )
        m_to_from = (
            re.search(
                r"\bTO\b\s+([A-Za-z0-9,\.\s\&\-\/]+?)\s+\bFROM\b\s+([A-Za-z0-9,\.\s\&\-\/]+)",
                narr,
                re.IGNORECASE,
            )
            if not m_from_to
            else None
        )

        if m_from_to:
            raw_a = m_from_to.group(1).strip()
            raw_b_full = m_from_to.group(2)
            raw_b = clean_party_tail(raw_b_full)

            norm_a = normalize_for_match(raw_a)
            norm_b = normalize_for_match(raw_b)

            if own_entity_norm and norm_a == own_entity_norm:
                picked = raw_b
                search_start = m_from_to.start(2)
            elif own_entity_norm and norm_b == own_entity_norm:
                picked = raw_a
                search_start = m_from_to.start(1)
            else:
                # Default to beneficiary side (B)
                picked = raw_b
                search_start = m_from_to.start(2)

            pos = narr.find(picked, search_start)
            if pos != -1:
                counterparty_raw = narr[pos : pos + len(picked)]
            else:
                counterparty_raw = picked

        elif m_to_from:
            raw_to = clean_party_tail(m_to_from.group(1))
            raw_from = clean_party_tail(m_to_from.group(2))
            norm_to = normalize_for_match(raw_to)
            norm_from = normalize_for_match(raw_from)

            if own_entity_norm and norm_from == own_entity_norm:
                picked = raw_to
                search_start = m_to_from.start(1)
            else:
                picked = raw_to
                search_start = m_to_from.start(1)

            pos = narr.find(picked, search_start)
            if pos != -1:
                counterparty_raw = narr[pos : pos + len(picked)]
            else:
                counterparty_raw = picked

        elif not is_routine_charge:
            m_bnf = re.search(
                r"\b(?:BENEFICIARY:?|/BNF/|B/O:?|ORDERING(?:\s+CUSTOMER)?:?|/ORDP/)\s*([A-Za-z0-9,\.\s\&\-\/]+)",
                narr,
                re.IGNORECASE,
            )
            if m_bnf:
                cand = clean_party_tail(m_bnf.group(1))
                pos = narr.find(cand, m_bnf.start(1))
                if pos != -1:
                    counterparty_raw = narr[pos : pos + len(cand)]
                else:
                    counterparty_raw = cand
            else:
                m_single_to = re.search(
                    r"\b(?:TO|PAYMENT TO|TRANSFER TO)\s+([A-Za-z0-9,\.\s\&\-\/]+)",
                    narr,
                    re.IGNORECASE,
                )
                if m_single_to:
                    cand = clean_party_tail(m_single_to.group(1))
                    norm_c = normalize_for_match(cand)
                    if not own_entity_norm or norm_c != own_entity_norm:
                        pos = narr.find(cand, m_single_to.start(1))
                        if pos != -1:
                            counterparty_raw = narr[pos : pos + len(cand)]
                        else:
                            counterparty_raw = cand

            if not counterparty_raw:
                # Search known entities in narrative
                for tbl_name, col, orig_val, v_norm in table_data:
                    if own_entity_norm and v_norm == own_entity_norm:
                        continue
                    m_ent = re.search(
                        r"\b" + re.escape(orig_val) + r"\b",
                        narr,
                        re.IGNORECASE,
                    )
                    if m_ent:
                        counterparty_raw = narr[m_ent.start() : m_ent.end()]
                        break

        # Strip any trailing punctuation from counterparty_raw if provenance allows
        if counterparty_raw:
            counterparty_raw = counterparty_raw.strip(" -;,/")
            pos = narr.find(counterparty_raw)
            if pos != -1:
                counterparty_raw = narr[pos : pos + len(counterparty_raw)]
            else:
                counterparty_raw = None

        # Counterparty matching
        if counterparty_raw:
            hit = find_entity_match(counterparty_raw, table_data)
            if hit:
                counterparty_match = hit
            else:
                counterparty_match = {
                    "status": "UNRESOLVED",
                    "matched_name": None,
                    "table": None,
                }
        else:
            counterparty_match = {
                "status": "CANNOT_VERIFY",
                "matched_name": None,
                "table": None,
            }

        # 3. Classification
        narr_upper = narr.upper()

        if is_routine_charge or any(
            w in narr_upper
            for w in [
                "BANK CHARGE",
                "ACCOUNT FEE",
                "INTEREST PAID",
                "INTEREST RECEIVED",
                "INTEREST CAPITALISED",
                "MONTHLY FEE",
                "COMMISSION",
                "SERVICE CHARGE",
                "WIRE FEE",
                "MAINTENANCE FEE",
            ]
        ):
            classification = "Other"

        elif (
            counterparty_match["status"] == "MATCH"
            and counterparty_match["table"] == "investors"
        ) or any(
            w in narr_upper
            for w in ["CAPITAL CALL", "DISTRIBUTION", "SUBSCRIPTION", "REDEMPTION"]
        ):
            classification = "Investor"

        elif any(
            w in narr_upper
            for w in [
                "MANAGEMENT FEE",
                "DIRECTOR FEE",
                "REBATE",
                "REIMBURSEMENT",
                "SETTLING OF BALANCES",
                "SETTLEMENT",
            ]
        ):
            classification = "Related Party"

        elif (
            project_code_raw is not None
            and counterparty_match["status"] == "MATCH"
            and counterparty_match["table"] in ("related_parties", "legal_entities")
        ):
            classification = "Investment Transfer"

        elif (
            any(
                w in narr_upper
                for w in [
                    "LOAN",
                    "EQUITY",
                    "SHARES",
                    "DRAWDOWN",
                    "PRINCIPAL",
                    "PURCHASE",
                    "INVESTMENT",
                ]
            )
            or (
                counterparty_match["status"] == "MATCH"
                and counterparty_match["table"] == "deals_positions"
            )
            or (
                project_code_raw is not None
                and counterparty_match["status"] == "UNRESOLVED"
            )
        ):
            classification = "Investment"

        elif (
            counterparty_match["status"] == "MATCH"
            and counterparty_match["table"] == "vendors"
        ) or any(
            w in narr_upper
            for w in [
                "INVOICE",
                "AUDIT",
                "LEGAL FEE",
                "CONSULTING",
                "ADVISORY",
                "SUPPLIER",
            ]
        ):
            classification = "Vendor"

        elif any(
            w in narr_upper
            for w in [
                "INTERNAL TRANSFER",
                "SWEEP",
                "TRANSFER BETWEEN ACCOUNTS",
                "ZERO BALANCE",
            ]
        ):
            classification = "Internal"

        else:
            classification = "Review"

        row["counterparty_raw"] = counterparty_raw
        row["counterparty_match"] = counterparty_match
        row["project_code_raw"] = project_code_raw
        row["project_code_match"] = project_code_match
        row["classification"] = classification

    kit.write_result(rows)
    print(f"parsed {len(rows)} rows")


if __name__ == "__main__":
    resolve_rows()