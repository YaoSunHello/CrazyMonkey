# RELAY migration handoff

STATUS: MIGRATED

SOURCE WORKSPACE: `${HOME}/Documents/ChatGPT/YLOOKUP WIN`

SOURCE BRANCH: `feature/relay-outputs` (local unborn branch; no commits and no remote)

DESTINATION REPO: `YaoSunHello/CrazyMonkey`

DESTINATION BRANCH: `Leo`

FILES MIGRATED:

- `backend/app/relay/` - the frozen-snapshot adapter, output models, immutable file store, PDF/XLSX/JSON exporters, RFC 5322 draft creation, guarded email delivery service, API router, and demo entry point.
- `backend/app/schemas/review_export.schema.json` - the public JSON export contract.
- `backend/fixtures/synthetic_review_snapshot.json` - a RELAY output fixture aligned with ATLAS's canonical synthetic expectations.
- `backend/tests/relay/` and `backend/tests/__init__.py` - focused contract, API, traceability, artifact, injection, and email-gate tests.
- `backend/app/main.py` - minimal router and local-development CORS integration.
- `backend/requirements.txt` - only the runtime/test packages required by this component.
- `backend/.env.example` - opt-in SMTP, confirmation, output-directory, and CORS configuration without credentials.
- `docs/handoffs/relay.md` - this bounded migration record.

FILES INTENTIONALLY NOT MIGRATED:

- The old `retinapeg/YLOOKUP` repository, its history, and its application baseline.
- All previous FundOps code and components.
- Source-workspace UI, README, startup, Docker, and orchestration files that were outside this agent's newly authored RELAY component.
- Source `.git` data, `.venv`, `node_modules`, caches, generated output bundles, and temporary visual-QA renders.
- ATLAS ingestion, parsing, analyst, challenger, verifier, and canonical model implementations.
- BEACON frontend files and every unrelated or teammate-owned change already present on `Leo`.

OLD YLOOKUP CODE INCLUDED: NO

FUNDOPS CODE INCLUDED: NO

DEPENDENCIES ADDED:

- `XlsxWriter==3.2.9` for new, non-mutating review workbooks.
- `jsonschema==4.25.1` for public-export validation.
- `httpx==0.28.1` for FastAPI application tests.
- `pytest==9.1.1` for the focused RELAY test suite.
- `reportlab` was already present on `Leo` from ATLAS and is reused for the PDF report.

TESTS:

- `PYTHONPATH=backend PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/python -m pytest -p no:cacheprovider -q backend/tests/relay` - PASS: 58 tests.
- `PYTHONPATH=backend PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/python -m pytest -p no:cacheprovider -q backend/tests` - PASS: 132 tests and 106 subtests on the final integrated worktree.
- `npm test -- --configLoader runner` from `frontend/` - PASS: 6 files and 12 tests.
- `npm run build -- --configLoader runner --outDir <temporary-directory>` from `frontend/` - PASS: TypeScript check and Vite production build.
- A fresh deterministic bundle was generated outside the repository and validated as PDF, XLSX, JSON, and recipient-free EML.
- Every PDF page and every XLSX worksheet was rendered and visually inspected; the workbook inspection found zero formula-error tokens.

KNOWN ISSUES:

- Real email transport is disabled by default. It requires explicit server configuration, an explicitly entered recipient, preview, a signed confirmation token, `confirmed=true`, literal `action=SEND`, and an idempotency key.
- The demo gate protects deliberate sends within one application process. Production deployment still needs authenticated-user/CSRF controls and persistent cross-worker token/idempotency storage before SMTP should be enabled.
- SMTP/provider acceptance is recorded as acceptance only; it is not represented as inbox delivery.
- The compatibility BEACON draft endpoint is display-only and recipient-free. The legacy BEACON send DTO is rejected because it cannot carry RELAY's required version, recipient, token, deliberate action, and idempotency fields.
- The checked-in output fixture explicitly lacks document hashes because it is not a live ATLAS run. Real ATLAS `ReviewSnapshot` inputs retain their supplied document hashes and `SourceRef` traceability through every export.

INTEGRATION NOTES:

- RELAY validates and adapts `app.atlas.models.ReviewSnapshot` with `contract_version=1`; it does not ingest documents or duplicate ATLAS evidence parsing.
- PDF, XLSX, JSON, and EML are derived from one frozen `(run_id, version, snapshot_sha256)` identity. Export does not rerun analysis or calculations.
- Primary routes are under `/api/runs/{run_id}` for snapshot freezing, deterministic export generation/download, recipient-free draft creation, recipient-bound preview, and explicitly confirmed send.
- BEACON-compatible downloads are exposed under `/api/v1/reviews/{run_id}/exports/{pdf|excel|json}` and resolve the latest frozen version while returning immutable version/hash headers.
- Each discrepancy carries its ATLAS evidence IDs into the report, workbook, JSON, and attached draft artifacts; source locators and hashes are retained where supplied.
- Use `PYTHONPATH=backend python -m app.relay.demo` to generate a local synthetic artifact bundle. Runtime outputs remain ignored by Git.
