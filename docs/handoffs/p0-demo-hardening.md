# P0 demo hardening handoff

STATUS: MERGE READY

SOURCE WORKSPACE: `/Users/leonardaarons-ditson/Desktop/crazymonkey-p0-bank-statements`

SOURCE BRANCH: `codex/p0-bank-statement-journey`

CRAZYMONKEY BRANCH: `codex/p0-bank-statement-journey`

BASELINE INTEGRATED: `origin/main` at `e675b20a8449b3344803bada301216f9d52f33e2`

FILES MIGRATED:

- `backend/app/ingestion/statements.py`: safe account fallback for renamed statement PDFs and a supported-layout gate.
- `backend/app/reference/tables.py`: central required-column validation.
- `backend/app/ui_bridge/service.py`: canonical ATLAS normalization, source identity checks, source-linked citations, partial-result handling, and shared profile eligibility.
- `backend/app/ui_bridge/store.py`: ATLAS metadata in job status and results.
- `backend/tests/test_ui_bridge.py`, `backend/tests/test_statement_ingestion.py`, and `backend/tests/test_reference_tables.py`: regression coverage for the backend integration.
- `frontend/src/ProfileWorkspace.tsx` and related adapter, intake, review-desk, type, style, and test files: one-PDF submission, idempotent job creation, job recovery, truthful profile labels, source metadata, processing history, and error handling.
- `scripts/start-v0.sh`: guarded combined backend/frontend launcher with readiness checks and owned-process cleanup.
- Root and frontend README updates documenting the connected live flow and its limits.

FILES INTENTIONALLY NOT MIGRATED:

- The earlier `backend/app/statement_jobs.py` implementation and its tests were removed because `backend/app/ui_bridge` on `main` is the canonical statement-review job API.
- The earlier `StatementWorkspace` frontend and its tests were removed because `ProfileWorkspace` on `main` is the canonical live frontend.
- No YLOOKUP repository baseline, FundOps implementation, generated output, dependency directory, credential, or local environment file is included.

DEPENDENCIES ADDED: None.

TESTS:

- Backend: `314 passed`, plus `10 subtests passed`.
- Frontend: `155 passed`, `2 skipped` opt-in contract tests in the ordinary offline run.
- Live frontend adapter contract: `2 passed` against the running FastAPI backend with the exact sample PDF bytes.
- TypeScript typecheck: passed.
- ESLint: passed with zero warnings.
- Production frontend build: passed.
- Launcher: clean start/stop, restart, child failure, interrupt, and occupied-port scenarios passed on disposable ports without disturbing existing listeners.
- Browser smoke evidence is recorded separately in the final branch report.

KNOWN ISSUES:

- The profile-workflow bridge is deliberately deterministic: it runs ATLAS, the statement parser, and deterministic verification, and reports agent resolution as `NOT_RUN`. It must not be presented as a model-backed classification run.
- Profile job state is process-local, so the V0 should run with one backend worker. Restarting the backend invalidates remembered job IDs; the frontend detects that and returns to intake.
- The supported PDF path targets the supplied text-based Calder statement layout. Unsupported or unreadable PDFs fail visibly instead of producing fixture results.
- The NAV/RELAY workspace remains a separate workflow. RELAY can prepare export artifacts and an email draft; real email sending remains disabled by default.

INTEGRATION NOTES:

- `backend/app/atlas` remains the canonical ingestion and evidence layer. The UI bridge stores the submitted bytes, normalizes each source through ATLAS, and passes only source-linked material into the existing parsers and deterministic verifier.
- The default browser workspace calls the real `/api/ui/v1` FastAPI contract. It does not answer locally and has no silent fixture fallback.
- NAV, BEACON, the verified runtime, and RELAY routes from `main` remain mounted in the same FastAPI application and were not replaced.
- One valid supported PDF is sufficient to enable **Start review**. The optional reference workbook is not required for statement arithmetic and evidence verification.

EXACT RUN:

```bash
cd /Users/leonardaarons-ditson/Desktop/crazymonkey-p0-bank-statements
CRAZYMONKEY_BACKEND_PORT=8030 CRAZYMONKEY_FRONTEND_PORT=4200 ./scripts/start-v0.sh
```

Then open <http://127.0.0.1:4200/>.
