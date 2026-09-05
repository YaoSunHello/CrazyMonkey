# V0 orchestrator handoff

STATUS: MIGRATED AND INTEGRATED

SOURCE WORKSPACES:

- `/Users/leonardaarons-ditson/Desktop/crazymonkey-fullstack-work`
- frontend audits of `origin/Leo`, `origin/leo2`, and `origin/adjust-for-frontend`

SOURCE BRANCH: `codex/fullstack-continuation` plus selectively reviewed frontend work from `Leo`, `leo2`, and `adjust-for-frontend`

CRAZYMONKEY BRANCH: `codex/frontend-on-main`, originally based on `origin/main` at `3884b9a8d312b18bdc6b8d4715bceb5099d78821` and updated through `origin/main` at `62cf6fd6a0276c7a8d8e9b0b4dc004ae32d6bcc6`

FILES MIGRATED:

- BEACON React review workflow and live HTTP adapter under `frontend/`
- the `leo2` Full Pack UI behind `VITE_ENABLE_PACK_WORKSPACE=1` (off by default)
- the standalone historical run viewer under `frontend/run-viewer/`
- canonical ATLAS ingestion/evidence modules under `backend/app/atlas/`
- analyst, challenger, verifier, review service, and BEACON facade under `backend/app/runtime/`
- immutable PDF/XLSX/JSON/EML export and guarded email-preview modules under `backend/app/relay/`
- additive FastAPI router and CORS mounting in `backend/app/main.py`
- focused frontend and backend test coverage

FILES INTENTIONALLY NOT MIGRATED:

- the `leo2` `/api/pack` Python importer/backend
- wholesale commits or history from `retinapeg/YLOOKUP`
- old FundOps code
- divergent full-stack versions or deletions of main's `agent.py`, `cli.py`, `profiles.py`, `emit.py`, `score.py`, `verification/`, `kit/`, run-history code, and legacy tests

DEPENDENCIES ADDED:

- runtime: `pypdf`, `reportlab`, `XlsxWriter==3.2.9`, `jsonschema==4.25.1`
- development/test: `httpx==0.28.1`

TESTS:

- complete combined backend suite: 255 passed plus 10 subtests
- legacy main backend subset: 130 passed
- frontend: 60 tests passed
- frontend TypeScript, ESLint, and production build passed
- visible browser smoke: real backend review, three versioned human decisions, PDF/XLSX/JSON downloads, and draft-only email preview
- generated nine-page PDF rendered and visually inspected
- six-sheet XLSX reconciled, formula-error scan clean, and every rendered sheet inspected

KNOWN ISSUES:

- V0 is the fixed source-linked NAV management-fee workflow. The earlier generic `profile_id` plus `questions[]` interface and browser profile dropdown are not yet implemented.
- active review records are process-local; use one backend worker and expect restart to clear active browser review state. Frozen RELAY snapshots remain on disk.
- scanned image-only PDFs have no OCR fallback.
- real email send remains deliberately disabled in the browser; preview/draft generation works.
- the preserved Full Pack screen requires the intentionally excluded `/api/pack` backend if its feature flag is explicitly enabled.

INTEGRATION NOTES:

- Main's existing `/health`, `/api/profiles`, `/api/profiles/{profile_id}`, CLI, agent, profile, importer, and verification behavior remains present.
- BEACON routes are namespaced under `/api/v1`, the structured runtime under `/api/cases`, and RELAY under `/api/runs` and `/api/relay`; no existing route is replaced.
- Live frontend mode fails closed with `Backend unavailable`; it never silently substitutes fixture answers.
- Generated review outputs are ignored under `outputs/relay/` and are not committed.
