# BEACON — human-review frontend

## Integration status

This repository version includes the BEACON HTTP facade and RELAY routes mounted
by `backend/app/main.py`. In live mode, the existing frontend posts the original
file bytes to that backend; ATLAS normalizes the sources, the runtime performs
the analyst/challenger/verifier sequence, and RELAY freezes and exports the
result. The browser does not calculate findings or silently substitute fixture
answers when the backend is unavailable.

The integration is additive to the backend already on `main`: the existing
`/health`, `/api/profiles`, `/api/profiles/{profile_id}`, CLI, agent, profile,
and verification code remain in place. The legacy `/api/pack` Python importer
from `leo2` is not included; only its frontend is preserved behind an
off-by-default feature flag.

For a standalone UI preview, run `npm ci` and `npm run dev` from `frontend/`, then
open `http://127.0.0.1:4173`. This defaults to explicitly labelled fixture mode.
For the integrated path, use the live-mode commands below; a missing or failed
backend is shown as **Backend unavailable**.

BEACON is CrazyMonkey's nontechnical fund-review workspace. It consumes the
backend's BEACON presentation contract after ATLAS has normalized the source
documents and the V0 runtime has reconstructed and verified the financial
result. The browser never parses a PDF, workbook, or CSV and never determines a
financial status itself.

The interface is intentionally exception-led. A reviewer can see, in one view:

- the investor and fund/reporting-period context;
- the administrator-reported amount, independent reconstruction, and directional
  difference;
- the deterministic finding, linked challenger severity, and an honest confidence
  state;
- the calculation inputs and exact verifier conclusion;
- key ATLAS evidence first, with every remaining source reference still available;
- a separate human-review state and note trail; and
- immutable RELAY outputs only after every computational non-match has a recorded
  human disposition.

BEACON presents and orchestrates these results. ATLAS owns extraction and source
references, the runtime owns financial calculation and verification, and RELAY
owns export generation and email preview/delivery controls.

## Integrated data flow

1. In live mode, selected `.pdf`, `.xlsx`, and `.csv` files are posted to the
   backend for filename/role detection. BEACON performs client-side extension,
   per-file-size, and duplicate-selection checks; the backend independently
   enforces upload limits and the manifest contract.
2. The confirmed upload manifest and original bytes are sent to the backend.
   ATLAS normalizes them; the V0 runtime performs evidence-bound reconstruction,
   challenge, and exact decimal verification.
3. The backend maps the canonical snake_case review snapshot to BEACON's
   camelCase presentation contract. `HttpReviewAdapter` rejects raw ATLAS
   snapshots and invalid presentation payloads missing render-critical fields;
   it never falls back to fixture data.
4. Human decisions are recorded in the process-local review service, and each
   decision freezes a new immutable RELAY snapshot version on disk. BEACON
   refetches the complete review after each decision so the displayed version and
   RELAY identity stay synchronized.
5. Once every `DISCREPANCY`, `CANNOT_VERIFY`, or `UNSUPPORTED` finding has a
   human disposition, BEACON enables PDF, Excel, JSON, and email-preview actions.
   RELAY returns the immutable review version and snapshot SHA-256; BEACON blocks
   an export if its returned version differs from the version on screen.

## Truth and safety boundaries

### Financial status and human review are independent

`MATCH`, `DISCREPANCY`, `CANNOT_VERIFY`, and `UNSUPPORTED` are computational
states. `REVIEWED`, `NEEDS_FOLLOW_UP`, and `TERM_CONFIRMED` are human workflow
states. Recording a human decision never rewrites a deterministic financial
finding into a match.

BEACON's RELAY-readiness gate means only that every non-match has a recorded
human disposition. It is a frontend workflow gate, not backend authorization,
fund approval, sign-off, certification, or remediation.

### Severity is not status, and confidence is not invented

Severity is the highest linked challenger-concern severity supplied by the
backend. A discrepancy with no linked concern therefore displays **Not
assigned**, not a severity inferred by the frontend. The canonical V0 snapshot
does not currently provide a confidence metric, so BEACON displays **Not scored**
and explains that the reviewer should rely on deterministic checks and source
evidence. It does not manufacture a percentage.

### Deterministic verification and commentary are visibly separate

The verifier's exact arithmetic/rule conclusion is shown separately from
challenger commentary. In `LIVE_MODEL` mode the latter may be agent-authored; in
the synthetic and offline modes it is explicitly labelled deterministic or
offline challenger commentary. The UI exposes observable conclusions and source
references; it does not claim a hosted-model call or private chain-of-thought.

### Evidence inspection is source-linked, not an original-file viewer

Evidence actions show the ATLAS evidence ID, document role, filename, locator,
and normalized quote/value. This provides traceability within the frozen
normalized review snapshot. It does not authenticate the original file,
digitally certify its contents, or provide an original-file viewer/download.

### Correction and sending stay capability-gated

The live backend advertises `termCorrection: false`: an unsourced override is
not allowed. The missing-side-letter workflow instead allows the reviewer to add
the required source document and rerun.

The BEACON email-preparation route returns an unsigned, recipient-free display
draft with immutable snapshot identity and three attachments. BEACON displays
**Draft — not sent**. The integrated facade advertises `emailSend: false`, so the
browser presents no send or confirm button. A separately authorized delivery
must first submit a recipient and immutable version to RELAY's versioned preview
endpoint, then use the returned signed token with RELAY's explicit confirmation
and idempotency contract.

## Development fixture mode

If `VITE_API_MODE` is absent or set to `mock`, BEACON uses an explicitly labelled
deterministic development fixture. Selected files are never parsed in this mode.
The fixture mirrors the committed synthetic example for UI development:

| Investor | Administrator-reported | Independent reconstruction | Difference | Finding |
| --- | ---: | ---: | ---: | --- |
| LP01 | £50,000 | £50,000 | £0 | `MATCH` |
| LP02 | £37,500 | £37,500 | £0 | `MATCH` |
| LP03 | £50,000 | £37,500 | £12,500 above | `DISCREPANCY` |
| LP04 | £50,000 | £40,000 | £10,000 above | `DISCREPANCY` |
| LP05 | £50,000 | £50,000 | £0 | `MATCH` |
| LP06 | £37,500 | unavailable | unavailable | `CANNOT_VERIFY` |

The resulting totals are six checks, three matches, two discrepancies, and one
item that cannot be verified. Fixture mode may demonstrate a local correction
version for UI testing; that is not a backend or source-document change.

## Run the integrated demo

From the CrazyMonkey repository root, start the backend:

```bash
uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd frontend
npm ci
VITE_API_MODE=live VITE_API_BASE_URL=http://127.0.0.1:8000 \
  npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:4173`, select **Load synthetic demo**, and use this
review path:

1. On the summary, confirm the `6 / 3 / 2 / 1` totals and open the first
   exception from **Review next exception**.
2. Inspect LP03's £50,000 administrator amount, £37,500 reconstruction, £12,500
   difference, calculation, and Side Letter Section 3.1 evidence.
3. Record LP03 as reviewed, then review LP04. Mark LP06 **Needs follow-up** with
   a note that its side letter is required.
4. Return to the summary. **Ready for RELAY** appears at `3 of 3 exceptions
   reviewed`; deterministic findings remain unchanged.
5. Download PDF, Excel, and JSON. Each success notice must show the same review
   version and snapshot-hash prefix.
6. Select **Prepare email**. Confirm it says **Draft — not sent**, shows the same
   version/hash and three attachments, has no recipient selected, and offers no
   send/confirm action.

The synthetic path still runs through the real backend, ATLAS normalization,
runtime, process-local review state, on-disk RELAY snapshot freezing, and RELAY
export generation. `DEMO_FIXTURE` identifies the backend's bounded deterministic
clause interpreter; it is not a hosted-model call or live fund data.

## Active BEACON API facade

| Operation | Route | Current behaviour |
| --- | --- | --- |
| Detect roles | `POST /api/v1/documents/detect` | Active; filename-based role proposal only |
| Start uploaded review | `POST /api/v1/reviews` | Active; bytes are normalized by ATLAS |
| Start synthetic review | `POST /api/v1/demo/reviews` | Active; creates a fresh backend review |
| Read progress | `GET /api/v1/reviews/{reviewId}/progress` | Active; V0 currently completes synchronously |
| Read result | `GET /api/v1/reviews/{reviewId}` | Active; mapped BEACON presentation contract |
| Retry review | `POST /api/v1/reviews/{reviewId}/retry` | Active; creates a fresh run |
| Update human review | `PATCH /api/v1/reviews/{reviewId}/findings/{findingId}/review` | Active; freezes version `n + 1` |
| Correct extracted term | `POST /api/v1/reviews/{reviewId}/findings/{findingId}/corrections` | Deliberately `501` for unsourced overrides |
| Add supporting document | `POST /api/v1/reviews/{reviewId}/documents` | Active; creates a fresh run with the added source |
| Request output | `GET /api/runs/{reviewId}/versions/{version}/exports/{format}` | Active for displayed-version PDF/XLSX/JSON through RELAY |
| Prepare email | `POST /api/v1/reviews/{reviewId}/email/prepare?version={version}` | Active, unsigned recipient-free display draft only |
| Legacy browser send | `POST /api/v1/reviews/{reviewId}/email/send` | Always rejected with `422`; advertised capability is `false` |
| Version-bound email preview | `POST /api/runs/{reviewId}/email/preview` | Requires a user-entered recipient and immutable review version; does not send |
| Confirmed RELAY send | `POST /api/runs/{reviewId}/email/send` | Disabled by default; also requires an enabled server, SMTP configuration, signed preview token, exact version, explicit `SEND`, and idempotency key |

## Validation

From `frontend/`:

```bash
npm run typecheck
npm run lint
npm test -- --run
npm run build
```

For the focused backend bridge from the repository root:

```bash
uv run pytest -q -p no:cacheprovider \
  backend/tests/test_runtime_beacon.py backend/tests/test_runtime_integration.py
```

For the complete backend suite from the repository root:

```bash
uv run pytest -q -p no:cacheprovider
```

The root backend test guard removes all email-enable and SMTP environment
variables and fails immediately if either `smtplib.SMTP` or `smtplib.SMTP_SSL`
is constructed. Tests of the confirmation workflow use an in-memory recording
transport; a passing suite therefore performs no network email operation.

Passing these checks proves the local component and integrated fixture path. It
does not prove production deployment, arbitrary-contract interpretation,
authentication, durable multi-user persistence, original-document retention, or
real email delivery.
