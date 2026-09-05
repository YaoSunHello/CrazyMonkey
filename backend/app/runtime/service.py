"""Small single-process demo service; RELAY owns immutable exported snapshots."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from app.atlas.models import NormalizedDocument, ReviewDecision, ReviewSnapshot

from .models import PipelineResult
from .pipeline import run_case, validate_case_id
from .snapshot import to_snapshot


@dataclass
class ReviewRecord:
    result: PipelineResult
    snapshot: ReviewSnapshot
    documents: list[NormalizedDocument]
    user_instruction: str


class ReviewService:
    """In-memory review UI state with copied reads and serialized human updates.

    Intended for one local demo worker. Frozen RELAY versions/artifacts persist
    on disk. No production auth or distributed coordination is implied.
    """
    def __init__(self, export_service=None, analyst=None):
        self._records = {}
        self._aliases = {}
        self._lock = RLock()
        self._export_service = export_service
        self.analyst = analyst

    @property
    def exports(self):
        if self._export_service is None:
            from app.relay.api import service
            return service
        return self._export_service

    def create(self, case_id, user_instruction, documents, synthetic=False):
        validate_case_id(case_id)
        result = run_case(case_id, user_instruction, documents, analyst=self.analyst)
        snapshot = to_snapshot(result, documents, synthetic=synthetic)
        self.exports.snapshot_store.freeze(snapshot.model_dump(mode="json"), route_run_id=result.run_id)
        record = ReviewRecord(result, snapshot, deepcopy(documents), user_instruction)
        with self._lock:
            self._records[result.run_id] = deepcopy(record)
            self._aliases[case_id] = result.run_id
        return deepcopy(record)

    def get(self, case_id_or_run_id):
        with self._lock:
            run_id = self._aliases.get(case_id_or_run_id, case_id_or_run_id)
            if run_id not in self._records:
                raise KeyError(case_id_or_run_id)
            return deepcopy(self._records[run_id])

    def review(self, case_id_or_run_id, finding_id, action, reviewer_label, note):
        decision = ReviewDecision(finding_id=finding_id, action=action, reviewer_label=reviewer_label, note=note)
        with self._lock:
            record = self.get(case_id_or_run_id)
            raw = record.snapshot.model_dump(mode="json")
            finding = next((f for f in raw["findings"] if f["finding_id"] == finding_id), None)
            if finding is None:
                raise KeyError(finding_id)
            previous = finding["human_review_state"]
            now = datetime.now(timezone.utc).isoformat()
            version = raw["version"] + 1
            raw.update(version=version, frozen_at=now, summary=None)
            finding.update(human_review_state=decision.action, reviewer_label=decision.reviewer_label,
                           reviewer_note=decision.note, reviewed_at=now)
            # Existing export contract treats audit events as records in this snapshot version.
            # Older immutable snapshots retain their original event versions unchanged.
            for event in raw["audit_trail"]:
                event["run_version"] = version
            raw["audit_trail"].append({
                "event_id": f"review-{uuid4().hex}", "run_id": raw["run_id"], "run_version": version,
                "finding_id": finding_id, "action": decision.action, "reviewer_label": decision.reviewer_label,
                "timestamp": now, "note": decision.note, "previous_review_state": previous,
                "new_review_state": decision.action, "affected_artifact_ids": [],
            })
            updated = ReviewSnapshot.model_validate(raw)
            self.exports.snapshot_store.freeze(updated.model_dump(mode="json"), route_run_id=updated.run_id)
            record.snapshot = updated
            self._records[updated.run_id] = deepcopy(record)
            return deepcopy(record)


reviews = ReviewService()
