from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .email_delivery import write_eml_draft
from .json_export import write_json_export
from .pdf_export import write_pdf_report
from .snapshot_store import FileSnapshotStore, FrozenSnapshot
from .utils import file_sha256, iso_z, period_slug, utc_now
from .xlsx_export import write_xlsx_report


class ExportError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArtifactDescriptor:
    artifact_type: str
    filename: str
    content_type: str
    sha256: str
    size_bytes: int
    download_url: str


@dataclass(frozen=True)
class ExportBundle:
    run_id: str
    version: int
    snapshot_sha256: str
    generated_at: str
    directory: Path
    artifacts: tuple[ArtifactDescriptor, ...]
    email_draft: dict[str, Any]

    def artifact(self, artifact_type: str) -> ArtifactDescriptor:
        aliases = {"excel": "xlsx"}
        wanted = aliases.get(artifact_type, artifact_type)
        for artifact in self.artifacts:
            if artifact.artifact_type == wanted:
                return artifact
        raise ExportError(f"artifact type {artifact_type!r} is not present")

    def artifact_path(self, artifact_type: str) -> Path:
        return self.directory / self.artifact(artifact_type).filename

    def response(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "version": self.version,
            "snapshot_sha256": self.snapshot_sha256,
            "generated_at": self.generated_at,
            "artifacts": [asdict(artifact) for artifact in self.artifacts],
            "email_draft": self.email_draft,
        }


class ExportService:
    def __init__(self, output_root: Path, schema_path: Path):
        self.output_root = output_root
        self.schema_path = schema_path
        self.snapshot_store = FileSnapshotStore(output_root / "snapshots")
        self.artifact_root = output_root / "artifacts"

    def generate_all(self, frozen: FrozenSnapshot) -> ExportBundle:
        snapshot = frozen.snapshot
        target = (
            self.artifact_root
            / snapshot.run_id
            / f"v{snapshot.version}"
            / frozen.snapshot_sha256
        )
        if target.exists():
            return self._load_bundle(target, expected=frozen)

        version_dir = target.parent
        version_dir.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".relay-build-", dir=version_dir))
        try:
            generated_at = utc_now()
            slug = period_slug(snapshot.reporting_period)
            base_name = f"CrazyMonkey_NAV_Review_{slug}"
            json_path = temporary / f"{base_name}.json"
            pdf_path = temporary / f"{base_name}.pdf"
            xlsx_path = temporary / f"{base_name}.xlsx"
            eml_path = temporary / f"{base_name}.eml"

            public_export = write_json_export(
                json_path,
                frozen,
                generated_at,
                self.schema_path,
            )
            write_pdf_report(pdf_path, frozen, generated_at)
            write_xlsx_report(xlsx_path, frozen, generated_at, public_export)
            email_draft = write_eml_draft(
                eml_path,
                frozen,
                generated_at,
                [pdf_path, xlsx_path, json_path],
            )

            artifact_paths = {
                "pdf": (pdf_path, "application/pdf"),
                "xlsx": (
                    xlsx_path,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "json": (json_path, "application/json"),
                "eml": (eml_path, "message/rfc822"),
            }
            artifacts = tuple(
                ArtifactDescriptor(
                    artifact_type=artifact_type,
                    filename=path.name,
                    content_type=content_type,
                    sha256=file_sha256(path),
                    size_bytes=path.stat().st_size,
                    download_url=(
                        f"/api/runs/{snapshot.run_id}/versions/{snapshot.version}/exports/"
                        f"{artifact_type}?snapshot_sha256={frozen.snapshot_sha256}"
                    ),
                )
                for artifact_type, (path, content_type) in artifact_paths.items()
            )
            manifest = {
                "run_id": snapshot.run_id,
                "version": snapshot.version,
                "snapshot_sha256": frozen.snapshot_sha256,
                "generated_at": iso_z(generated_at),
                "artifacts": [asdict(artifact) for artifact in artifacts],
                "email_draft": email_draft,
                "status": "ARTIFACT_BUNDLE_COMPLETE",
            }
            manifest_path = temporary / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            for artifact in artifacts:
                path = temporary / artifact.filename
                if not path.is_file() or file_sha256(path) != artifact.sha256:
                    raise ExportError(f"artifact verification failed: {artifact.filename}")

            try:
                os.rename(temporary, target)
            except FileExistsError:
                shutil.rmtree(temporary)
            return self._load_bundle(target, expected=frozen)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise

    def get_or_generate(self, run_id: str, version: int) -> ExportBundle:
        return self.generate_all(self.snapshot_store.get(run_id, version))

    def _load_bundle(self, directory: Path, expected: FrozenSnapshot) -> ExportBundle:
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            raise ExportError("artifact directory exists without a complete manifest")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        identity = (
            manifest.get("run_id"),
            manifest.get("version"),
            manifest.get("snapshot_sha256"),
        )
        if identity != expected.identity:
            raise ExportError("artifact manifest does not match the frozen snapshot")
        if manifest.get("status") != "ARTIFACT_BUNDLE_COMPLETE":
            raise ExportError("artifact bundle is not complete")
        artifacts = tuple(ArtifactDescriptor(**item) for item in manifest["artifacts"])
        for artifact in artifacts:
            path = directory / artifact.filename
            if (
                not path.is_file()
                or path.stat().st_size != artifact.size_bytes
                or file_sha256(path) != artifact.sha256
            ):
                raise ExportError(f"cached artifact failed integrity check: {artifact.filename}")
        return ExportBundle(
            run_id=expected.snapshot.run_id,
            version=expected.snapshot.version,
            snapshot_sha256=expected.snapshot_sha256,
            generated_at=manifest["generated_at"],
            directory=directory,
            artifacts=artifacts,
            email_draft=manifest["email_draft"],
        )


def default_export_service() -> ExportService:
    repository_root = Path(__file__).resolve().parents[3]
    output_root = Path(os.getenv("CRAZYMONKEY_RELAY_OUTPUT_DIR", repository_root / "outputs" / "relay"))
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "review_export.schema.json"
    return ExportService(output_root=output_root, schema_path=schema_path)
