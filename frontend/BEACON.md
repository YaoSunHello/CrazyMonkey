# BEACON — CrazyMonkey human-review frontend

BEACON is CrazyMonkey's frontend and human-review surface for management-fee review findings. It presents document intake, visible processing progress, deterministic findings, source evidence, calculations, independent human-review states, controlled corrections, and guarded output actions.

This component is frontend-only. It does not perform document extraction, authoritative calculation, verification, export generation, or email delivery by itself.

## Current scope

BEACON provides:

- document selection, client-side validation, detection, and role confirmation;
- an explicit synthetic development demo;
- backend-reported review progress with failure and retry states;
- summary counts derived from findings, plus exception-led filters;
- finding-level reported, expected, and difference values;
- calculation inputs and formula display;
- structured PDF, workbook, and CSV evidence views;
- separate computational and human-review states;
- reviewer notes and correction/version history;
- capability-gated JSON, PDF, Excel, and email actions;
- a mock/live adapter boundary for backend integration.

The current review surface covers management-fee checks only. It does not include old YLOOKUP/FundOps code, Atlas backend implementation, Relay output implementation, authentication, or any certification/compliance claim.

## Truth and safety boundaries

### Development fixture mode is the default

If `VITE_API_MODE` is absent, BEACON runs in `mock` mode. The interface labels this as **Development fixture mode**.

The deterministic fixture is aligned to Atlas's committed synthetic source-pack outcomes, but it was not produced by a backend run. The UI states this explicitly. It represents:

| Investor | Administrator | Expected | Difference | Status |
| --- | ---: | ---: | ---: | --- |
| LP01 | £50,000 | £50,000 | £0 | MATCH |
| LP02 | £37,500 | £37,500 | £0 | MATCH |
| LP03 | £50,000 | £37,500 | £12,500 | DISCREPANCY |
| LP04 | £50,000 | £40,000 | £10,000 | DISCREPANCY |
| LP05 | £50,000 | £50,000 | £0 | MATCH |
| LP06 | £37,500 | unavailable | unavailable | CANNOT_VERIFY |

The resulting summary is six checks, three matches, two discrepancies, and one item that cannot be verified.

### Selected files are not reviewed in fixture mode

The mock adapter can classify selected filenames for UI development, but it never invents findings from selected files. Uploaded-pack review remains disabled until Atlas is connected. A failed live request never silently falls back to fixture data.

Accepted client-side formats are `.xlsx`, `.csv`, and `.pdf`, with a 25 MiB per-file limit. Backend validation remains authoritative once an upload endpoint exists.

### Human review does not rewrite computational status

`REVIEWED`, `NEEDS_FOLLOW_UP`, and `TERM_CONFIRMED` are human workflow states. They do not convert `DISCREPANCY` or `CANNOT_VERIFY` into `MATCH`.

The fixture correction path creates a new finding version and recomputes dependent values and statements. It does not imply that a source document or backend record was changed.

### Outputs are capability-gated

In fixture mode:

- the labelled JSON development fixture can be downloaded;
- PDF and Excel remain disabled until Relay is connected;
- an email draft can be previewed;
- email sending remains disabled;
- no external message is sent.

Relay's immutable version/hash, preview-token, recipient, idempotency, confirmation, and explicit-send controls must remain authoritative when integrated.

## Run locally

From the CrazyMonkey repository root:

```bash
cd frontend
npm ci
npm run dev
```

Open the URL shown by Vite, then choose **Load synthetic demo**.

Validation commands:

```bash
npm run typecheck
npm run lint
npm test
npm run build
```

## Adapter modes

| Mode | Configuration | Behaviour |
| --- | --- | --- |
| Development fixture | `VITE_API_MODE=mock` or unset | Runs the explicitly labelled deterministic demo; selected files are not parsed. |
| Integration mode | `VITE_API_MODE=live` | Selects the provisional HTTP adapter. This is not evidence that the backend contract is implemented or healthy. |

Example adapter configuration:

```bash
VITE_API_MODE=live VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## Provisional review API boundary

`src/api/httpReviewAdapter.ts` currently describes a frontend facade under `/api/v1`:

| Operation | Provisional route |
| --- | --- |
| Detect roles | `POST /api/v1/documents/detect` |
| Start uploaded review | `POST /api/v1/reviews` |
| Start synthetic review | `POST /api/v1/demo/reviews` |
| Retry review | `POST /api/v1/reviews/{reviewId}/retry` |
| Read progress | `GET /api/v1/reviews/{reviewId}/progress` |
| Read result | `GET /api/v1/reviews/{reviewId}` |
| Update human review | `PATCH /api/v1/reviews/{reviewId}/findings/{findingId}/review` |
| Correct extracted term | `POST /api/v1/reviews/{reviewId}/findings/{findingId}/corrections` |
| Add supporting document | `POST /api/v1/reviews/{reviewId}/documents` |
| Request output | `GET /api/v1/reviews/{reviewId}/exports/{format}` |
| Prepare email | `POST /api/v1/reviews/{reviewId}/email/prepare` |
| Send email | `POST /api/v1/reviews/{reviewId}/email/send` |

At migration time, the upload, review-run, progress, result, retry, human-review, correction, and supporting-document routes are not implemented by CrazyMonkey and must not be described as operational.

Concurrent Relay work defines compatibility handlers for `GET /api/v1/reviews/{runId}/exports/{format}` and `POST /api/v1/reviews/{runId}/email/prepare`. It deliberately rejects BEACON's legacy email-send shape because that request lacks the recipient, immutable version, preview token, and idempotency key required for a safe send. Those Relay changes are separately owned and are not part of the BEACON commit; endpoint availability depends on the Relay router being committed and mounted.

## Atlas integration blocker

Atlas currently supplies ingestion and canonical snake_case models, while BEACON uses a camelCase presentation model. Before enabling live mode, the team needs a validated Atlas-to-BEACON mapper or an agreed review-workflow facade that:

1. validates contract version, run ID, mode, review version, statuses, money values, and evidence;
2. exposes upload, progress, failure, completed-review, retry, and supporting-document workflows;
3. persists human decisions, notes, and immutable corrections;
4. maps Atlas's source references, calculations, challenger concerns, and verifier results without inventing data;
5. prohibits fallback from failed live requests to fixture results.

`HttpReviewAdapter.getReview()` must not be treated as compatible with a raw Atlas `ReviewSnapshot` until that mapper exists.

## Relay integration blocker

Relay's authoritative route family is `/api/runs/...`. The compatibility export/draft bridge described above does not replace Relay's immutable run/version/snapshot identity or its separate email draft/preview/explicit-send sequence.

Before enabling PDF, Excel, or email sending, the team must mount and test Relay, reconcile the canonical synthetic fixture, freeze the authoritative review version, consume returned artifact descriptors/URLs, and preserve Relay's preview-token and idempotency controls.

Passing the frontend checks proves only this component. It does not prove Atlas extraction, Relay artifact generation, email delivery, deployment, or an end-to-end live service.
