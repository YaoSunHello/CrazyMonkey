"""Streaming, source-bound local pack ingestion independent of ATLAS limits.

Every populated spreadsheet row is retained in SQLite. Profiles are explicitly
bounded excerpts, never a claim that a model reviewed the complete workbook.
Financial calculations and instructions found in documents are not executed.
"""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
import sqlite3
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from openpyxl.styles.numbers import BUILTIN_FORMATS
from pypdf import PdfReader


MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_XLSX_EXPANDED_BYTES = 300 * 1024 * 1024
MAX_ROWS_PER_SHEET = 200_000
MAX_CELLS_PER_FILE = 4_000_000
MAX_SHEETS = 128
MAX_PDF_PAGES = 2_000
MAX_PROFILE_BYTES = 70_000
MAX_TEXT_CHUNK_CHARS = 12_000
MAX_CELL_CHARS = 1_000_000
_CELL = re.compile(r"^([A-Z]{1,3})([1-9][0-9]*)$")
_FLAGS = {"review", "needs review", "requires review", "unmatched", "no match", "no project match", "missing mapping", "suspense"}


def initialize_database(connection: sqlite3.Connection) -> None:
    """Create pack tables without committing a caller-owned transaction."""
    connection.execute("""CREATE TABLE IF NOT EXISTS documents (
        document_id TEXT PRIMARY KEY,
        relative_path TEXT NOT NULL UNIQUE,
        kind TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        profile_json TEXT NOT NULL
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS evidence (
        evidence_id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents(document_id),
        locator TEXT NOT NULL,
        content_json TEXT NOT NULL
    )""")
    connection.execute("CREATE INDEX IF NOT EXISTS evidence_document_id ON evidence(document_id)")


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    read = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            read += len(chunk)
            if read > MAX_FILE_BYTES:
                raise ValueError("file exceeds the 25 MiB ingestion limit")
            digest.update(chunk)
    return digest.hexdigest()


def _tag(element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _children(element, name):
    return [child for child in element if _tag(child) == name]


def _child(element, name):
    return next((child for child in element if _tag(child) == name), None)


class _XmlReader:
    """Reject DTD/entity declarations before ElementTree can expand them."""
    def __init__(self, source):
        self.source = source
        self.tail = b""

    def read(self, size=-1):
        data = self.source.read(size)
        combined = self.tail + data
        if b"\x00" in data or b"<!DOCTYPE" in combined.upper() or b"<!ENTITY" in combined.upper():
            raise ValueError("unsupported XML encoding or entity declaration")
        self.tail = combined[-16:]
        return data


def _xml(archive: ZipFile, name: str):
    with archive.open(name) as source:
        return ET.parse(_XmlReader(source)).getroot()


def _part(base: str, target: str) -> str:
    if "\\" in target:
        raise ValueError("invalid XLSX relationship path")
    path = posixpath.normpath(target.lstrip("/") if target.startswith("/")
                             else posixpath.join(posixpath.dirname(base), target))
    if path == ".." or path.startswith("../"):
        raise ValueError("XLSX relationship escapes the archive")
    return path


def _strings(archive, member):
    if member is None:
        return []
    strings = []
    with archive.open(member) as source:
        iterator = ET.iterparse(_XmlReader(source), events=("start", "end"))
        _, root = next(iterator)
        for event, element in iterator:
            if event == "end" and _tag(element) == "si":
                # Rich-text runs are joined in order, preserving their spaces.
                value = "".join(node.text or "" for node in element.iter() if _tag(node) == "t")
                if len(value) > MAX_CELL_CHARS:
                    raise ValueError("spreadsheet string exceeds the supported bound")
                strings.append(value)
                if len(strings) > MAX_CELLS_PER_FILE:
                    raise ValueError("spreadsheet shared-string count exceeds the supported bound")
                element.clear()
                root.clear()
    return strings


def _styles(archive, member):
    if member is None:
        return []
    root = _xml(archive, member)
    custom = {int(node.attrib["numFmtId"]): node.attrib["formatCode"]
              for node in root.iter() if _tag(node) == "numFmt"}
    formats = []
    xfs = _child(root, "cellXfs")
    if xfs is not None:
        for node in xfs:
            number = int(node.attrib.get("numFmtId", "0"))
            formats.append(custom.get(number, BUILTIN_FORMATS.get(number, f"format-id-{number}")))
    return formats


def _cell_value(cell, strings, styles):
    raw_type = cell.attrib.get("t", "n")
    value_node, formula, inline = _child(cell, "v"), _child(cell, "f"), _child(cell, "is")
    raw = value_node.text if value_node is not None else None
    if formula is None and raw is None and inline is None:
        return None
    record = {"type": "number", "original_value": raw if raw is not None else ""}
    if formula is not None:
        record.update(type="formula", original_value="=" + (formula.text or ""),
                      formula=formula.text or "", formula_attributes=dict(formula.attrib),
                      cached_value=raw, cache_status="PRESENT_UNVERIFIED" if raw is not None else "MISSING")
    elif raw_type == "s":
        if raw is None or not re.fullmatch(r"[0-9]+", raw) or int(raw) >= len(strings):
            raise ValueError("unresolved XLSX shared-string index")
        record.update(type="string", original_value=strings[int(raw)])
    elif raw_type == "inlineStr":
        record.update(type="string", original_value="".join(node.text or "" for node in inline.iter() if _tag(node) == "t") if inline is not None else "")
    elif raw_type in {"str", "b", "d", "e"}:
        record["type"] = {"str": "string", "b": "boolean", "d": "date", "e": "error"}[raw_type]
    elif raw_type != "n":
        raise ValueError("unsupported XLSX cell type")
    if len(record["original_value"]) > MAX_CELL_CHARS:
        raise ValueError("spreadsheet cell exceeds the supported text bound")
    if "s" in cell.attrib:
        style_id = int(cell.attrib["s"])
        if not 0 <= style_id < len(styles):
            raise ValueError("unresolved XLSX cell style")
        record["style_id"] = style_id
        if styles[style_id] != "General":
            record["number_format"] = styles[style_id]
    return record


class _EvidenceWriter:
    def __init__(self, connection, document_id):
        self.connection = connection
        self.document_id = document_id
        self.pending = []
        self.count = 0

    def add(self, locator, content):
        encoded = _json(content)
        evidence_id = "packev_" + hashlib.sha256((self.document_id + "\0" + locator).encode()).hexdigest()
        self.pending.append((evidence_id, self.document_id, locator, encoded))
        self.count += 1
        if len(self.pending) >= 200:
            self.flush()
        return evidence_id

    def flush(self):
        if self.pending:
            self.connection.executemany("INSERT INTO evidence(evidence_id,document_id,locator,content_json) VALUES(?,?,?,?)", self.pending)
            self.pending.clear()


def _sample(evidence_id, locator, text):
    # Only the profile excerpt is shortened; complete evidence is already stored.
    limit = 1300
    return {"evidence_id": evidence_id, "locator": locator,
            "text": text[:limit] + ("\n[Excerpt shortened; complete evidence is stored.]" if len(text) > limit else "")}


def _row_text(sheet, row, cells):
    parts = [f"{sheet} — row {row}"]
    length = len(parts[0])
    for coordinate, value in cells.items():
        text = f"{coordinate}: {value['original_value']}"
        parts.append(text[:1500])
        length += len(text)
        if length > 1500:
            break
    return "\n".join(parts)


def _xlsx(path, writer, profile):
    all_samples = []
    try:
        archive = ZipFile(path)
    except BadZipFile as exc:
        raise ValueError("invalid XLSX archive") from exc
    with archive:
        parts = archive.infolist()
        if len(parts) > 10_000 or sum(part.file_size for part in parts) > MAX_XLSX_EXPANDED_BYTES:
            raise ValueError("XLSX exceeds the 300 MiB expanded-size or part-count limit")
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("XLSX contains duplicate archive members")
        workbook_part = "xl/workbook.xml"
        workbook = _xml(archive, workbook_part)
        relationships = _xml(archive, "xl/_rels/workbook.xml.rels")
        targets, strings_part, styles_part = {}, None, None
        for relationship in relationships:
            if relationship.attrib.get("TargetMode") == "External":
                continue
            target = _part(workbook_part, relationship.attrib["Target"])
            targets[relationship.attrib["Id"]] = target
            kind = relationship.attrib.get("Type", "").rsplit("/", 1)[-1]
            if kind == "sharedStrings":
                strings_part = target
            elif kind == "styles":
                styles_part = target
        strings, styles = _strings(archive, strings_part), _styles(archive, styles_part)
        sheets = [node for node in workbook.iter() if _tag(node) == "sheet"]
        if len(sheets) > MAX_SHEETS:
            raise ValueError("workbook exceeds the sheet-count limit")
        seen_names = set()
        cell_records = 0
        for sheet in sheets:
            name = sheet.attrib["name"]
            if name in seen_names:
                raise ValueError("workbook contains duplicate worksheet names")
            seen_names.add(name)
            relationship_id = next((value for key, value in sheet.attrib.items() if key.rsplit("}", 1)[-1] == "id"), None)
            if relationship_id not in targets:
                raise ValueError("worksheet relationship cannot be resolved")
            summary = {"name": name, "rows": 0, "cells": 0, "headers": {},
                       "state": sheet.attrib.get("state", "visible"), "formula_cells": 0,
                       "empty_cell_records": 0, "review_flag_rows": 0, "worksheet_row_records": 0}
            candidates, header_score, last_sample = [], (-1, -1), None
            first_sample, first_data, header_sample = None, None, None
            header_candidates = 0
            flagged = []
            last_row = 0
            with archive.open(targets[relationship_id]) as source:
                iterator = ET.iterparse(_XmlReader(source), events=("start", "end"))
                _, root = next(iterator)
                for event, element in iterator:
                    if event != "end" or _tag(element) != "row":
                        continue
                    row = int(element.attrib.get("r", str(last_row + 1)))
                    if row <= last_row or row > MAX_ROWS_PER_SHEET:
                        raise ValueError("worksheet rows are duplicated, out of order or exceed 200,000")
                    last_row = row
                    summary["worksheet_row_records"] += 1
                    cells, seen_coordinates = {}, set()
                    for cell in _children(element, "c"):
                        cell_records += 1
                        if cell_records > MAX_CELLS_PER_FILE:
                            raise ValueError("workbook exceeds the 4,000,000-cell limit")
                        coordinate = cell.attrib.get("r", "")
                        match = _CELL.fullmatch(coordinate)
                        if match is None or int(match[2]) != row or coordinate in seen_coordinates:
                            raise ValueError("worksheet cell has an invalid or duplicate coordinate")
                        seen_coordinates.add(coordinate)
                        column = 0
                        for letter in match[1]:
                            column = column * 26 + ord(letter) - 64
                        if column > 16_384:
                            raise ValueError("worksheet column exceeds the Excel limit")
                        record = _cell_value(cell, strings, styles)
                        if record is None:
                            summary["empty_cell_records"] += 1
                        else:
                            cells[coordinate] = record
                            summary["formula_cells"] += record["type"] == "formula"
                    if cells:
                        locator = f"{name}!row {row}"
                        evidence_id = writer.add(locator, {"kind": "XLSX_ROW", "sheet": name, "row": row, "cells": cells})
                        summary["rows"] += 1
                        summary["cells"] += len(cells)
                        current = _sample(evidence_id, locator, _row_text(name, row, cells))
                        first_sample = first_sample or current
                        if summary["rows"] == 2:
                            first_data = current
                        last_sample = current
                        if header_candidates < 12:
                            header_candidates += 1
                            strings_in_row = {coordinate: record["original_value"] for coordinate, record in cells.items()
                                              if record["type"] == "string" and record["original_value"].strip()}
                            score = (len(strings_in_row), -len(cells) + len(strings_in_row))
                            if score > header_score:
                                header_score = score
                                summary["headers"] = dict(list(strings_in_row.items())[:256])
                                summary["header_row"] = row
                                summary["header_evidence_id"] = evidence_id
                                summary["headers_omitted"] = max(0, len(strings_in_row) - 256)
                                header_sample = current
                        if any(record["type"] == "string" and record["original_value"].strip().casefold() in _FLAGS
                               for record in cells.values()):
                            summary["review_flag_rows"] += 1
                            if len(flagged) < 3:
                                flagged.append(current)
                    element.clear()
                    root.clear()
            for sample in [header_sample, first_sample, last_sample, *flagged, first_data]:
                if sample is not None and sample["evidence_id"] not in {item["evidence_id"] for item in candidates}:
                    candidates.append(sample)
            header_labels = {}
            for coordinate, label in summary["headers"].items():
                header_labels.setdefault(label, []).append(coordinate)
            summary["duplicate_headers"] = {label: coordinates for label, coordinates in header_labels.items() if len(coordinates) > 1}
            profile["sheets"].append(summary)
            profile["row_count"] += summary["rows"]
            profile["cell_count"] += summary["cells"]
            all_samples.append(candidates)
        profile["expanded_bytes"] = sum(part.file_size for part in parts)
        profile["formula_cells"] = sum(sheet["formula_cells"] for sheet in profile["sheets"])
        profile["review_flag_rows"] = sum(sheet["review_flag_rows"] for sheet in profile["sheets"])
    # Round-robin across sheets preserves representation of later sheets.
    return [samples[index] for index in range(max((len(group) for group in all_samples), default=0))
            for samples in all_samples if index < len(samples)]


def _pdf(path, writer, profile):
    samples = []
    with path.open("rb") as source:
        reader = PdfReader(source)
        if reader.is_encrypted:
            raise ValueError("encrypted PDFs require a separately decrypted source")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ValueError("PDF exceeds the page-count limit")
        for index, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            if len(text) > 2_000_000:
                raise ValueError("PDF page text exceeds the supported bound")
            locator = f"page {index}"
            evidence_id = writer.add(locator, {"kind": "PDF_PAGE", "page": index, "text": text, "extraction": "pypdf_text"})
            profile["page_count"] += 1
            if not text.strip():
                profile["issues"].append({"code": "PDF_PAGE_NO_EXTRACTABLE_TEXT", "locator": locator})
            samples.append(_sample(evidence_id, locator, text))
    if len(samples) > 2:
        samples = [samples[0], samples[-1], *samples[1:-1]]
    return samples


def _text(path, writer, profile):
    text = path.read_text(encoding="utf-8-sig")
    samples = []
    start = 0
    while start < len(text):
        end = min(len(text), start + MAX_TEXT_CHUNK_CHARS)
        if end < len(text):
            boundary = text.rfind("\n\n", start, end)
            if boundary > start:
                end = boundary + 2
        locator = f"characters {start}:{end}"
        excerpt = text[start:end]
        evidence_id = writer.add(locator, {"kind": "TEXT_CHUNK", "text": excerpt,
                                          "text_start": start, "text_end": end})
        profile["row_count"] += 1
        samples.append(_sample(evidence_id, locator, excerpt))
        start = end
    profile["text_char_count"] = len(text)
    if len(samples) > 2:
        samples = [samples[0], samples[-1], *samples[1:-1]]
    return samples


def _bounded_profile(profile, candidates, limit):
    candidate_count = max(profile.get("candidate_sample_count", 0), len(candidates))
    profile["sample_evidence"] = []
    profile["sample_evidence_count"] = 0
    profile["excerpt_limit_bytes"] = limit
    profile["excerpt_truncated"] = False
    profile["candidate_sample_count"] = candidate_count
    profile["issue_count"] = max(profile.get("issue_count", 0), len(profile["issues"]))
    profile["issues"] = profile["issues"][:50]
    profile["coverage"] = "All populated rows/cells or document pages/chunks are stored; this profile is a bounded excerpt, not complete model review."
    # Header labels also remain available in their complete row evidence.
    if len(_json(profile).encode()) > limit:
        for sheet in profile["sheets"]:
            sheet["headers_omitted"] = sheet.get("headers_omitted", 0) + len(sheet["headers"])
            sheet["headers"] = {}
            sheet["duplicate_headers"] = {}
        profile["excerpt_truncated"] = True
    for candidate in candidates:
        profile["sample_evidence"].append(candidate)
        profile["sample_evidence_count"] = len(profile["sample_evidence"])
        if len(_json(profile).encode()) > limit:
            profile["sample_evidence"].pop()
            profile["sample_evidence_count"] = len(profile["sample_evidence"])
            profile["excerpt_truncated"] = True
            continue
    if len(profile["sample_evidence"]) < candidate_count or len(profile["issues"]) < profile["issue_count"]:
        profile["excerpt_truncated"] = True
    if len(_json(profile).encode()) > limit:
        raise ValueError("profile metadata exceeds the configured excerpt limit")
    return profile


def ingest_file(path: Path, relative_path: str, connection: sqlite3.Connection,
                *, profile_excerpt_bytes: int = MAX_PROFILE_BYTES) -> dict:
    """Import one source atomically; retain exact XLSX numeric text in SQLite.

    Re-importing the same path/content is idempotent. A caller may wrap several
    imports in its own transaction. No source file is edited or copied here.
    """
    if not isinstance(relative_path, str) or not relative_path or len(relative_path) > 2048 or "\\" in relative_path or "\x00" in relative_path:
        raise ValueError("relative_path must be a bounded relative POSIX path")
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative_path.split("/")):
        raise ValueError("relative_path must not escape the pack")
    if type(profile_excerpt_bytes) is not int or not 2048 <= profile_excerpt_bytes <= MAX_PROFILE_BYTES:
        raise ValueError("profile excerpt limit must be between 2,048 and 70,000 bytes")
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("source must be a regular non-symlink file")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("file exceeds the 25 MiB ingestion limit")
    kind = {".xlsx": "XLSX", ".pdf": "PDF", ".md": "MARKDOWN", ".txt": "TEXT"}.get(path.suffix.lower())
    if kind is None:
        raise ValueError("supported pack files are XLSX, PDF, MD and TXT")
    sha256 = _sha_file(path)
    document_id = "packdoc_" + hashlib.sha256((relative_path + "\0" + sha256).encode()).hexdigest()
    existing = connection.execute("SELECT profile_json FROM documents WHERE document_id=?", (document_id,)).fetchone()
    if existing is not None:
        profile = json.loads(existing[0])
        return _bounded_profile(profile, list(profile["sample_evidence"]), profile_excerpt_bytes)
    profile = {"document_id": document_id, "relative_path": relative_path, "kind": kind,
               "row_count": 0, "cell_count": 0, "page_count": 0, "sha256": sha256,
               "size_bytes": path.stat().st_size, "sheets": [], "issues": []}
    connection.execute("SAVEPOINT pack_ingest_file")
    try:
        connection.execute("INSERT INTO documents(document_id,relative_path,kind,sha256,profile_json) VALUES(?,?,?,?,?)",
                           (document_id, relative_path, kind, sha256, "{}"))
        writer = _EvidenceWriter(connection, document_id)
        candidates = _xlsx(path, writer, profile) if kind == "XLSX" else _pdf(path, writer, profile) if kind == "PDF" else _text(path, writer, profile)
        writer.flush()
        if _sha_file(path) != sha256:
            raise ValueError("source changed during ingestion")
        profile["evidence_count"] = writer.count
        profile = _bounded_profile(profile, candidates, profile_excerpt_bytes)
        connection.execute("UPDATE documents SET profile_json=? WHERE document_id=?", (_json(profile), document_id))
        connection.execute("RELEASE SAVEPOINT pack_ingest_file")
        return profile
    except Exception:
        connection.execute("ROLLBACK TO SAVEPOINT pack_ingest_file")
        connection.execute("RELEASE SAVEPOINT pack_ingest_file")
        raise
