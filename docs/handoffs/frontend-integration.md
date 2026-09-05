# Frontend and integration handoff

Date: 5 September 2026

## Delivery state

This integration is being completed on the single branch
`codex/crazymonkey-main-integration-v2`, created directly from live
`origin/main` at `f11d7cc51dbd253c123673e84243f105b81ec55c`. Backend integration was
tested at `7514b2ece8a1f9ba41f1a9e15c13e0d714fda7f5`. The tested application
tip is `5ec2bed0abf08ff64e4216d1872dd97619695eee`; its backend tree is byte-for-byte
unchanged from `7514b2e`. The commit after `5ec2bed` is documentation-only and
records this evidence.

The integration retains every existing workflow while making the assignment's
folder-first journey the default landing:

- the profile-driven folder review is mounted as **Profile workflows** at `/`
  (`/?workspace=profiles` remains a supported alias);
- the current `main` NAV review remains available unchanged at
  `/?workspace=nav` and through the workspace switcher;
- the preserved Full Pack screen remains behind
  `VITE_ENABLE_PACK_WORKSPACE=1`; and
- the deterministic bridge is mounted under `/api/ui/v1` alongside the
  existing `/api/v1`, `/api/cases`, `/api/runs`, and `/api/relay` routers.

No existing backend route is redirected or replaced. `frontend/BEACON.md` is
preserved as the detailed NAV/RELAY description.

Publication must remain a normal, non-force fast-forward from this one branch.
The project owner's later explicit instruction to publish to `main` supersedes
the older `Leo`/no-`main` publication text in the supplied assignment; it does
not relax the safety gate.
Immediately before pushing, refresh `refs/heads/main` explicitly, prove that
the refreshed remote tip is an ancestor of the final documentation-only
successor, and confirm that its application tree matches tested commit
`5ec2bed`. Push the final successor by its exact literal SHA to
`refs/heads/main`. If `main` advances, integrate the new tip and rerun the
checks; do not overwrite it.

## Workspace boundaries

| Workspace | Availability | Purpose | HTTP surface |
| --- | --- | --- | --- |
| **Profile workflows** | Default at `/`; alias `/?workspace=profiles` | Inspect a folder, select a runnable JSON profile, submit a strict manifest plus exact bytes, follow deterministic statement checks, review findings, inspect sources, or open a committed replay | `/health`, `/api/profiles`, `/api/ui/v1` |
| **NAV review** | `/?workspace=nav` or workspace switcher | ATLAS-backed NAV review, versioned human decisions, and RELAY PDF/XLSX/JSON and email-draft workflow | `/api/v1`, `/api/cases`, `/api/runs`, `/api/relay` |
| **Full Pack** | Only with `VITE_ENABLE_PACK_WORKSPACE=1` | Preserved historical whole-pack screen | Requires `/api/pack`, whose backend is intentionally absent |

Workspace state stays isolated. Switching workspaces does not reinterpret a
NAV review as a profile job or route either adapter through the other contract.
The Full Pack feature flag exposes its screen, not a working backend.

## Design rationale from the source material

The workspace design follows the recurring operational constraints in
`samples/03-call-transcripts/call-1-nav-workflow-review.pdf` without inventing
quotes, users, or performance figures:

- repeated review burden becomes a visible inventory, bounded processing
  progress, and exception-led review rather than an opaque loading state;
- numeric reconciliation exposes operands, differences, outcomes, and source
  citations so a reviewer can follow how a result was reached; and
- responsibility stays with the reviewer: human review status is editable,
  while the immutable computational outcome remains separate and unchanged.

## Backend route ownership

The combined FastAPI application mounts four distinct capability families:

| Prefix | Owner | Current capability |
| --- | --- | --- |
| `/api/profiles` | Core profile registry | Discovers every repository profile; this is broader than the subset runnable through the UI bridge |
| `/api/ui/v1` | Profile workflow bridge | Local deterministic PDF statement jobs, optional reference workbook validation, sources, JSON result artifact, human review state, and committed replays |
| `/api/cases` | Verified runtime | Structured V0 case execution and result retrieval |
| `/api/v1` | BEACON plus RELAY compatibility facade | NAV upload/detection, review presentation, versioned human review, supporting-document rerun, export retrieval, and draft preparation |
| `/api/runs`, `/api/relay` | RELAY | Immutable snapshots, PDF/XLSX/JSON exports, version-bound draft/preview, and guarded delivery routes |
| `/api/pack` | Not mounted | Historical Full Pack dependency; deliberately absent |

The shared `backend/app/main.py` retains the existing runtime, BEACON, and
RELAY routers and adds `ui_bridge_router`. Its development CORS policy permits
`GET`, `POST`, `PATCH`, and `OPTIONS`, including `Content-Type`, `If-None-Match`,
and `Idempotency-Key`. CORS is a browser transport policy, not authentication;
the contribution does not add authentication or a production allow-list.

## Profile workflow contract

The production profile adapter centralises these routes:

| Method | Route | Behaviour |
| --- | --- | --- |
| `GET` | `/health` | Process health only; not sufficient by itself to enable a job |
| `GET` | `/api/profiles` | Core profile identities and labels |
| `GET` | `/api/ui/v1/capabilities` | Runnable profile subset, formats, limits, artifact availability, and execution disclosure |
| `POST` | `/api/ui/v1/jobs` | Strict JSON manifest plus positionally matched multipart bytes; requires `Idempotency-Key` |
| `GET` | `/api/ui/v1/jobs/{job_id}` | Processing state, per-document states, and bounded shared trace events |
| `GET` | `/api/ui/v1/jobs/{job_id}/result` | Deterministic results, findings, citations, projection, and artifact links |
| `GET` | `/api/ui/v1/jobs/{job_id}/sources/{source_id}` | Exact stored bytes for an accepted uploaded source |
| `GET` | `/api/ui/v1/jobs/{job_id}/artifacts/{artifact_id}` | Generated artifact bytes |
| `PATCH` | `/api/ui/v1/jobs/{job_id}/findings/{finding_id}/review` | Human review state only; computational status remains unchanged |
| `GET` | `/api/ui/v1/replays` | Summaries of committed recorded results |
| `GET` | `/api/ui/v1/replays/{replay_id}` | Read-only committed replay envelope |

`POST /api/ui/v1/jobs` is `multipart/form-data` with one JSON `manifest` field
and ordered `files` parts. Each file part must match its manifest entry's
position, filename, extension, declared MIME type, signature, and exact byte
count. Reusing an idempotency key with identical content returns the existing
job; using it for changed content returns `409`.

The bridge advertises only profiles it can run locally. The current subset is
`journal-entries` and `pipeline-validation`; the agent-only `mandate-fit`
profile remains discoverable through `/api/profiles` but is not advertised by
`/api/ui/v1/capabilities`.

Exact advertised and enforced limits are:

```text
40 selected files
25 MiB per file
100 MiB per batch
12 nested directories, excluding the filename
100 retained events per job
at least one PDF source
at most one optional XLSX reference
```

Folder discovery retains safe nested browser-relative paths, drains every
directory-entry batch, permits the same leaf filename in different folders,
and rejects duplicate or unsafe relative paths. VCS, dependency, environment,
credential/private-key, cache/build, temporary, unsupported, unreadable, and
oversized inputs are surfaced rather than silently uploaded. Ambiguous
answer/output folders require an explicit user choice. Processing never starts
until the inventory is valid and the user confirms it.

Job events reuse the repository event shape
`{ kind, label, detail, status, body, meta, at }`. The job's
`processing_state` is authoritative for `SUCCEEDED`, `PARTIAL`, or `FAILED`;
presentation status on the final event is not substituted for it. A failed
document can therefore coexist with usable results in a `PARTIAL` job.

## Truth and capability boundaries

Profile workflow jobs are explicitly labelled `LOCAL_DETERMINISTIC`, report
zero model calls, and report that the browser executed no commands. The bridge
uses the core balance verifier's exported operands and outcomes; it does not
implement a second verifier. Resolution and classification are labelled
`NOT_RUN`, and unresolved values stay unresolved rather than being guessed.

Recorded runs are committed result playback, not reruns. They have no event
trace, perform zero model calls, and do not claim idle-time compression.

The profile bridge generates and serves JSON only. Its report/PDF and
workbook/XLSX capabilities are false with explicit reasons. This does not
remove NAV review's separate RELAY PDF, XLSX, and JSON exports. Source links
serve accepted uploaded bytes and preserve page/bounding-box citations, but the
profile UI does not draw an invented highlight or certify a source document.

Profile jobs, review state, sources, artifacts, and idempotency records are
process-local and bounded. There is no durable multi-user job store, user
authentication, production deployment, SSE/WebSocket stream, browser-executed
agent, credential use, sandbox execution, or profile-bridge email operation in
this change.

## Owned paths

Repository and integration documentation:

```text
README.md
docs/handoffs/frontend-integration.md
frontend/BEACON.md
frontend/README.md
```

The integration contribution is limited to these backend paths:

```text
backend/app/main.py
backend/app/ui_bridge/__init__.py
backend/app/ui_bridge/router.py
backend/app/ui_bridge/schemas.py
backend/app/ui_bridge/service.py
backend/app/ui_bridge/store.py
backend/app/verification/checks.py
backend/tests/test_ui_bridge.py
backend/tests/test_verification.py
```

Its frontend paths are:

```text
frontend/index.html
frontend/src/App.integration.test.tsx
frontend/src/App.resilience.test.tsx
frontend/src/App.test.tsx
frontend/src/App.tsx
frontend/src/App.workspace.test.tsx
frontend/src/ProfileWorkspace.tsx
frontend/src/ProfileWorkspace.test.tsx
frontend/src/ProfileWorkspace.integration.test.tsx
frontend/src/ProfileWorkspace.resilience.test.tsx
frontend/src/api/workspaceAdapter.ts
frontend/src/api/workspaceAdapter.test.ts
frontend/src/api/workspaceAdapter.contract.test.ts
frontend/src/components/JobProgress.tsx
frontend/src/components/PackWorkspace.tsx
frontend/src/components/ProfileReviewDesk.tsx
frontend/src/components/ProfileReviewDesk.test.tsx
frontend/src/components/RecordedReplayView.tsx
frontend/src/components/WorkspaceIntake.tsx
frontend/src/main.tsx
frontend/src/profileWorkspace.css
frontend/src/styles.css
frontend/src/test/workspaceFixtures.ts
frontend/src/utils/folderSelection.ts
frontend/src/utils/folderSelection.test.ts
frontend/src/workspaceTypes.ts
frontend/vite.config.ts
```

## Launch commands

From the final repository checkout, install the Python environment and start
the combined backend:

```bash
uv sync
PYTHONPATH=backend uv run python -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8000
```

In another terminal, prefer Vite's same-origin development proxy:

```bash
cd frontend
npm ci
CRAZYMONKEY_BACKEND_ORIGIN=http://127.0.0.1:8000 \
VITE_API_MODE=live VITE_API_BASE_URL=/ \
  npm run dev -- --host 127.0.0.1
```

Open Profile workflows at <http://127.0.0.1:4173/> and NAV at
<http://127.0.0.1:4173/?workspace=nav>. `CRAZYMONKEY_BACKEND_ORIGIN` is a
server-only proxy target; `VITE_API_BASE_URL=/` keeps browser requests on the
frontend origin.

For optional direct cross-origin development, bypass the proxy explicitly:

```bash
cd frontend
VITE_API_MODE=live VITE_API_BASE_URL=http://127.0.0.1:8000 \
  npm run dev -- --host 127.0.0.1
```

The backend defaults permit loopback frontend origins on ports `4173` and
`5173`. For any other origin, set a precise comma-separated
`CRAZYMONKEY_CORS_ORIGINS` value before starting the backend.

## Browser support and manual gap

Current Chrome and Edge are the supported demo browsers for complete folder
selection and drag/drop. The folder picker uses `webkitdirectory` and
`webkitRelativePath`; full folder drag/drop uses the browser entry API. The
Codex in-app browser is Chromium, but Safari and Firefox are not certified by
this handoff.

Automated coverage exercises the visible **Choose folder** control, its real
directory input, nested relative paths, traversal batches, and the upload/job
contracts. No successful browser-driven operating-system folder picker or
Finder drag/drop journey is claimed at this point. Before making that claim, a
human must complete both a genuine nested-folder picker smoke and a Finder
drag/drop smoke in current Chrome or Edge, then verify upload, polling, result
rendering, review PATCH, source opening, and JSON artifact download.

## Verification status

All passing results below were produced from the combined application commit
`5ec2bed0abf08ff64e4216d1872dd97619695eee`. They are local release evidence,
not production or customer-use claims.

| Check | Command or evidence | Status |
| --- | --- | --- |
| Complete backend suite | Locked, isolated, secret-free `uv run --locked --isolated --all-groups --no-env-file --no-cache ... python -m pytest -q -p no:cacheprovider` | **PASS — 294 tests and 10 subtests; one deprecation warning** |
| Frontend typecheck | `cd frontend && npm run typecheck` | **PASS** |
| Frontend lint | `cd frontend && npm run lint` | **PASS** |
| Frontend unit/component suite | `cd frontend && npm test -- --run` | **PASS — 18 files passed, 1 gated file skipped; 143 tests passed, 2 gated tests skipped (145 total), including capability-bootstrap gating, partial-entry rejection, URL/history state, focus retention, response-identity checks, path parity, and failed-document selection** |
| Frontend production build | `cd frontend && npm run build` | **PASS — 41 modules transformed** |
| Live adapter/backend contract | Environment-gated `workspaceAdapter.contract.test.ts` against this branch's combined backend and the committed sample statement | **PASS — 2/2 tests; exact uploaded bytes, polling/result retrieval, source retrieval, and JSON artifact** |
| Combined OpenAPI and CORS | Running combined app plus an `OPTIONS /api/ui/v1/jobs` preflight from the frontend origin | **PASS — 34 method/path routes with no duplicates; required routes present; requested headers and origin accepted** |
| RELAY export validation | Combined backend snapshot/export responses plus file-format inspection | **PASS — PDF/XLSX/JSON returned HTTP 200 with the same version/hash; PDF is 9 pages, XLSX opens as a valid ZIP package, and JSON metadata matches the run/version/hash** |
| `git diff --check` | Integration tip against `origin/main` | **PASS** |
| Visible NAV smoke | Real combined backend through the final frontend | **PASS — synthetic ATLAS review loaded, three human reviews produced immutable v4, PDF/XLSX/JSON downloaded through the UI, email remained preview-only, and the browser console was clean** |
| Visible Profile workflows smoke | Real combined backend at `/`, plus `/private/tmp/crazymonkey-profile-root-1280x800.png` and `/private/tmp/crazymonkey-profile-root-1440x900.png` | **PASS — correct Profile title/root landing, one accessible control per picker, live capability bootstrap, zero model calls/no browser execution disclosed, and no clipping/overflow at either required viewport** |
| Native OS folder picker and Finder drag/drop | Manual current Chrome or Edge | **NOT CLAIMED / MANUAL GAP** |

Passing local tests will establish the checked local contracts only. It will
not prove a production deployment, browser support beyond the inspected
surface, arbitrary-document interpretation, durable persistence,
authentication, live customer use, certification, or real email delivery.
