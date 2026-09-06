"""A CSV view of completed statement-job data, never another analysis pass."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import quote

from app.relay.utils import spreadsheet_literal
from app.verification.checks import _as_date

CSV_SCHEMA_VERSION = "transactions.v1"
CSV_CONTENT_TYPE = "text/csv; charset=utf-8"
CSV_COLUMNS = (
    "schema_version", "job_id", "profile_id", "case_name", "execution_label",
    "agent_resolution_status", "job_processing_state", "source_id", "source_filename",
    "source_relative_path", "document_hash", "atlas_document_id", "atlas_extraction_status",
    "document_processing_state", "computational_outcome", "account_short_code",
    "account_number", "currency", "row_id", "source_index", "chain_order",
    "value_date", "value_date_iso", "post_date", "time", "bank_reference",
    "customer_reference", "trn_type", "narrative", "credit", "debit", "signed_movement",
    "balance", "link_status", "difference", "finding_id", "older_row_id",
    "derived_balance", "comparison_balance", "citation_page", "citation_x0", "citation_top",
    "citation_x1", "citation_bottom",
)
_DECIMAL_COLUMNS = {
    "credit", "debit", "signed_movement", "balance", "difference",
    "derived_balance", "comparison_balance",
}
_NUMERIC_COLUMNS = {
    "source_index", "chain_order", "citation_page", "citation_x0", "citation_top",
    "citation_x1", "citation_bottom",
}
_DECIMAL = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", re.ASCII)


@dataclass(frozen=True)
class TransactionCsv:
    content: bytes
    row_count: int
    filename: str
    url: str

    def descriptor(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "filename": self.filename,
            "content_type": CSV_CONTENT_TYPE,
            "row_count": self.row_count,
            "sha256": hashlib.sha256(self.content).hexdigest(),
        }


def _decimal_cell(value: str | None) -> str:
    """Keep exact signed decimals; never treat a formula-looking string as money."""
    if value is None:
        return ""
    if not isinstance(value, str) or _DECIMAL.fullmatch(value) is None or not Decimal(value).is_finite():
        raise ValueError("CSV amount must be an exact finite decimal string or null")
    return value


def build_transactions_csv(result: dict[str, Any]) -> TransactionCsv:
    """Flatten only existing rows/links, retaining source order and raw evidence.

    The supported statements run newest-first. ``chain_order`` is the reverse
    ordinal within the same source, not a date/time sort. The oldest row has no
    adjacent older-row finding, so its link fields are empty, never a made-up
    PASS. Financial outcomes and signed movement come from the existing result.
    Human-review actions do not alter these CSV bytes or their descriptor hash.
    """
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    count = 0
    for document in result.get("documents", []):
        if document.get("purpose") != "SOURCE" or document.get("processing_state") != "SUCCEEDED":
            continue
        rows = document.get("rows", [])
        links = {link["newer_row_id"]: link for link in document.get("transaction_links", [])}
        statement = document.get("statement") or {}
        atlas = document.get("atlas") or {}
        for row in rows:
            citation = row.get("citation") or {}
            bbox = citation.get("bbox") or {}
            link = links.get(row["row_id"], {})
            value_date = row.get("value_date", "")
            parsed_date = _as_date(value_date)
            record = {
                "schema_version": CSV_SCHEMA_VERSION,
                "job_id": result["job_id"],
                "profile_id": result["profile_id"],
                "case_name": result["case_name"],
                "execution_label": result["execution_label"],
                "agent_resolution_status": result["agent_resolution"]["status"],
                "job_processing_state": result["processing_state"],
                "source_id": document["source_id"],
                "source_filename": document["filename"],
                "source_relative_path": document["relative_path"],
                "document_hash": citation.get("document_hash") or document.get("sha256"),
                "atlas_document_id": citation.get("atlas_document_id") or atlas.get("document_id"),
                "atlas_extraction_status": atlas.get("extraction_status"),
                "document_processing_state": document["processing_state"],
                "computational_outcome": document.get("computational_outcome"),
                "account_short_code": statement.get("account_short_code"),
                "account_number": row.get("account_number"),
                "currency": row.get("currency"),
                "row_id": row["row_id"],
                "source_index": row["index"],
                "chain_order": len(rows) - 1 - row["index"],
                "value_date": value_date,
                "value_date_iso": parsed_date.isoformat() if parsed_date else "",
                "post_date": row.get("post_date"),
                "time": row.get("time"),
                "bank_reference": row.get("bank_reference"),
                "customer_reference": row.get("customer_reference"),
                "trn_type": row.get("trn_type"),
                "narrative": row.get("narrative"),
                "credit": row.get("credit"),
                "debit": row.get("debit"),
                "signed_movement": row.get("signed_movement"),
                "balance": row.get("balance"),
                "link_status": link.get("status"),
                "difference": link.get("difference"),
                "finding_id": link.get("finding_id"),
                "older_row_id": link.get("older_row_id"),
                "derived_balance": link.get("derived_balance"),
                "comparison_balance": link.get("comparison_balance"),
                "citation_page": citation.get("page"),
                "citation_x0": bbox.get("x0"),
                "citation_top": bbox.get("top"),
                "citation_x1": bbox.get("x1"),
                "citation_bottom": bbox.get("bottom"),
            }
            writer.writerow({
                key: _decimal_cell(value) if key in _DECIMAL_COLUMNS
                else value if key in _NUMERIC_COLUMNS
                else spreadsheet_literal(value)
                for key, value in record.items()
            })
            count += 1
    job_id = result["job_id"]
    return TransactionCsv(
        content=stream.getvalue().encode("utf-8"),
        row_count=count,
        filename=f"{job_id}-transactions.csv",
        url=f"/api/ui/v1/jobs/{quote(job_id, safe='')}/transactions.csv",
    )
