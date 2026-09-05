# CrazyMonkey frontend

The frontend keeps the workflows on current `main` and adds the profile-driven
folder review as the brief-required landing workspace. It does not replace
BEACON/NAV or reuse its API contract.

| Workspace | How to open it | Backend contract |
| --- | --- | --- |
| **Profile workflows** | Default at `/`; `/?workspace=profiles` remains a supported alias | Deterministic UI bridge under `/api/ui/v1`, plus `/health` and `/api/profiles` |
| **NAV review** | Select it in the workspace navigation or open `/?workspace=nav` | Active BEACON, runtime, and RELAY routes under `/api/v1`, `/api/cases`, `/api/runs`, and `/api/relay` |
| **Full Pack** | Set `VITE_ENABLE_PACK_WORKSPACE=1`, then select it or open `/?workspace=pack` | Historical `/api/pack` dependency; that backend is not included, so this workspace is off by default |

The Profile workflows adapter is always live: it validates backend health,
profile discovery, and the `ui.v1` capabilities contract before enabling a
job. It never falls back to fixture output. The NAV workspace retains its
explicit mock mode for isolated UI development; set `VITE_API_MODE=live` for an
integrated backend run.

For the PDF-only demo, keep **Bank statement validation** selected, choose a
supported bank-statement PDF, then choose **Start review**. One valid PDF enables
the button immediately; there is no additional blanket confirmation checkbox.
Files discovered under answer/output-like folders still require explicit
per-file inclusion. Selecting files alone never starts a job.

The two live choices retain their backend IDs: **Bank statement validation**
uses `journal-entries`, and **Statement validation package** uses
`pipeline-validation`. Both describe the deterministic bridge, which parses
statements and checks arithmetic/source evidence without model resolution or
classification. Recorded runs remain a separate, explicitly selected view.

Accepted jobs are remembered in browser session storage for the configured
backend, so reloading the tab resumes the existing job without uploading again.
If the backend no longer has that job, the workspace returns to the inventory
with recovery guidance. **New review** starts a fresh submission identity;
retrying an uncertain upload preserves its idempotency key. Results retain the
actual processing history, original-source links, and available source metadata.

## Run the integrated frontend

From the repository root, install dependencies and start the combined FastAPI
application:

```bash
uv sync
PYTHONPATH=backend uv run python -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8000
```

In another terminal, use Vite's same-origin proxy. `CRAZYMONKEY_BACKEND_ORIGIN`
is read by the Vite server, while the browser sends requests to its own origin:

```bash
cd frontend
npm ci
CRAZYMONKEY_BACKEND_ORIGIN=http://127.0.0.1:8000 \
VITE_API_MODE=live VITE_API_BASE_URL=/ \
  npm run dev -- --host 127.0.0.1
```

Open <http://127.0.0.1:4173/> for Profile workflows or
<http://127.0.0.1:4173/?workspace=nav> for NAV review.

Direct cross-origin development is optional:

```bash
cd frontend
VITE_API_MODE=live VITE_API_BASE_URL=http://127.0.0.1:8000 \
  npm run dev -- --host 127.0.0.1
```

The backend's default development CORS list permits the loopback frontend on
ports `4173` and `5173`. Set `CRAZYMONKEY_CORS_ORIGINS` to an explicit
comma-separated allow-list when using another origin; do not use a wildcard as
a production policy.

## Profile workflow limits

The `/api/ui/v1/capabilities` response is authoritative. The current bridge
advertises `journal-entries` and `pipeline-validation`, accepts PDF sources and
at most one optional XLSX reference, and enforces:

- 40 selected files;
- 25 MiB per file;
- 100 MiB per batch;
- 12 nested directories, excluding the filename; and
- 100 retained job events.

Profile jobs are labelled `LOCAL_DETERMINISTIC`, execute zero model calls, and
produce a downloadable JSON artifact. The bridge does not advertise PDF or
XLSX generation; those formats remain available only through the separate NAV
review and RELAY flow.

Current Chrome and Edge are the supported demo browsers for folder selection
and full folder drag/drop because the implementation uses `webkitdirectory`,
`webkitRelativePath`, and the browser entry API. Safari and Firefox are not
certified by this handoff. Automated tests cover nested paths and traversal,
but no successful manual operating-system folder-picker or Finder drag/drop
journey is claimed yet.

See [BEACON.md](BEACON.md) for the NAV workflow and
[`docs/handoffs/frontend-integration.md`](../docs/handoffs/frontend-integration.md)
for the merged contract, boundaries, owned paths, and release checklist.
