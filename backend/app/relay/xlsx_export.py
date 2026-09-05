from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

import xlsxwriter

from .models import OutputSnapshotView
from .snapshot_store import FrozenSnapshot
from .utils import iso_z, mode_label, spreadsheet_literal


SHEET_NAMES = [
    "Summary",
    "Findings",
    "Investor Terms",
    "Calculations",
    "Sources",
    "Audit Trail",
]


def write_xlsx_report(
    path: Path,
    frozen: FrozenSnapshot,
    generated_at: datetime,
    public_export: dict[str, Any],
) -> None:
    snapshot = frozen.snapshot
    workbook = xlsxwriter.Workbook(
        str(path),
        {
            "strings_to_formulas": False,
            "strings_to_urls": False,
            "constant_memory": False,
        },
    )
    workbook.set_calc_mode("auto")
    workbook.set_properties(
        {
            "title": "YLookup NAV Review",
            "subject": f"Management-fee checks for {snapshot.reporting_period}",
            "author": "YLookup RELAY",
            "company": "YLookup",
            "comments": "Generated only from the frozen review snapshot.",
        }
    )
    workbook.set_custom_property("YLookup Run ID", snapshot.run_id)
    workbook.set_custom_property("YLookup Review Version", str(snapshot.version))
    workbook.set_custom_property("YLookup Snapshot SHA256", frozen.snapshot_sha256)
    workbook.set_custom_property("YLookup Generated At", iso_z(generated_at))
    workbook.set_custom_property("YLookup Mode", snapshot.mode.value)
    formats = _formats(workbook)

    _write_summary(workbook, formats, snapshot, frozen, generated_at)
    _write_findings(workbook, formats, snapshot, frozen, generated_at)
    _write_terms(workbook, formats, snapshot, frozen, generated_at)
    _write_calculations(workbook, formats, snapshot, frozen, generated_at)
    _write_sources(workbook, formats, snapshot, frozen, generated_at)
    _write_audit(workbook, formats, snapshot, frozen, generated_at, public_export)
    workbook.close()
    validate_xlsx(path)


def validate_xlsx(path: Path) -> None:
    try:
        with ZipFile(path) as archive:
            corrupt = archive.testzip()
            if corrupt:
                raise ValueError(f"generated workbook contains a corrupt member: {corrupt}")
            names = set(archive.namelist())
            required = {"[Content_Types].xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml"}
            if not required.issubset(names):
                raise ValueError("generated workbook is missing required OOXML members")
            if any(name.startswith("xl/externalLinks/") for name in names):
                raise ValueError("generated workbook unexpectedly contains external links")
            if any(name.lower().endswith("vbaproject.bin") for name in names):
                raise ValueError("generated workbook unexpectedly contains VBA")
    except BadZipFile as exc:
        raise ValueError("generated workbook is not a valid XLSX archive") from exc


def _formats(workbook: xlsxwriter.Workbook) -> dict[str, Any]:
    base = {"font_name": "Arial", "font_size": 10, "font_color": "#243B53"}
    return {
        "title": workbook.add_format(
            {**base, "bold": True, "font_size": 17, "font_color": "#102A43", "bottom": 1, "bottom_color": "#CBD2D9"}
        ),
        "subtitle": workbook.add_format({**base, "italic": True, "font_color": "#52606D"}),
        "meta_label": workbook.add_format({**base, "bold": True, "font_color": "#334E68", "bg_color": "#F3F6F9"}),
        "meta_value": workbook.add_format({**base, "bg_color": "#F3F6F9"}),
        "meta_hash": workbook.add_format({**base, "font_size": 8, "bg_color": "#F3F6F9"}),
        "section": workbook.add_format(
            {**base, "bold": True, "font_color": "#102A43", "bottom": 1, "bottom_color": "#9FB3C8"}
        ),
        "header": workbook.add_format(
            {
                **base,
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#102A43",
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
                "border": 0,
            }
        ),
        "body": workbook.add_format({**base, "valign": "top"}),
        "wrap": workbook.add_format({**base, "text_wrap": True, "valign": "top"}),
        "small_wrap": workbook.add_format({**base, "font_size": 9, "text_wrap": True, "valign": "top"}),
        "integer": workbook.add_format(
            {**base, "num_format": "#,##0", "align": "right", "valign": "top"}
        ),
        "currency": workbook.add_format(
            {
                **base,
                "num_format": '#,##0.00;(#,##0.00);-',
                "align": "right",
                "valign": "top",
            }
        ),
        "percentage": workbook.add_format(
            {**base, "num_format": "0.00%", "align": "right", "valign": "top"}
        ),
        "decimal": workbook.add_format(
            {**base, "num_format": "0.0000", "align": "right", "valign": "top"}
        ),
        "date": workbook.add_format(
            {
                **base,
                "num_format": "yyyy-mm-dd hh:mm:ss",
                "align": "left",
                "valign": "top",
            }
        ),
        "count": workbook.add_format(
            {**base, "bold": True, "font_size": 15, "align": "center", "bg_color": "#EAF2FF"}
        ),
        "count_label": workbook.add_format(
            {**base, "font_size": 9, "align": "center", "bg_color": "#EAF2FF", "font_color": "#334E68"}
        ),
        "note": workbook.add_format(
            {**base, "italic": True, "font_color": "#52606D", "text_wrap": True, "valign": "top"}
        ),
        "warning": workbook.add_format(
            {**base, "font_color": "#8A5A00", "bg_color": "#FFF4D6", "text_wrap": True, "valign": "top"}
        ),
        "literal_formula": workbook.add_format(
            {**base, "font_name": "Courier New", "font_size": 9, "font_color": "#334E68"}
        ),
    }


def _add_sheet(workbook, name: str, tab_color: str | None = None):  # type: ignore[no-untyped-def]
    worksheet = workbook.add_worksheet(name)
    worksheet.hide_gridlines(2)
    if tab_color:
        worksheet.set_tab_color(tab_color)
    worksheet.set_landscape()
    worksheet.fit_to_pages(1, 0)
    worksheet.set_margins(0.35, 0.35, 0.5, 0.5)
    worksheet.set_header("&LYLookup NAV Review&R&P of &N")
    return worksheet


def _sheet_header(
    worksheet,
    formats,
    title: str,
    snapshot: OutputSnapshotView,
    frozen: FrozenSnapshot,
    generated_at: datetime,
    width: int,
) -> int:
    worksheet.set_row(0, 25)
    worksheet.write_string(0, 0, spreadsheet_literal(title), formats["title"])
    if width > 1:
        worksheet.set_row(1, 18)
        worksheet.write_string(
            1,
            0,
            spreadsheet_literal("Frozen output view - no analysis or calculation is rerun during export."),
            formats["subtitle"],
        )
    metadata = [
        ("Run ID", snapshot.run_id, "Review version", snapshot.version),
        ("Reporting period", snapshot.reporting_period, "Generated", iso_z(generated_at)),
        ("Mode", mode_label(snapshot.mode.value), "Snapshot SHA-256", frozen.snapshot_sha256),
    ]
    for row_offset, values in enumerate(metadata, start=2):
        worksheet.write_string(row_offset, 0, values[0], formats["meta_label"])
        worksheet.write_string(row_offset, 1, spreadsheet_literal(values[1]), formats["meta_value"])
        worksheet.write_string(row_offset, 2, values[2], formats["meta_label"])
        if isinstance(values[3], int):
            worksheet.write_number(row_offset, 3, values[3], formats["meta_value"])
        else:
            value_format = formats["meta_hash"] if values[2] == "Snapshot SHA-256" else formats["meta_value"]
            worksheet.write_string(row_offset, 3, spreadsheet_literal(values[3]), value_format)
    worksheet.set_row(5, 8)
    return 6


def _write_summary(workbook, formats, snapshot, frozen, generated_at):  # type: ignore[no-untyped-def]
    sheet = _add_sheet(workbook, "Summary", "#1D4ED8")
    row = _sheet_header(sheet, formats, "YLookup NAV Review", snapshot, frozen, generated_at, 8)
    counts = snapshot.summary_counts()
    sheet.write_string(row, 0, "Scope", formats["section"])
    sheet.write_string(row + 1, 0, spreadsheet_literal(snapshot.coverage.scope), formats["warning"])
    sheet.write_string(
        row + 2,
        0,
        "This workbook does not state that the entire NAV has been validated.",
        formats["note"],
    )
    row += 4
    cards = [
        ("Checks completed", counts["checks_completed"]),
        ("Matches", counts["matches"]),
        ("Discrepancies", counts["discrepancies"]),
        ("Cannot verify", counts["cannot_verify"]),
        ("Unsupported", counts["unsupported"]),
        ("Unreviewed", counts["unreviewed"]),
    ]
    for column, (label, value) in enumerate(cards):
        sheet.write_string(row, column, label, formats["count_label"])
        sheet.write_number(row + 1, column, value, formats["count"])
        sheet.set_column(column, column, 18)
    row += 4
    sheet.write_string(row, 0, "Review details", formats["section"])
    details = [
        ("Fund", snapshot.fund_name or "Not supplied"),
        ("Documents reviewed", len([item for item in snapshot.source_documents if item.supplied])),
        ("Checks expected", snapshot.coverage.checks_expected),
        ("Computational states", "Human review does not alter MATCH, DISCREPANCY, CANNOT_VERIFY or UNSUPPORTED."),
    ]
    for offset, (label, value) in enumerate(details, start=1):
        sheet.write_string(row + offset, 0, label, formats["meta_label"])
        if isinstance(value, int):
            sheet.write_number(row + offset, 1, value, formats["integer"])
        elif value is None:
            sheet.write_string(row + offset, 1, "Not supplied", formats["body"])
        else:
            sheet.write_string(row + offset, 1, spreadsheet_literal(value), formats["wrap"])
    row += len(details) + 3
    sheet.write_string(row, 0, "Important limitations", formats["section"])
    limitation = (
        "This review checks the management-fee calculations described in this workbook. "
        "It does not constitute legal advice, regulated approval, audit certification, "
        "or validation of the entire NAV. "
        + (
            "Synthetic demo rules are simplified. "
            if snapshot.mode.value == "SYNTHETIC_DEMO"
            else ""
        )
        + (
            "Upstream limitations: " + " | ".join(snapshot.limitations)
            if snapshot.limitations
            else ""
        )
    )
    sheet.merge_range(row + 1, 0, row + 1, 5, limitation, formats["warning"])
    sheet.set_row(row + 1, 66)
    sheet.set_column(0, 0, 24)
    sheet.set_column(1, 1, 42)
    sheet.set_column(2, 2, 20)
    sheet.set_column(3, 3, 44)


def _write_findings(workbook, formats, snapshot, frozen, generated_at):  # type: ignore[no-untyped-def]
    sheet = _add_sheet(workbook, "Findings", "#A61B1B")
    row = _sheet_header(sheet, formats, "Findings", snapshot, frozen, generated_at, 11)
    headers = [
        "Investor",
        "Check Type",
        "Administrator Value",
        "Expected Value",
        "Difference",
        "Variance Direction",
        "Computational Status",
        "Human Review Status",
        "Explanation",
        "Calculation ID",
        "Evidence IDs",
    ]
    _write_headers(sheet, row, headers, formats)
    for index, finding in enumerate(snapshot.findings, start=row + 1):
        _write_text(sheet, index, 0, finding.investor_id, formats["body"])
        _write_text(sheet, index, 1, finding.check_type, formats["body"])
        _write_number_or_blank(sheet, index, 2, finding.administrator_value, formats["currency"])
        _write_number_or_blank(sheet, index, 3, finding.expected_value, formats["currency"])
        _write_number_or_blank(sheet, index, 4, finding.difference, formats["currency"])
        _write_text(sheet, index, 5, finding.variance_direction, formats["wrap"])
        _write_text(sheet, index, 6, finding.computational_status.value, formats["body"])
        _write_text(sheet, index, 7, finding.human_review_status.value, formats["body"])
        _write_text(sheet, index, 8, finding.explanation, formats["wrap"])
        _write_text(sheet, index, 9, finding.calculation_id or "", formats["body"])
        _write_text(sheet, index, 10, ", ".join(finding.evidence_ids), formats["wrap"])
        sheet.set_row(index, 44)
    last_row = row + max(1, len(snapshot.findings))
    sheet.freeze_panes(row + 1, 1)
    sheet.autofilter(row, 0, last_row, len(headers) - 1)
    sheet.conditional_format(row + 1, 6, last_row, 6, {"type": "text", "criteria": "containing", "value": "DISCREPANCY", "format": workbook.add_format({"font_color": "#A61B1B", "bg_color": "#FDECEC", "bold": True})})
    sheet.conditional_format(row + 1, 6, last_row, 6, {"type": "text", "criteria": "containing", "value": "CANNOT_VERIFY", "format": workbook.add_format({"font_color": "#8A5A00", "bg_color": "#FFF4D6", "bold": True})})
    widths = [12, 20, 20, 18, 16, 28, 22, 20, 65, 28, 45]
    for column, width in enumerate(widths):
        sheet.set_column(column, column, width)


def _write_terms(workbook, formats, snapshot, frozen, generated_at):  # type: ignore[no-untyped-def]
    sheet = _add_sheet(workbook, "Investor Terms")
    row = _sheet_header(sheet, formats, "Investor Terms", snapshot, frozen, generated_at, 11)
    headers = [
        "Investor",
        "Term",
        "Default Rate",
        "Override Rate",
        "Applicable Rate",
        "Effective From",
        "Effective To",
        "Fee Base",
        "Currency",
        "Evidence IDs",
        "Applicability State",
    ]
    _write_headers(sheet, row, headers, formats)
    for index, term in enumerate(snapshot.investor_terms, start=row + 1):
        _write_text(sheet, index, 0, term.investor_id, formats["body"])
        _write_text(sheet, index, 1, term.term, formats["body"])
        _write_number_or_blank(sheet, index, 2, term.default_rate_fraction, formats["percentage"])
        _write_number_or_blank(sheet, index, 3, term.override_rate_fraction, formats["percentage"])
        _write_number_or_blank(sheet, index, 4, term.applicable_rate_fraction, formats["percentage"])
        _write_text(sheet, index, 5, term.effective_from or "Not supplied", formats["body"])
        _write_text(sheet, index, 6, term.effective_to or "Not supplied", formats["body"])
        _write_number_or_blank(sheet, index, 7, term.fee_base, formats["currency"])
        _write_text(sheet, index, 8, term.currency, formats["body"])
        _write_text(sheet, index, 9, ", ".join(term.evidence_ids), formats["wrap"])
        _write_text(sheet, index, 10, term.applicability_state, formats["wrap"])
    last_row = row + max(1, len(snapshot.investor_terms))
    sheet.freeze_panes(row + 1, 1)
    sheet.autofilter(row, 0, last_row, len(headers) - 1)
    widths = [12, 20, 16, 16, 16, 16, 16, 18, 11, 46, 22]
    for column, width in enumerate(widths):
        sheet.set_column(column, column, width)


def _write_calculations(workbook, formats, snapshot, frozen, generated_at):  # type: ignore[no-untyped-def]
    sheet = _add_sheet(workbook, "Calculations", "#176B3A")
    row = _sheet_header(sheet, formats, "Calculations", snapshot, frozen, generated_at, 11)
    headers = [
        "Investor",
        "Fee Base",
        "Annual Rate",
        "Period Factor",
        "Application Formula",
        "Formula Text",
        "Server Calculated Expected Fee",
        "Reported Fee",
        "Difference",
        "Currency",
        "Calculation ID",
    ]
    _write_headers(sheet, row, headers, formats)
    for index, calculation in enumerate(snapshot.calculations, start=row + 1):
        excel_row = index + 1
        _write_text(sheet, index, 0, calculation.investor_id, formats["body"])
        _write_number_or_blank(sheet, index, 1, calculation.fee_base, formats["currency"])
        _write_number_or_blank(sheet, index, 2, calculation.annual_rate_fraction, formats["percentage"])
        _write_number_or_blank(sheet, index, 3, calculation.period_factor, formats["decimal"])
        formula = f"=B{excel_row}*C{excel_row}*D{excel_row}"
        if all(
            value is not None
            for value in (
                calculation.fee_base,
                calculation.annual_rate_fraction,
                calculation.period_factor,
                calculation.expected_value,
            )
        ):
            sheet.write_formula(index, 4, formula, formats["currency"], calculation.expected_value)
            # This is an application-authored explanation string. `write_string`
            # plus `strings_to_formulas=False` keeps it visibly literal without
            # exposing an executable formula cell or an on-screen apostrophe.
            sheet.write_string(index, 5, formula, formats["literal_formula"])
        else:
            sheet.write_string(index, 4, "Not available", formats["body"])
            sheet.write_string(index, 5, "Not available", formats["body"])
        _write_number_or_blank(sheet, index, 6, calculation.expected_value, formats["currency"])
        _write_number_or_blank(sheet, index, 7, calculation.reported_value, formats["currency"])
        _write_number_or_blank(sheet, index, 8, calculation.difference, formats["currency"])
        _write_text(sheet, index, 9, calculation.currency, formats["body"])
        _write_text(sheet, index, 10, calculation.calculation_id, formats["body"])
    last_row = row + max(1, len(snapshot.calculations))
    sheet.freeze_panes(row + 1, 1)
    sheet.autofilter(row, 0, last_row, len(headers) - 1)
    widths = [12, 18, 16, 15, 22, 24, 25, 18, 18, 11, 30]
    for column, width in enumerate(widths):
        sheet.set_column(column, column, width)


def _write_sources(workbook, formats, snapshot, frozen, generated_at):  # type: ignore[no-untyped-def]
    sheet = _add_sheet(workbook, "Sources")
    row = _sheet_header(sheet, formats, "Sources", snapshot, frozen, generated_at, 10)
    headers = [
        "Document",
        "Document ID",
        "Role",
        "SHA-256",
        "Hash Status",
        "Evidence ID",
        "Page / Section / Sheet / Cell",
        "Quoted Text / Value",
        "Context",
        "Source Kind",
    ]
    _write_headers(sheet, row, headers, formats)
    documents = {document.document_id: document for document in snapshot.source_documents}
    for index, evidence in enumerate(snapshot.evidence_references, start=row + 1):
        document = documents[evidence.document_id]
        _write_text(sheet, index, 0, document.filename, formats["wrap"])
        _write_text(sheet, index, 1, document.document_id, formats["body"])
        _write_text(sheet, index, 2, document.role, formats["body"])
        _write_text(sheet, index, 3, document.sha256 or "Not supplied", formats["small_wrap"])
        _write_text(sheet, index, 4, "SUPPLIED" if document.sha256 else "NOT_SUPPLIED", formats["body"])
        _write_text(sheet, index, 5, evidence.evidence_id, formats["body"])
        _write_text(sheet, index, 6, evidence.locator, formats["wrap"])
        quote_or_value = evidence.quoted_text or evidence.value or "Not supplied"
        _write_text(sheet, index, 7, quote_or_value, formats["wrap"])
        _write_text(sheet, index, 8, evidence.context or "", formats["wrap"])
        _write_text(sheet, index, 9, evidence.source_kind, formats["body"])
        sheet.set_row(index, 48)
    last_row = row + max(1, len(snapshot.evidence_references))
    sheet.freeze_panes(row + 1, 1)
    sheet.autofilter(row, 0, last_row, len(headers) - 1)
    widths = [32, 28, 18, 66, 16, 28, 36, 70, 55, 16]
    for column, width in enumerate(widths):
        sheet.set_column(column, column, width)


def _write_audit(workbook, formats, snapshot, frozen, generated_at, public_export):  # type: ignore[no-untyped-def]
    sheet = _add_sheet(workbook, "Audit Trail")
    row = _sheet_header(sheet, formats, "Audit Trail", snapshot, frozen, generated_at, 8)
    headers = [
        "Timestamp",
        "Run Version",
        "Finding",
        "Reviewer",
        "Action",
        "Previous State",
        "New State",
        "Note",
    ]
    _write_headers(sheet, row, headers, formats)
    for index, event in enumerate(public_export["audit_trail"], start=row + 1):
        parsed = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        sheet.write_datetime(index, 0, parsed, formats["date"])
        sheet.write_number(index, 1, int(event["run_version"]), formats["integer"])
        _write_text(sheet, index, 2, event.get("finding_id") or "", formats["body"])
        _write_text(sheet, index, 3, event.get("reviewer") or "", formats["body"])
        _write_text(sheet, index, 4, event.get("action") or "", formats["wrap"])
        _write_text(sheet, index, 5, event.get("previous_state") or "", formats["body"])
        _write_text(sheet, index, 6, event.get("new_state") or "", formats["body"])
        _write_text(sheet, index, 7, event.get("note") or "", formats["wrap"])
        sheet.set_row(index, 34)
    last_row = row + max(1, len(public_export["audit_trail"]))
    sheet.freeze_panes(row + 1, 1)
    sheet.autofilter(row, 0, last_row, len(headers) - 1)
    widths = [22, 13, 30, 22, 28, 20, 20, 70]
    for column, width in enumerate(widths):
        sheet.set_column(column, column, width)


def _write_headers(sheet, row: int, headers: list[str], formats: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
    sheet.set_row(row, 30)
    for column, header in enumerate(headers):
        sheet.write_string(row, column, header, formats["header"])


def _write_text(sheet, row: int, column: int, value: Any, cell_format: Any) -> None:  # type: ignore[no-untyped-def]
    literal = spreadsheet_literal(value)
    if literal == "":
        sheet.write_blank(row, column, None, cell_format)
    else:
        sheet.write_string(row, column, literal, cell_format)


def _write_number_or_blank(sheet, row: int, column: int, value: float | None, cell_format: Any) -> None:  # type: ignore[no-untyped-def]
    if value is None:
        sheet.write_blank(row, column, None, cell_format)
    else:
        sheet.write_number(row, column, float(value), cell_format)
