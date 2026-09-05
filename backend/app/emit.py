"""Project a finished run into whatever envelope a profile asks for.

Two specifications want the same run described differently.
`docs/backend-model-evaluation.md` wants `statement_rows`, `mapping_results`,
`journal_entries`, `review_queue`. `docs/business-case-2-model-pipeline-
validation.md` wants `extracted_rows`, `mapping_summary`, `export_candidates`,
`blocked_exports`, `audit_trail`. Same documents, same passes, same checks —
different presentation and a different gate.

So the shape is declared and the *computing* is shared. A profile's `output`
block names keys and says where each one's content comes from:

    "run_id":        "@run_id"                  something the run already knows
    "document_set":  "bank_statements"          a literal
    "extracted_rows": "@rows"                   the rows, projected per `row`
    "review_queue":  "@derive:review_queue"     one of the derivations below

The derivations are engine code because they are the same work in both cases —
what a review queue *is* does not change between specifications. The choice and
the naming is profile data. That division is what lets the second profile be a
JSON file with no Python behind it, and it is the test the design has to pass.

Nothing here decides whether output is trustworthy. That already happened: the
checks ran, and a row's fate follows from their result.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.kit.reference_kit import normalise

# Statuses a row can carry and still be complete.
#
# `MATCH` is obvious. `CANNOT_VERIFY` is the one worth explaining: it means the
# document named nothing to resolve — a bank charge has no counterparty, and
# saying so is a finding, not a gap. Blocking on it would conflate "we looked
# and there is nothing there" with "we did not look", which is the exact
# distinction the fourth state exists to draw, and it would put 95 of 100 rows
# in a review queue that a person then stops reading.
#
# `UNRESOLVED` does block: a name was pulled out of the document and matched
# nothing, so somebody has to decide. So does a resolution that is simply
# absent, because that row was never examined at all.
SETTLED = {"MATCH", "CANNOT_VERIFY"}

# Why a row is in the review queue, in the vocabulary
# `business-case-2` §6C sets out. A reason a reviewer can act on beats a
# boolean they have to investigate.
REASONS = {
    "counterparty": "COUNTERPARTY_UNRESOLVED",
    "project_code": "PROJECT_CODE_UNRESOLVED",
    "position": "POSITION_MAPPING_FAILED",
    "classification": "LOW_CLASSIFICATION_CONFIDENCE",
    "citation": "MISSING_SOURCE_CITATION",
}


def _resolution(row: dict, field: str) -> dict:
    """A resolution as a dict, whether the profile nested it or flattened it."""
    value = row.get(field)
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return {"status": value}
    return {}


def _match_fields(row: dict, required: list[str] | None = None) -> list[str]:
    """The resolutions this row should carry.

    `required` comes from the profile, and including a field the row does not
    have is the point: a row missing a resolution entirely has not been
    examined, and treating absence as success is the failure both
    specifications name outright — "missing data becomes MATCH". So a declared
    field that is absent blocks export exactly as an unresolved one does.
    """
    present = [key for key in row if key.endswith("_match") or key.endswith("_status")]
    for key in required or []:
        if key not in present:
            present.append(key)
    return present


def _amount(row: dict):
    """One signed number from the statement's separate credit and debit columns.

    The statement already prints debits with a leading minus, so this selects
    rather than negates — inverting a sign that was already there is a way to
    silently double a correction.
    """
    for key in ("credit", "debit"):
        raw = row.get(key)
        if raw not in (None, ""):
            try:
                return float(str(raw).replace(",", ""))
            except ValueError:
                return None
    return None


# --- row-level derivations ----------------------------------------------


def _row_id(row: dict, index: int, context: dict) -> str:
    return f"{context.get('account', 'row')}-{index:03d}"


def _direction(row: dict, index: int, context: dict) -> str:
    return "credit" if row.get("credit") not in (None, "") else "debit"


def _signed_amount(row: dict, index: int, context: dict):
    return _amount(row)


def _source_citation(row: dict, index: int, context: dict) -> dict:
    """Where this row was read from. Never fabricated: if there is no page, say so."""
    page = row.get("page")
    return {
        "page": page,
        "snippet": normalise(row.get("narrative")) or normalise(row.get("bank_reference")),
    }


def _review_reason(row: dict, index: int, context: dict) -> str | None:
    """The first thing standing between this row and export, or None."""
    if row.get("page") is None:
        return REASONS["citation"]
    for field in _match_fields(row, context.get("requires")):
        status = normalise(_resolution(row, field).get("status")).upper()
        if status not in SETTLED:
            stem = field.rsplit("_", 1)[0]
            return REASONS.get(stem, f"{stem.upper()}_UNRESOLVED")
    if normalise(row.get("classification")).casefold() == "review":
        return REASONS["classification"]
    return None


def _ready_for_export(row: dict, index: int, context: dict) -> bool:
    return _review_reason(row, index, context) is None


ROW_DERIVATIONS = {
    "row_id": _row_id,
    "direction": _direction,
    "signed_amount": _signed_amount,
    "source_citation": _source_citation,
    "review_reason": _review_reason,
    "ready_for_export": _ready_for_export,
}


def project_row(row: dict, index: int, spec: dict, context: dict) -> dict:
    """One output row, built from a profile's field map."""
    out = {}
    for key, source in spec.items():
        if isinstance(source, str) and source.startswith("@derive:"):
            out[key] = ROW_DERIVATIONS[source.removeprefix("@derive:")](row, index, context)
        elif isinstance(source, str) and source.startswith("@status:"):
            # One specification nests the resolution and the other wants the
            # bare status. Reading it out here means the agent produces one
            # shape and both envelopes are served from it.
            out[key] = (
                normalise(_resolution(row, source.removeprefix("@status:")).get("status")).upper()
                or "CANNOT_VERIFY"
            )
        elif isinstance(source, str) and source.startswith("@"):
            out[key] = context.get(source[1:])
        elif isinstance(source, str) and source.startswith("$"):
            out[key] = row.get(source[1:])
        else:
            out[key] = source
    return out


# --- envelope-level derivations ------------------------------------------


def _rows_with_reasons(context: dict) -> list[tuple[int, dict, str | None]]:
    return [
        (i, row, _review_reason(row, i, context))
        for i, row in enumerate(context.get("rows", []))
    ]


def derive_review_queue(context: dict) -> list[dict]:
    """Everything a person has to decide, with what they need to decide it.

    `business-case-2` calls this the control surface rather than a side
    feature, and it is right: a queue of problems is work, a queue of decisions
    is progress. Each item carries its citation and the raw value, so the
    reviewer does not start from nothing.
    """
    queue = []
    for index, row, reason in _rows_with_reasons(context):
        if reason is None:
            continue
        item = {
            "row_id": _row_id(row, index, context),
            "reason": reason,
            "source_citation": _source_citation(row, index, context),
            "raw_narrative": normalise(row.get("narrative")),
            "amount": _amount(row),
            "currency": row.get("currency"),
        }
        for field in _match_fields(row, context.get("requires")):
            resolution = _resolution(row, field)
            if normalise(resolution.get("status")).upper() not in SETTLED:
                item[field] = resolution or {"status": "CANNOT_VERIFY"}
        queue.append(item)

    # A failing or unresolvable check is a review item too — it is not about one
    # row, so it would otherwise vanish from the only surface a person reads.
    for check in context.get("checks", []):
        # FAIL and UNRESOLVED only. A CANNOT_VERIFY check is the same finding as
        # a CANNOT_VERIFY row — the input to decide it was not in this run — and
        # there is nothing for a reviewer to do about it. It stays in `checks`,
        # where it is visible, rather than padding the queue they have to work.
        if check.get("status") in ("FAIL", "UNRESOLVED"):
            queue.append(
                {
                    "row_id": None,
                    "reason": f"CHECK_{check['status']}",
                    "check": check.get("name"),
                    "detail": check.get("detail"),
                    "evidence": check.get("evidence"),
                }
            )
    return queue


def derive_mapping_summary(context: dict) -> dict:
    """Counts per resolved field, per status.

    The number both specifications ask to see stated out loud rather than
    implied: how much did *not* resolve. Claiming 100% against data with known
    gaps is a named failure condition in each of them.
    """
    summary: dict[str, dict[str, int]] = {}
    for row in context.get("rows", []):
        for field in _match_fields(row, context.get("requires")):
            status = normalise(_resolution(row, field).get("status")).upper() or "MISSING"
            summary.setdefault(field, {})
            summary[field][status] = summary[field].get(status, 0) + 1
    return summary


def derive_export_candidates(context: dict) -> list[dict]:
    spec = context.get("row_spec", {})
    return [
        project_row(row, index, spec, context)
        for index, row, reason in _rows_with_reasons(context)
        if reason is None
    ]


def derive_blocked_exports(context: dict) -> list[dict]:
    """Rows held back, each saying why.

    Held back rather than dropped: hiding an unresolved row from the user is
    listed as disallowed behaviour, and so is exporting it as final.
    """
    spec = context.get("row_spec", {})
    return [
        {**project_row(row, index, spec, context), "review_reason": reason}
        for index, row, reason in _rows_with_reasons(context)
        if reason is not None
    ]


def derive_journal_entries(context: dict) -> list[dict]:
    """The journal lines the run produced, if it produced any.

    Empty is an honest answer while no pass builds them, and better than a
    plausible-looking guess: a batch that does not foot must never reach an
    export, so inventing one here would defeat the checks that come after.
    """
    lines = []
    for index, row in enumerate(context.get("rows", [])):
        for line in row.get("journal_lines") or []:
            lines.append({**line, "row_id": _row_id(row, index, context)})
    return lines


def derive_audit_trail(context: dict) -> dict:
    """What it takes to reconstruct this run if a number is challenged later.

    `business-case-2` §6A is explicit that a reviewer must be able to get back
    to the exact run that produced a figure, so this records the inputs by
    content hash rather than by name — a file can be replaced without its name
    changing.
    """
    return {
        "run_id": context.get("run_id"),
        "profile": context.get("profile"),
        "model": context.get("model"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": context.get("input_documents", []),
        "checks_run": [c.get("name") for c in context.get("checks", [])],
        "rows_in": context.get("rows_in", len(context.get("rows", []))),
        "rows_out": len(context.get("rows", [])),
    }


def derive_summary(context: dict) -> dict:
    """The clean split both specifications ask the demo to end on."""
    reasons = [reason for _, _, reason in _rows_with_reasons(context)]
    tally: dict[str, int] = {}
    for check in context.get("checks", []):
        status = check.get("status", "PASS")
        tally[status] = tally.get(status, 0) + 1
    return {
        "rows": len(context.get("rows", [])),
        "ready_for_export": sum(1 for r in reasons if r is None),
        "needs_review": sum(1 for r in reasons if r is not None),
        "checks": tally,
    }


DERIVATIONS = {
    "review_queue": derive_review_queue,
    "mapping_summary": derive_mapping_summary,
    "export_candidates": derive_export_candidates,
    "blocked_exports": derive_blocked_exports,
    "journal_entries": derive_journal_entries,
    "audit_trail": derive_audit_trail,
    "summary": derive_summary,
}


def file_digest(path) -> dict:
    return {
        "filename": getattr(path, "name", str(path)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def build(profile, context: dict) -> dict:
    """The envelope this profile declares, filled from a finished run."""
    output = profile.output or {}
    envelope = output.get("envelope") or {}
    context = {
        **context,
        "row_spec": output.get("row") or {},
        # Which resolutions this profile expects on every row. Absence of one
        # blocks export rather than passing silently.
        "requires": output.get("requires") or [],
    }

    if not envelope:
        # Nothing declared: emit what we have rather than an empty object, so a
        # profile mid-authoring still produces something inspectable.
        return {"rows": context.get("rows", []), "checks": context.get("checks", [])}

    built = {}
    for key, source in envelope.items():
        if isinstance(source, str) and source.startswith("@derive:"):
            built[key] = DERIVATIONS[source.removeprefix("@derive:")](context)
        elif source == "@rows":
            built[key] = [
                project_row(row, index, context["row_spec"], context)
                for index, row in enumerate(context.get("rows", []))
            ]
        elif isinstance(source, str) and source.startswith("@"):
            built[key] = context.get(source[1:])
        else:
            built[key] = source
    return built
