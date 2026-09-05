from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import FindingStatus, HumanReviewDecision, OutputSnapshotView
from .snapshot_store import FrozenSnapshot
from .utils import bounded_text, iso_z, mode_label, money_text


NAVY = colors.HexColor("#102A43")
BLUE = colors.HexColor("#1D4ED8")
PALE_BLUE = colors.HexColor("#EAF2FF")
PALE_RED = colors.HexColor("#FDECEC")
RED = colors.HexColor("#A61B1B")
PALE_AMBER = colors.HexColor("#FFF4D6")
AMBER = colors.HexColor("#8A5A00")
PALE_GREEN = colors.HexColor("#EAF7EF")
GREEN = colors.HexColor("#176B3A")
GREY = colors.HexColor("#52606D")
LIGHT_GREY = colors.HexColor("#E4E7EB")
OFF_WHITE = colors.HexColor("#F7F9FC")


def write_pdf_report(path: Path, frozen: FrozenSnapshot, generated_at: datetime) -> None:
    snapshot = frozen.snapshot
    styles = _styles()
    decisions = {decision.finding_id: decision for decision in snapshot.human_review_decisions}
    calculations = snapshot.calculation_by_id()
    evidence = snapshot.evidence_by_id()
    counts = snapshot.summary_counts()

    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=19 * mm,
        title="CrazyMonkey NAV Review",
        author="CrazyMonkey RELAY",
        subject=(
            f"Run {snapshot.run_id}, version {snapshot.version}, "
            f"snapshot {frozen.snapshot_sha256}"
        ),
    )
    story = []
    story.extend(
        [
            Paragraph("CRAZYMONKEY NAV REVIEW", styles["title"]),
            Paragraph(
                escape(snapshot.fund_name or "Investor-level management-fee review"),
                styles["subtitle"],
            ),
            Spacer(1, 4 * mm),
            _metadata_table(snapshot, frozen.snapshot_sha256, generated_at, styles),
            Paragraph(
                "Snapshot identity: " + escape(frozen.snapshot_sha256),
                styles["hash"],
            ),
            Spacer(1, 6 * mm),
            _section("SCOPE", styles),
            Paragraph(escape(snapshot.coverage.scope), styles["scope"]),
            Paragraph(
                "This report checks only the management-fee calculations listed below. "
                "It does not state that the entire NAV has been validated.",
                styles["body"],
            ),
            Spacer(1, 5 * mm),
            _section("SUMMARY", styles),
            _summary_table(counts, styles),
            Spacer(1, 6 * mm),
        ]
    )

    discrepancies = [
        finding
        for finding in snapshot.findings
        if finding.computational_status == FindingStatus.DISCREPANCY
    ]
    story.append(_section("KEY EXCEPTIONS", styles))
    if not discrepancies:
        story.append(Paragraph("No discrepancies are present in this snapshot.", styles["body"]))
    for exception_index, finding in enumerate(discrepancies):
        if exception_index:
            story.append(PageBreak())
        calculation = calculations.get(finding.calculation_id or "")
        related_evidence = [evidence[item] for item in finding.evidence_ids if item in evidence]
        decision = decisions.get(finding.finding_id)
        story.extend(
            _exception_block(
                finding,
                calculation,
                related_evidence,
                decision,
                styles,
            )
        )
        story.append(Spacer(1, 4 * mm))

    cannot_verify = [
        finding
        for finding in snapshot.findings
        if finding.computational_status == FindingStatus.CANNOT_VERIFY
    ]
    story.extend([Spacer(1, 2 * mm), _section("CANNOT VERIFY", styles)])
    if not cannot_verify:
        story.append(Paragraph("No cannot-verify findings are present.", styles["body"]))
    for finding in cannot_verify:
        issue = next(
            (
                issue
                for issue in snapshot.unresolved_issues
                if issue.finding_id == finding.finding_id
            ),
            None,
        )
        issue_text = issue.summary if issue is not None else finding.explanation
        if issue is not None and issue.missing_evidence:
            issue_text += " Missing evidence: " + "; ".join(issue.missing_evidence)
        story.append(
            KeepTogether(
                [
                    Paragraph(escape(finding.investor_id), styles["finding_title"]),
                    Paragraph(escape(bounded_text(issue_text, 3000)), styles["warning"]),
                    Paragraph(
                        "Human review: "
                        + escape(_review_description(decisions.get(finding.finding_id))),
                        styles["small"],
                    ),
                ]
            )
        )
        story.append(Spacer(1, 3 * mm))

    story.extend(
        [
            Spacer(1, 3 * mm),
            _section("HUMAN REVIEW", styles),
            _human_review_table(snapshot, decisions, styles),
            Spacer(1, 6 * mm),
            _section("LIMITATIONS", styles),
            Paragraph(
                "This review checks the management-fee calculations described above. "
                "It does not constitute legal advice, regulated approval, audit certification, "
                "or validation of the entire NAV.",
                styles["limitation"],
            ),
            Paragraph(
                (
                    "Synthetic demo rules are simplified. "
                    if snapshot.mode.value == "SYNTHETIC_DEMO"
                    else ""
                )
                + "OCR or image-only PDFs may be unsupported. "
                "Every finding remains subject to human review.",
                styles["body"],
            ),
            *[
                Paragraph("Upstream limitation: " + escape(bounded_text(item, 3000)), styles["body"])
                for item in snapshot.limitations
            ],
            PageBreak(),
            _section("SOURCE AND CALCULATION INDEX", styles),
            Paragraph(
                "The identifiers below link each displayed result to the frozen snapshot. "
                "A missing document hash is shown explicitly and is not treated as verified.",
                styles["body"],
            ),
            Spacer(1, 3 * mm),
            _source_table(snapshot, styles),
            Spacer(1, 6 * mm),
            _calculation_table(snapshot, styles),
        ]
    )

    def decorate_page(canvas, doc) -> None:  # type: ignore[no-untyped-def]
        canvas.saveState()
        canvas.setTitle("CrazyMonkey NAV Review")
        canvas.setAuthor("CrazyMonkey RELAY")
        canvas.setSubject(
            f"Run {snapshot.run_id}; version {snapshot.version}; snapshot {frozen.snapshot_sha256}"
        )
        canvas.setStrokeColor(LIGHT_GREY)
        canvas.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GREY)
        footer = (
            f"Run {snapshot.run_id} | v{snapshot.version} | "
            f"{mode_label(snapshot.mode.value)} | {iso_z(generated_at)}"
        )
        canvas.drawString(18 * mm, 9.5 * mm, footer[:115])
        canvas.drawRightString(A4[0] - 18 * mm, 9.5 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=decorate_page, onLaterPages=decorate_page)
    validate_pdf(path)


def validate_pdf(path: Path) -> None:
    reader = PdfReader(str(path))
    if not reader.pages:
        raise ValueError("generated PDF has no pages")
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    required = ("CRAZYMONKEY NAV REVIEW", "Management-fee checks only", "LIMITATIONS")
    missing = [value for value in required if value not in text]
    if missing:
        raise ValueError(f"generated PDF is missing required text: {missing}")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "RelayTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=3,
        ),
        "subtitle": ParagraphStyle(
            "RelaySubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=GREY,
        ),
        "section": ParagraphStyle(
            "RelaySection",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=NAVY,
            spaceBefore=2,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "RelayBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#243B53"),
            spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "RelaySmall",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=GREY,
        ),
        "hash": ParagraphStyle(
            "RelayHash",
            parent=base["BodyText"],
            fontName="Courier",
            fontSize=5.2,
            leading=7,
            textColor=GREY,
        ),
        "scope": ParagraphStyle(
            "RelayScope",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=BLUE,
            spaceAfter=4,
        ),
        "finding_title": ParagraphStyle(
            "RelayFindingTitle",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=NAVY,
            spaceAfter=3,
        ),
        "exception": ParagraphStyle(
            "RelayException",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#3B1B1B"),
        ),
        "warning": ParagraphStyle(
            "RelayWarning",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=AMBER,
            backColor=PALE_AMBER,
            borderPadding=6,
            spaceAfter=4,
        ),
        "limitation": ParagraphStyle(
            "RelayLimitation",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=13,
            textColor=NAVY,
            backColor=OFF_WHITE,
            borderPadding=7,
            spaceAfter=5,
        ),
        "table_header": ParagraphStyle(
            "RelayTableHeader",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9,
            textColor=colors.white,
            alignment=TA_CENTER,
        ),
        "table_cell": ParagraphStyle(
            "RelayTableCell",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.2,
            leading=9,
            textColor=colors.HexColor("#243B53"),
        ),
    }


def _section(title: str, styles: dict[str, ParagraphStyle]) -> Table:
    table = Table([[Paragraph(escape(title), styles["section"])]], colWidths=[174 * mm])
    table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.8, LIGHT_GREY),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    return table


def _metadata_table(
    snapshot: OutputSnapshotView,
    digest: str,
    generated_at: datetime,
    styles: dict[str, ParagraphStyle],
) -> Table:
    rows = [
        ("Run ID", snapshot.run_id, "Review version", str(snapshot.version)),
        ("Reporting period", snapshot.reporting_period, "Generated", iso_z(generated_at)),
        ("Mode", mode_label(snapshot.mode.value), "Snapshot SHA-256", digest),
    ]
    data = []
    for row in rows:
        data.append(
            [
                Paragraph(f"<b>{escape(row[0])}</b>", styles["small"]),
                Paragraph(escape(row[1]), styles["small"]),
                Paragraph(f"<b>{escape(row[2])}</b>", styles["small"]),
                Paragraph(
                    escape(row[3]),
                    styles["hash"] if row[2] == "Snapshot SHA-256" else styles["small"],
                ),
            ]
        )
    table = Table(data, colWidths=[25 * mm, 60 * mm, 28 * mm, 61 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), OFF_WHITE),
                ("BOX", (0, 0), (-1, -1), 0.5, LIGHT_GREY),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, LIGHT_GREY),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _summary_table(counts: dict[str, int], styles: dict[str, ParagraphStyle]) -> Table:
    columns = [
        ("Checks", counts["checks_completed"], PALE_BLUE, BLUE),
        ("Matches", counts["matches"], PALE_GREEN, GREEN),
        ("Discrepancies", counts["discrepancies"], PALE_RED, RED),
        ("Cannot verify", counts["cannot_verify"], PALE_AMBER, AMBER),
        ("Unsupported", counts["unsupported"], OFF_WHITE, GREY),
    ]
    data = [
        [Paragraph(escape(label), styles["small"]) for label, _, _, _ in columns],
        [Paragraph(f"<b>{value}</b>", styles["finding_title"]) for _, value, _, _ in columns],
    ]
    table = Table(data, colWidths=[34.8 * mm] * 5, rowHeights=[8 * mm, 12 * mm])
    commands = [
        ("BOX", (0, 0), (-1, -1), 0.4, LIGHT_GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for index, (_, _, background, foreground) in enumerate(columns):
        commands.extend(
            [
                ("BACKGROUND", (index, 0), (index, -1), background),
                ("TEXTCOLOR", (index, 0), (index, -1), foreground),
            ]
        )
    table.setStyle(TableStyle(commands))
    return table


def _exception_block(finding, calculation, evidence, decision, styles):  # type: ignore[no-untyped-def]
    heading = f"{escape(finding.investor_id)} - {escape(finding.check_type)}"
    amount_rows = [
        ["Administrator", money_text(finding.administrator_value, finding.currency)],
        ["Expected", money_text(finding.expected_value, finding.currency)],
        ["Difference", money_text(finding.difference, finding.currency)],
    ]
    amounts = Table(amount_rows, colWidths=[35 * mm, 50 * mm])
    amounts.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#243B53")),
                ("BACKGROUND", (0, 0), (-1, -1), PALE_RED),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, RED),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    content = [KeepTogether([Paragraph(heading, styles["finding_title"]), amounts]), Spacer(1, 2 * mm)]
    content.append(Paragraph(escape(bounded_text(finding.explanation, 4000)), styles["exception"]))
    if calculation:
        expression = calculation.expression or "Formula description not supplied"
        content.append(
            Paragraph(
                f"<b>Calculation:</b> {escape(expression)}<br/><b>Expected fee:</b> "
                f"{escape(money_text(calculation.expected_value, calculation.currency))}",
                styles["exception"],
            )
        )
    if evidence:
        refs = "<br/>".join(
            f"{escape(bounded_text(item.filename, 240))} / {escape(bounded_text(item.locator, 500))} "
            f"[{escape(item.evidence_id)}]"
            for item in evidence
        )
        content.append(Paragraph(f"<b>Evidence:</b><br/>{refs}", styles["exception"]))
    content.append(
        Paragraph(
            "<b>Human review:</b> " + escape(_review_description(decision)),
            styles["exception"],
        )
    )
    return content


def _review_description(decision: HumanReviewDecision | None) -> str:
    if decision is None:
        return "UNREVIEWED; reviewer and timestamp not supplied"
    reviewer = decision.reviewer_label or "reviewer not supplied"
    reviewed_at = iso_z(decision.timestamp) if decision.timestamp else "timestamp not supplied"
    note = f"; note: {decision.notes}" if decision.notes else ""
    return f"{decision.state.value}; {reviewer}; {reviewed_at}{note}"


def _human_review_table(snapshot, decisions, styles):  # type: ignore[no-untyped-def]
    data = [
        [
            Paragraph("Investor", styles["table_header"]),
            Paragraph("Finding", styles["table_header"]),
            Paragraph("State", styles["table_header"]),
            Paragraph("Reviewer", styles["table_header"]),
            Paragraph("Timestamp / note", styles["table_header"]),
        ]
    ]
    for finding in snapshot.findings:
        decision = decisions.get(finding.finding_id)
        detail = "Timestamp not supplied"
        if decision and decision.timestamp:
            detail = iso_z(decision.timestamp)
        if decision and decision.notes:
            detail += f" - {decision.notes}"
        data.append(
            [
                Paragraph(escape(finding.investor_id), styles["table_cell"]),
                Paragraph(escape(finding.check_type), styles["table_cell"]),
                Paragraph(escape(finding.human_review_status.value), styles["table_cell"]),
                Paragraph(
                    escape(decision.reviewer_label if decision and decision.reviewer_label else "Not supplied"),
                    styles["table_cell"],
                ),
                Paragraph(escape(detail), styles["table_cell"]),
            ]
        )
    table = Table(data, colWidths=[20 * mm, 35 * mm, 27 * mm, 30 * mm, 62 * mm], repeatRows=1)
    table.setStyle(_grid_table_style())
    return table


def _source_table(snapshot, styles):  # type: ignore[no-untyped-def]
    data = [
        [
            Paragraph("Document", styles["table_header"]),
            Paragraph("Role", styles["table_header"]),
            Paragraph("SHA-256", styles["table_header"]),
            Paragraph("Evidence locator", styles["table_header"]),
        ]
    ]
    evidence_by_document: dict[str, list[str]] = {}
    for item in snapshot.evidence_references:
        evidence_by_document.setdefault(item.document_id, []).append(
            f"{item.evidence_id}: {item.locator}"
        )
    for document in snapshot.source_documents:
        data.append(
            [
                Paragraph(escape(document.filename), styles["table_cell"]),
                Paragraph(escape(document.role), styles["table_cell"]),
                Paragraph(escape(document.sha256 or "Not supplied"), styles["table_cell"]),
                Paragraph(
                    escape(
                        "; ".join(evidence_by_document.get(document.document_id, []))
                        or "No direct evidence reference"
                    ),
                    styles["table_cell"],
                ),
            ]
        )
    table = Table(data, colWidths=[48 * mm, 27 * mm, 55 * mm, 44 * mm], repeatRows=1)
    table.setStyle(_grid_table_style())
    return table


def _calculation_table(snapshot, styles):  # type: ignore[no-untyped-def]
    data = [
        [
            Paragraph("Investor", styles["table_header"]),
            Paragraph("Fee base", styles["table_header"]),
            Paragraph("Annual rate", styles["table_header"]),
            Paragraph("Period factor", styles["table_header"]),
            Paragraph("Expected", styles["table_header"]),
            Paragraph("Reported", styles["table_header"]),
            Paragraph("Difference", styles["table_header"]),
        ]
    ]
    for calculation in snapshot.calculations:
        data.append(
            [
                Paragraph(escape(calculation.investor_id), styles["table_cell"]),
                Paragraph(escape(money_text(calculation.fee_base, calculation.currency)), styles["table_cell"]),
                Paragraph(
                    escape(
                        f"{calculation.annual_rate_fraction:.2%}"
                        if calculation.annual_rate_fraction is not None
                        else "Not supplied"
                    ),
                    styles["table_cell"],
                ),
                Paragraph(
                    escape(
                        f"{calculation.period_factor:g}"
                        if calculation.period_factor is not None
                        else "Not supplied"
                    ),
                    styles["table_cell"],
                ),
                Paragraph(escape(money_text(calculation.expected_value, calculation.currency)), styles["table_cell"]),
                Paragraph(escape(money_text(calculation.reported_value, calculation.currency)), styles["table_cell"]),
                Paragraph(escape(money_text(calculation.difference, calculation.currency)), styles["table_cell"]),
            ]
        )
    table = Table(
        data,
        colWidths=[21 * mm, 27 * mm, 22 * mm, 20 * mm, 28 * mm, 28 * mm, 28 * mm],
        repeatRows=1,
    )
    table.setStyle(_grid_table_style())
    return table


def _grid_table_style() -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, OFF_WHITE]),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, NAVY),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, LIGHT_GREY),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )
