import re
import sys
import traceback
import kit

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

VALID_CP_TABLES = {
    "legal_entities",
    "related_parties",
    "vendors",
    "investors",
    "deals_positions",
}

VALID_PROJECT_TABLES = {
    "project_codes",
}


def extract_match(res, default_table=None):
    """Normalize return value from kit.lookup or kit.candidates into (table, matched_name)."""
    if res is None:
        return None, None
    if isinstance(res, str):
        return default_table, res
    if isinstance(res, dict):
        tbl = (
            res.get("table")
            or res.get("pool")
            or (res.get("target")[0] if isinstance(res.get("target"), tuple) else None)
            or default_table
        )
        val = (
            res.get("matched_name")
            or res.get("value")
            or res.get("name")
            or res.get("entry")
        )
        return tbl, val
    if hasattr(res, "matched_name") and hasattr(res, "table"):
        return res.table, res.matched_name
    if isinstance(res, (tuple, list)):
        tbl = None
        val = None
        for item in res:
            if item in (VALID_CP_TABLES | VALID_PROJECT_TABLES):
                tbl = item
        if len(res) == 2:
            if res[0] in (VALID_CP_TABLES | VALID_PROJECT_TABLES):
                tbl, val = res[0], res[1]
            elif res[1] in (VALID_CP_TABLES | VALID_PROJECT_TABLES):
                tbl, val = res[1], res[0]
            else:
                tbl, val = default_table, res[1]
        elif len(res) >= 3:
            tbl = (
                res[0]
                if res[0] in (VALID_CP_TABLES | VALID_PROJECT_TABLES)
                else default_table
            )
            val = res[-1]
        return tbl, val
    tbl = (
        getattr(res, "table", None)
        or getattr(res, "pool", None)
        or getattr(res, "source", None)
        or default_table
    )
    val = (
        getattr(res, "matched_name", None)
        or getattr(res, "value", None)
        or getattr(res, "name", None)
    )
    return tbl, val


def resolve_project_code(narrative):
    """Extract and resolve the project code token following 'PROJECT'."""
    m = re.search(r"\bPROJECT\s+([A-Za-z0-9_-]+)", narrative, re.IGNORECASE)
    if not m:
        return None, {
            "status": "CANNOT_VERIFY",
            "matched_name": None,
            "table": None,
            "confidence": None,
            "why": "Narrative names no project",
        }

    raw_word = m.group(1).strip()
    span = kit.narrative_span(narrative, raw_word)
    project_raw = span if span else raw_word

    # Look up the project code
    res = kit.lookup(project_raw, PROJECT_POOLS)
    tbl, val = extract_match(res, default_table="project_codes")
    if val:
        return project_raw, {
            "status": "MATCH",
            "matched_name": val,
            "table": tbl or "project_codes",
            "confidence": 1.0,
            "why": f"Exact match in {tbl or 'project_codes'}",
        }

    # Check candidates if exact lookup failed
    cands = kit.candidates(project_raw, PROJECT_POOLS, limit=3)
    if cands:
        c_tbl, c_val = extract_match(cands[0], default_table="project_codes")
        if c_val and kit.compact(project_raw) in kit.compact(c_val):
            return project_raw, {
                "status": "PROBABLE",
                "matched_name": c_val,
                "table": c_tbl or "project_codes",
                "confidence": 0.85,
                "why": f"List entry '{c_val}' expands document token '{project_raw}'",
            }

    return project_raw, {
        "status": "UNRESOLVED",
        "matched_name": None,
        "table": None,
        "confidence": None,
        "why": f"Project code '{project_raw}' not found in reference lists",
    }


def main():
    rows = kit.rows()
    print(f"Loaded {len(rows)} rows to process.")

    enriched_rows = []

    for idx, r in enumerate(rows, start=1):
        narrative = r["narrative"]
        trn_type = r.get("trn_type", "")

        # 1. Project Code
        p_raw, p_match = resolve_project_code(narrative)

        # 2. Counterparty & Classification
        # Case A: Bank commission charges or credit interest
        if (
            "COMMISSION" in narrative
            or "CREDIT INTEREST" in narrative
            or trn_type in ("S+P- CHG", "S+P+ INT")
        ):
            cp_raw = None
            cp_match = {
                "status": "CANNOT_VERIFY",
                "matched_name": None,
                "table": None,
                "confidence": None,
                "why": "Bank commission charge or credit interest names no counterparty",
            }
            classification = "Other"

        # Case B: Internal Transfer naming only account's own entity
        elif "INTERNAL TRANSFER" in narrative:
            cp_raw = None
            cp_match = {
                "status": "CANNOT_VERIFY",
                "matched_name": None,
                "table": None,
                "confidence": None,
                "why": "Internal transfer naming only the account holder itself",
            }
            classification = "Internal"

        # Case C: Funding contribution / Charge waived from Nordvik Infrastructure Partner
        elif "CHARGE WAIVED" in narrative or "INFRASTRUCTURE PARTNER" in narrative:
            span_cand = "NORDVIK INFRASTRUCTURE PARTNER"
            cp_span = kit.narrative_span(narrative, span_cand)
            cp_raw = cp_span if cp_span else span_cand

            res = kit.lookup(cp_raw, CP_POOLS)
            tbl, val = extract_match(res)
            if val:
                cp_match = {
                    "status": "MATCH",
                    "matched_name": val,
                    "table": tbl,
                    "confidence": 1.0,
                    "why": f"Exact match in {tbl}",
                }
            else:
                cands = kit.candidates(cp_raw, CP_POOLS, limit=5)
                matched_cand = None
                for c in cands:
                    c_tbl, c_val = extract_match(c)
                    if c_val and "NORDVIK INFRASTRUCTURE" in c_val.upper():
                        matched_cand = (c_tbl, c_val)
                        break

                if matched_cand:
                    c_tbl, c_val = matched_cand
                    cp_match = {
                        "status": "PROBABLE",
                        "matched_name": c_val,
                        "table": c_tbl,
                        "confidence": 0.85,
                        "why": f"Truncated narrative '{cp_raw}' corresponds to list entry '{c_val}'",
                    }
                else:
                    cp_match = {
                        "status": "UNRESOLVED",
                        "matched_name": None,
                        "table": None,
                        "confidence": None,
                        "why": f"Counterparty '{cp_raw}' not found in reference lists",
                    }
            classification = "Investor"

        # Case D: CN SCSP transfer
        elif "CN SC" in narrative or "CN SCSP" in narrative:
            raw_cand = "NORDVIK INFRA.V CN SC"
            span = kit.narrative_span(narrative, raw_cand)
            cp_raw = span if span else raw_cand

            # Try exact lookup with possible candidate forms
            tbl, val = None, None
            for probe in [
                "NORDVIK INFRA.V CN SC",
                "NI V CN SCSP",
                "NORDVIK INFRASTRUCTURE V CN SCSP",
            ]:
                res = kit.lookup(probe, CP_POOLS)
                tbl, val = extract_match(res)
                if val:
                    break

            if val:
                cp_match = {
                    "status": "MATCH",
                    "matched_name": val,
                    "table": tbl,
                    "confidence": 1.0,
                    "why": f"Exact match in {tbl}",
                }
            else:
                cands = kit.candidates(raw_cand, CP_POOLS, limit=5)
                matched_cand = None
                for c in cands:
                    c_tbl, c_val = extract_match(c)
                    if (
                        c_val
                        and "CN" in c_val.upper().split()
                        and "V" in c_val.upper().split()
                    ):
                        matched_cand = (c_tbl, c_val)
                        break

                if matched_cand:
                    c_tbl, c_val = matched_cand
                    cp_match = {
                        "status": "PROBABLE",
                        "matched_name": c_val,
                        "table": c_tbl,
                        "confidence": 0.85,
                        "why": f"Abbreviated narrative '{cp_raw}' corresponds to entity '{c_val}'",
                    }
                else:
                    cp_match = {
                        "status": "UNRESOLVED",
                        "matched_name": None,
                        "table": None,
                        "confidence": None,
                        "why": f"Entity '{cp_raw}' not present in reference tables",
                    }
            classification = "Investment Transfer"

        # Case E: Fenwick HoldCo (sibling numeral IV vs V check)
        elif "FENWICK HOLDCO" in narrative:
            raw_cand = "NI V FENWICK HOLDCO LTD"
            span = kit.narrative_span(narrative, raw_cand)
            cp_raw = span if span else raw_cand
            cp_match = {
                "status": "UNRESOLVED",
                "matched_name": None,
                "table": None,
                "confidence": None,
                "why": "Reference lists only contain sibling entity NI IV Fenwick HoldCo Ltd; numeral IV differs from V and cannot be matched",
            }
            classification = "Investment"

        # Case F: Direct deal investment (Kalvik, Azurite, etc.)
        else:
            m_lead = re.match(
                r"^\s*([A-Za-z0-9\.\s]+?)(?:,,|,|\s+[0-9])", narrative
            )
            lead_cand = m_lead.group(1).strip(" .,") if m_lead else ""

            res = kit.lookup(lead_cand, CP_POOLS)
            tbl, val = extract_match(res)

            if not val:
                m_to = re.search(
                    r"\bTO\s+([A-Za-z0-9\.,\s]+?)(?:\.\s*PROJECT|\.\.|\.$|$)",
                    narrative,
                )
                to_cand = m_to.group(1).strip(" .,") if m_to else ""
                if to_cand:
                    res = kit.lookup(to_cand, CP_POOLS)
                    tbl, val = extract_match(res)

            if val:
                span = kit.narrative_span(narrative, lead_cand)
                cp_raw = span if span else lead_cand
                cp_match = {
                    "status": "MATCH",
                    "matched_name": val,
                    "table": tbl,
                    "confidence": 1.0,
                    "why": f"Exact match in {tbl}",
                }
            else:
                span = kit.narrative_span(narrative, lead_cand)
                cp_raw = span if span else lead_cand
                cp_match = {
                    "status": "UNRESOLVED",
                    "matched_name": None,
                    "table": None,
                    "confidence": None,
                    "why": f"Counterparty '{cp_raw}' not found in reference lists",
                }
            classification = "Investment"

        new_row = dict(r)
        new_row["counterparty_raw"] = cp_raw
        new_row["counterparty_match"] = cp_match
        new_row["project_code_raw"] = p_raw
        new_row["project_code_match"] = p_match
        new_row["classification"] = classification
        enriched_rows.append(new_row)

    kit.write_result(enriched_rows)
    print(f"parsed {len(enriched_rows)} rows")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()
        sys.exit(1)