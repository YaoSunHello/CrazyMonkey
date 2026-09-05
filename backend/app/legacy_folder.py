"""Iterate files through the original ATLAS and V0 runtime in isolated processes.

The iterator preserves original limits and records unsupported inputs explicitly.
OFFLINE means the original DEMO_FIXTURE analyst, never a live model result.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import signal
import subprocess
import sys
from time import perf_counter
from uuid import uuid4
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from .atlas import IngestionError, normalize_file
from .atlas import ingestion as atlas_ingestion
from .runtime.pipeline import run_case


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INSTRUCTION = (
    "Review this source with the original management-fee runtime. Preserve source citations, "
    "report missing governing evidence explicitly, and do not infer missing financial values."
)
MODES = {"OFFLINE", "LIVE_MODEL"}
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
COORDINATE = re.compile(r"([A-Z]+)([1-9][0-9]*)\Z")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _no_symlinks(path):
    path = Path(path).absolute()
    if any(candidate.is_symlink() for candidate in (path, *path.parents)):
        raise ValueError("Symlink paths are not supported")
    return path


def enumerate_files(input_dir):
    """Visit all nonhidden entries without following directory or file symlinks."""
    root = _no_symlinks(input_dir)
    if not root.is_dir():
        raise ValueError("--input must be an existing directory")
    found = []
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                if entry.name.startswith("."):
                    continue
                path = Path(entry.path)
                if entry.is_symlink():
                    found.append({"relative_path": path.relative_to(root).as_posix(), "is_symlink": True})
                elif entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False):
                    found.append({"relative_path": path.relative_to(root).as_posix(), "is_symlink": False})
    return sorted(found, key=lambda item: item["relative_path"])


def _column_number(letters):
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter) - ord("A") + 1
    return number


def _xlsx_preflight(path):
    """Use original ZIP limits, then stream XML before openpyxl materialization."""
    data = path.read_bytes()
    atlas_ingestion._inspect_xlsx_zip(path, data)
    del data
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        links = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {item.attrib["Id"]: item.attrib.get("Target") for item in links
                   if item.attrib.get("TargetMode") != "External"}
        strings = bytearray()
        if "xl/sharedStrings.xml" in archive.namelist():
            with archive.open("xl/sharedStrings.xml") as stream:
                for _, element in ET.iterparse(stream, events=("end",)):
                    if element.tag == NS + "si":
                        strings.append(bool("".join(t.text or "" for t in element.iter(NS + "t")).strip()))
                        element.clear()
        summaries = []
        total_cells = total_grid = 0
        for sheet in workbook.findall(NS + "sheets/" + NS + "sheet"):
            target = targets.get(sheet.attrib[REL + "id"])
            if not target:
                raise IngestionError("XLSX_PARSE_FAILED", "Workbook sheet relationship is missing")
            target = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            if ".." in Path(target).parts:
                raise IngestionError("UNSAFE_XLSX_PACKAGE", "Unsafe worksheet relationship")
            rows = columns = count = current_row = current_column = 0
            with archive.open(target) as stream:
                for event, element in ET.iterparse(stream, events=("start", "end")):
                    if event == "start" and element.tag == NS + "row":
                        current_row = int(element.get("r", current_row + 1))
                        current_column = 0
                    if event != "end":
                        continue
                    if element.tag == NS + "c":
                        address = element.get("r")
                        if address:
                            match = COORDINATE.fullmatch(address)
                            if match is None:
                                raise IngestionError("XLSX_PARSE_FAILED", "Invalid worksheet cell coordinate")
                            column, row = _column_number(match[1]), int(match[2])
                        else:
                            column, row = current_column + 1, current_row
                        current_column = column
                        rows, columns = max(rows, row), max(columns, column)
                        raw = element.findtext(NS + "v")
                        kind = element.get("t")
                        if element.find(NS + "f") is not None:
                            nonempty = True
                        elif kind == "s" and raw is not None:
                            index = int(raw)
                            if not 0 <= index < len(strings):
                                raise IngestionError("XLSX_PARSE_FAILED", "Invalid shared string index")
                            nonempty = bool(strings[index])
                        elif kind == "inlineStr":
                            nonempty = bool("".join(t.text or "" for t in element.iter(NS + "t")).strip())
                        else:
                            nonempty = raw is not None and bool(raw.strip())
                        count += nonempty
                        element.clear()
                    elif element.tag == NS + "row":
                        element.clear()
            if rows > atlas_ingestion.MAX_WORKBOOK_ROWS or columns > atlas_ingestion.MAX_WORKBOOK_COLUMNS:
                raise IngestionError("WORKSHEET_DIMENSION_LIMIT", f"Sheet {sheet.attrib['name']!r} exceeds the original worksheet dimension limit")
            total_grid += rows * columns
            if total_grid > atlas_ingestion.MAX_WORKBOOK_GRID_CELLS:
                raise IngestionError("WORKBOOK_GRID_LIMIT", "Workbook exceeds the original worksheet scan cell limit")
            total_cells += count
            if total_cells > atlas_ingestion.MAX_NONEMPTY_CELLS:
                raise IngestionError("WORKBOOK_CELL_LIMIT", "Workbook exceeds the original non-empty cell limit")
            summaries.append({"name": sheet.attrib["name"], "max_row": rows, "max_column": columns, "nonempty_cells": count})
        return {"status": "PASSED", "method": "original_zip_limits_and_streamed_xml",
                "sheets": summaries, "nonempty_cells": total_cells, "grid_cells": total_grid}


def preflight_file(path):
    path = _no_symlinks(path)
    if not path.is_file():
        raise IngestionError("FILE_NOT_FOUND", "Source file does not exist")
    size = path.stat().st_size
    if size > atlas_ingestion.MAX_FILE_BYTES:
        raise IngestionError("FILE_TOO_LARGE", "Source exceeds the original 25 MiB file limit")
    if not size:
        raise IngestionError("EMPTY_FILE", "Source file is empty")
    if path.suffix.lower() != ".xlsx":
        return {"status": "PASSED", "method": "file_size_only_original_normalizer_handles_format"}
    try:
        return _xlsx_preflight(path)
    except IngestionError:
        raise
    except Exception as exc:
        raise IngestionError("XLSX_PARSE_FAILED", "XLSX preflight could not parse the package") from exc


def _create_analyst(mode):
    from .legacy_model import create_analyst
    return create_analyst(mode)


def _empty_artifacts(directory):
    for filename, value in (("normalized_evidence.json", None), ("runtime_result.json", None),
                            ("trace.json", []), ("model_calls.json", [])):
        if not (directory / filename).exists():
            _write_json(directory / filename, value)


def process_file(source, output_dir, *, relative_path, mode="OFFLINE", instruction=DEFAULT_INSTRUCTION):
    """Worker entry: persist originals' evidence and original runtime outcome."""
    if mode not in MODES:
        raise ValueError("mode must be OFFLINE or LIVE_MODEL")
    source = _no_symlinks(source)
    directory = _no_symlinks(output_dir)
    directory.mkdir(parents=True, exist_ok=False)
    _empty_artifacts(directory)
    started = perf_counter()
    before = after = None
    handle = None
    result = {"relative_path": relative_path, "source_path": str(source), "mode": mode,
              "scope": "SINGLE_FILE_COMPATIBILITY_TEST",
              "actual_analyst_mode": "DEMO_FIXTURE" if mode == "OFFLINE" else "MODEL",
              "status": "RUNNING", "stage": "SOURCE_INTEGRITY", "started_at": _now(),
              "runtime_status": None, "evidence_count": 0, "model_call_count": 0}
    try:
        before = _sha(source)
        _write_json(directory / "source_hashes.json", {"before": before, "after": None, "unchanged": None})
        result["stage"] = "PREFLIGHT"
        result["preflight"] = preflight_file(source)
        result["stage"] = "NORMALIZATION"
        normalized = normalize_file(source, original_storage_key=str(source))
        result["normalization_status"] = normalized.document.extraction_status
        result["normalization_warnings"] = normalized.document.warnings
        result["document_role"] = normalized.document.role
        result["evidence_count"] = len(normalized.evidence)
        if normalized.document.document_hash != before:
            raise ValueError("Source changed between hashing and normalization")
        # Full original normalized evidence, without model excerpts or caps.
        (directory / "normalized_evidence.json").write_text(normalized.model_dump_json(indent=2) + "\n", encoding="utf-8")
        result["stage"] = "MODEL_CONFIGURATION"
        handle = _create_analyst(mode)
        result["stage"] = "RUNTIME"
        runtime = run_case("legacy-file-" + uuid4().hex[:16], instruction, [normalized], analyst=handle.analyst)
        (directory / "runtime_result.json").write_text(runtime.model_dump_json(indent=2) + "\n", encoding="utf-8")
        _write_json(directory / "trace.json", [event.model_dump(mode="json") for event in runtime.trace])
        result["runtime_status"] = runtime.status
        result["actual_analyst_mode"] = runtime.mode
        result["finding_count"] = len(runtime.findings)
        result["status"] = "RUNTIME_" + runtime.status
        if not runtime.findings and runtime.status == "PASS":
            result["status"] = "INVALID_EMPTY_PASS"
        result["stage"] = "COMPLETE"
    except IngestionError as exc:
        result["status"] = "INGESTION_UNSUPPORTED" if exc.code == "UNSUPPORTED_FORMAT" else "INGESTION_REJECTED"
        result["error"] = {"code": exc.code, "message": exc.message}
        if result["stage"] == "PREFLIGHT":
            result["preflight"] = {"status": "REJECTED", "error_code": exc.code}
    except Exception as exc:
        result["status"] = "MODEL_FAILED" if result["stage"] == "MODEL_CONFIGURATION" else "FAILED"
        # Provider errors can contain credentials; persist type and fixed text only.
        result["error"] = {"code": type(exc).__name__, "message": "The original layer could not complete this file; see the recorded stage."}
    finally:
        if handle is not None:
            try:
                status = handle.status()
                result["model_status"] = status
                result["model_call_count"] = status.get("model_call_count", 0)
                _write_json(directory / "model_calls.json", handle.calls)
                if status.get("error_count", 0):
                    result["status"] = "MODEL_FAILED"
                    result["error"] = {"code": status.get("last_error_code") or "MODEL_CALLBACK_FAILED", "message": "A model or structured-response failure occurred; there was no offline fallback."}
                elif mode == "LIVE_MODEL" and result["runtime_status"] is not None and not result["model_call_count"]:
                    result["status"] = "MODEL_FAILED"
                    result["error"] = {"code": "NO_RECORDED_MODEL_CALL", "message": "LIVE_MODEL did not record a model call."}
            except Exception:
                result["status"] = "MODEL_FAILED"
                result["error"] = {"code": "MODEL_STATUS_FAILED", "message": "Could not verify model-call metadata."}
            finally:
                try:
                    handle.close()
                except Exception:
                    result["status"] = "MODEL_FAILED"
        try:
            after = _sha(_no_symlinks(source))
        except (OSError, ValueError):
            after = None
        unchanged = before is not None and before == after
        if not unchanged:
            result["status"] = "SOURCE_CHANGED"
            result["stage"] = "SOURCE_INTEGRITY"
            result["error"] = {"code": "SOURCE_CHANGED", "message": "Source hashes before and after processing do not match."}
        _write_json(directory / "source_hashes.json", {"before": before, "after": after, "unchanged": unchanged})
        result.update(source_sha256_before=before, source_sha256_after=after, source_unchanged=unchanged,
                      duration_seconds=round(perf_counter() - started, 6), finished_at=_now())
        _write_json(directory / "file_result.json", result)
    return result


def _terminate_process(process):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=3)


def _run_worker(source, directory, relative_path, mode, timeout, instruction):
    command = [sys.executable, "-m", "app.legacy_folder", "--worker", "--source", str(source),
               "--file-output", str(directory), "--relative-path", relative_path, "--mode", mode,
               "--instruction", instruction]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPOSITORY_ROOT / "backend")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.Popen(command, cwd=REPOSITORY_ROOT, env=environment,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        return {"timed_out": False, "returncode": process.wait(timeout=timeout)}
    except subprocess.TimeoutExpired:
        _terminate_process(process)
        return {"timed_out": True, "returncode": process.returncode}
    except BaseException:
        _terminate_process(process)
        raise


def _summary(manifest):
    files = manifest["files"]
    counts = dict(Counter(item["status"] for item in files))
    terminal = [item for item in files if item["selected"] and item["status"] not in {"PENDING", "RUNNING"}]
    return {"iterator_status": manifest["iterator_status"], "mode": manifest["mode"],
            "scope": "SINGLE_FILE_COMPATIBILITY_TEST",
            "analyst_mode": "DEMO_FIXTURE" if manifest["mode"] == "OFFLINE" else "MODEL",
            "input_root": manifest["input_root"], "output_directory": manifest["output_directory"],
            "discovered_file_count": len(files), "selected_file_count": sum(item["selected"] for item in files),
            "finished_file_count": len(terminal), "status_counts": counts,
            "runtime_pass_count": counts.get("RUNTIME_PASS", 0), "files": files,
            "limitations": ["Iterator completion records attempts, not a successful financial review.",
                            "Each file is reviewed separately using the original V0 management-fee contracts.",
                            "The original NAV review normally needs LPA, investor register and NAV evidence together; a single-file CANNOT_VERIFY can mean missing related context, not corrupt input.",
                            "Missing cross-file governing evidence is not invented; original ingestion limits are unchanged.",
                            "OFFLINE uses the original DEMO_FIXTURE analyst; no model call or full NAV certification is implied."]}


def run_folder(input_dir, output_dir=None, *, patterns=None, mode="OFFLINE", timeout=120,
               instruction=DEFAULT_INSTRUCTION, progress=print):
    if mode not in MODES:
        raise ValueError("mode must be OFFLINE or LIVE_MODEL")
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= 86400:
        raise ValueError("timeout must be positive and no more than 86400 seconds")
    if not instruction.strip() or len(instruction) > 10000:
        raise ValueError("instruction must contain 1..10000 characters")
    source_root = _no_symlinks(input_dir).resolve()
    entries = enumerate_files(source_root)
    target = _no_symlinks(output_dir or (REPOSITORY_ROOT / "outputs/legacy-folder" /
                         (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:10]))).resolve()
    if target.exists():
        raise ValueError("Output directory must be new; existing outputs are never overwritten")
    if target == source_root or target.is_relative_to(source_root) or source_root.is_relative_to(target):
        raise ValueError("Output directory must not overlap the input directory")
    target.mkdir(parents=True, exist_ok=False)
    (target / "files").mkdir()
    selected_patterns = list(patterns or [])
    for index, entry in enumerate(entries, 1):
        entry["selected"] = not selected_patterns or any(fnmatch.fnmatchcase(entry["relative_path"], pattern) for pattern in selected_patterns)
        entry["status"] = "PENDING" if entry["selected"] else "SKIPPED_FILTER"
        entry["file_output"] = f"files/{index:04d}" if entry["selected"] else None
    manifest = {"schema_version": 1, "iterator_status": "RUNNING", "created_at": _now(), "mode": mode,
                "scope": "SINGLE_FILE_COMPATIBILITY_TEST",
                "input_root": str(source_root), "output_directory": str(target), "patterns": selected_patterns,
                "per_file_timeout_seconds": timeout, "files": entries}
    def persist():
        _write_json(target / "manifest.json", manifest)
        _write_json(target / "result.json", _summary(manifest))
    persist()
    for index, entry in enumerate(entries, 1):
        if not entry["selected"]:
            continue
        source = source_root / entry["relative_path"]
        directory = target / entry["file_output"]
        entry["status"] = "RUNNING"
        persist()
        if progress:
            progress(f"[{index}/{len(entries)}] {entry['relative_path']}: RUNNING")
        started = perf_counter()
        metadata = {"relative_path": entry["relative_path"], "mode": mode, "source_path": str(source),
                    "scope": "SINGLE_FILE_COMPATIBILITY_TEST"}
        parent_before = None
        try:
            if entry["is_symlink"]:
                metadata.update(status="PATH_REJECTED", stage="SOURCE_INTEGRITY", error={"code": "SYMLINK_REJECTED", "message": "Symlinks are not followed."})
            else:
                parent_before = _sha(_no_symlinks(source))
                execution = _run_worker(source, directory, entry["relative_path"], mode, timeout, instruction)
                result_file = directory / "file_result.json"
                if execution["timed_out"]:
                    metadata.update(status="TIMED_OUT", stage="WORKER", error={"code": "FILE_TIMEOUT", "message": "The isolated worker exceeded its per-file timeout and was stopped."})
                elif execution["returncode"] != 0 or not result_file.is_file():
                    metadata.update(status="WORKER_FAILED", stage="WORKER", error={"code": "WORKER_EXIT", "message": "The worker ended without a complete file result."})
                else:
                    metadata = json.loads(result_file.read_text(encoding="utf-8"))
                    if metadata.get("relative_path") != entry["relative_path"] or metadata.get("mode") != mode:
                        raise ValueError("Worker result does not match the selected file")
                    if metadata.get("source_sha256_before") != parent_before:
                        metadata.update(status="SOURCE_CHANGED", stage="SOURCE_INTEGRITY",
                                        error={"code": "SOURCE_CHANGED", "message": "Source changed before the worker began."})
                        _write_json(result_file, metadata)
        except Exception as exc:
            metadata.update(status="WORKER_FAILED", stage="WORKER", error={"code": type(exc).__name__, "message": "Could not complete the isolated worker."})
        if metadata["status"] in {"TIMED_OUT", "WORKER_FAILED", "PATH_REJECTED"}:
            directory.mkdir(parents=True, exist_ok=True)
            _empty_artifacts(directory)
            hashes_path = directory / "source_hashes.json"
            hashes = {"before": parent_before}
            try:
                after = _sha(_no_symlinks(source)) if not entry["is_symlink"] else None
            except (OSError, ValueError):
                after = None
            hashes.update(after=after, unchanged=hashes.get("before") is not None and hashes.get("before") == after)
            _write_json(hashes_path, hashes)
            metadata.update(source_sha256_before=hashes.get("before"), source_sha256_after=after,
                            source_unchanged=hashes["unchanged"], duration_seconds=round(perf_counter() - started, 6))
            _write_json(directory / "file_result.json", metadata)
        entry.update(status=metadata["status"], stage=metadata.get("stage"), runtime_status=metadata.get("runtime_status"),
                     evidence_count=metadata.get("evidence_count", 0), source_unchanged=metadata.get("source_unchanged"),
                     model_call_count=metadata.get("model_call_count", 0), error=metadata.get("error"),
                     duration_seconds=metadata.get("duration_seconds"))
        persist()
        if progress:
            progress(f"[{index}/{len(entries)}] {entry['relative_path']}: {entry['status']}")
    manifest.update(iterator_status="COMPLETED", finished_at=_now())
    persist()
    return _summary(manifest)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--match", action="append", default=[])
    parser.add_argument("--mode", choices=sorted(MODES), default="OFFLINE")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--instruction", default=DEFAULT_INSTRUCTION)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--source", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--file-output", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--relative-path", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        if not args.source or not args.file_output or not args.relative_path:
            parser.error("Worker source, output and relative path are required")
        process_file(args.source, args.file_output, relative_path=args.relative_path, mode=args.mode, instruction=args.instruction)
        return 0
    if args.input is None:
        parser.error("--input is required")
    try:
        result = run_folder(args.input, args.output, patterns=args.match, mode=args.mode,
                            timeout=args.timeout, instruction=args.instruction)
    except (ValueError, OSError):
        parser.error("Input/output path or configuration is invalid; input must exist and output must be new and separate")
    print(json.dumps({key: result[key] for key in ("iterator_status", "mode", "output_directory", "discovered_file_count", "selected_file_count", "status_counts")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
