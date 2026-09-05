from __future__ import annotations

import json
from pathlib import Path

from .export_service import default_export_service


def main() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    fixture = backend_root / "fixtures" / "synthetic_review_snapshot.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    service = default_export_service()
    frozen = service.snapshot_store.freeze(payload, route_run_id=payload["run_id"])
    bundle = service.generate_all(frozen)
    print(json.dumps(bundle.response(), indent=2))


if __name__ == "__main__":
    main()
