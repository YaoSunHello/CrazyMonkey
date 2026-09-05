"""Read-only views of ATLAS evidence. No synthesized source references."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.atlas.ids import sha256_bytes
from app.atlas.ingestion import MAX_FILE_BYTES
from app.atlas.models import NormalizedDocument, SourceRef
from .contracts import NumericInput

NUMBER = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"


def source_text(ref: SourceRef) -> str:
    return ref.quote if ref.quote is not None else ref.original_value or ""


class EvidenceStore:
    def __init__(self, documents: list[NormalizedDocument]):
        self.documents = []
        self.refs: dict[str, SourceRef] = {}
        self.docs = {}
        for document in documents:
            # Revalidate even caller-supplied mutable ATLAS model objects.
            document = NormalizedDocument.model_validate(document.model_dump())
            if document.document.document_id in self.docs:
                raise ValueError("duplicate normalized document")
            self.docs[document.document.document_id] = document
            self.documents.append(document)
            for ref in document.evidence:
                if ref.evidence_id in self.refs:
                    raise ValueError("duplicate evidence ID")
                self.refs[ref.evidence_id] = ref

    def get(self, evidence_id: str) -> SourceRef:
        if evidence_id not in self.refs:
            raise ValueError(f"unresolved ATLAS evidence ID: {evidence_id}")
        return self.refs[evidence_id]

    def document_text(self, document_id: str) -> str:
        return "\n".join(source_text(ref) for ref in self.docs[document_id].evidence)

    def citation(self, evidence_id: str) -> dict:
        ref = self.get(evidence_id)
        doc = self.docs[ref.document_id].document
        return {"filename": doc.filename, "locator": ref.locator,
                **ref.model_dump(mode="json")}

    def verify_originals(self) -> None:
        for document in self.docs.values():
            path = Path(document.document.original_storage_key)
            if not path.is_file() or path.is_symlink():
                raise ValueError(f"source changed or disappeared: {document.document.filename}")
            with path.open("rb") as source:
                data = source.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES or sha256_bytes(data) != document.document.document_hash:
                raise ValueError(f"source changed or disappeared: {document.document.filename}")

    def model_payload(self) -> dict:
        return {"documents": [{"document": d.document.model_dump(mode="json", exclude={"original_storage_key"}),
                               "evidence": [r.model_dump(mode="json") for r in d.evidence]}
                              for d in self.docs.values()]}

    def number(self, spec: NumericInput) -> Decimal:
        ref = self.get(spec.evidence_id)
        if ref.formula or ref.cache_status != "NOT_APPLICABLE":
            raise ValueError("formula/cached evidence cannot supply a verified numeric input")
        if ref.data_type in ("b", "bool", "boolean", "e", "error"):
            raise ValueError("boolean/error cell is not a financial number")
        raw = source_text(ref).strip()
        token = spec.token
        if token is not None:
            # Prevent selecting 5 from 1.5%, or 10 from an investor identifier.
            # Sentence punctuation may follow a complete number. Decimal/group
            # separators followed by a digit still forbid numeric substring cuts.
            pattern = r"(?<![\w.,+\-−])" + re.escape(token) + r"(?![\w%]|[.,]\d)"
            if not re.search(pattern, raw):
                raise ValueError("numeric token is not an exact bounded source substring")
            if ref.kind != "PDF_TEXT" and token.strip() != raw.strip():
                raise ValueError("cell inputs must use the complete original cell value")
        else:
            token = raw
        cleaned = token.strip()
        negative = cleaned.startswith("(") and cleaned.endswith(")")
        if negative:
            cleaned = cleaned[1:-1].strip()
        cleaned = re.sub(r"^(?:GBP|USD|EUR|£|\$|€)\s*", "", cleaned)
        percent = cleaned.endswith("%")
        if percent:
            if spec.unit != "rate":
                raise ValueError("percent requires a rate input")
            cleaned = cleaned[:-1].strip()
        if not re.fullmatch(NUMBER, cleaned) or len(cleaned) > 40:
            raise ValueError("source is not a supported unambiguous number")
        try:
            value = Decimal(cleaned.replace(",", ""))
            if negative:
                value = -value
            if percent:
                value /= Decimal(100)
        except InvalidOperation as exc:
            raise ValueError("invalid Decimal input") from exc
        if not value.is_finite() or abs(value) > Decimal("1e24"):
            raise ValueError("numeric input exceeds the supported bound")
        if spec.unit == "rate" and not Decimal(0) <= value <= Decimal(1):
            raise ValueError("rate outside 0..1")
        if spec.unit == "factor" and not Decimal(0) < value <= Decimal(1):
            raise ValueError("period factor outside 0..1")
        return value
