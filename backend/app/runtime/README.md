# Verified V0 runtime

For concurrent Gemini discovery, verified corrected workbook copies, and the
`run`, `replay`, and `list` commands, see [Turbo Audit](FAST_AUDIT.md).

For the autonomous folder audit CLI, bounded arithmetic DSL, runtime provider
adapter and independent challenge pass, see [INVESTIGATOR.md](INVESTIGATOR.md):

```sh
PYTHONPATH=backend python -m app.runtime.audit --input /path/to/files --instruction "Find material financial discrepancies in this fund pack."
```

This is executable application code after ATLAS, not a stored expected-result
fixture. It consumes the existing `NormalizedDocument` and `SourceRef` contracts.
ATLAS alone generates the fictional source pack and extracts PDF, XLSX and CSV.

## Run the integrated offline demo

From the CrazyMonkey repository root, with backend requirements installed:

```sh
PYTHONPATH=backend backend/.venv/bin/python -m app.runtime.demo --output outputs/v0-demo
```

The command creates a unique output directory containing eight original files,
their normalized evidence, a runtime JSON result, the versioned Atlas review
snapshot, and RELAY PDF/XLSX/JSON/EML exports. It does **not** send email. Its
`SIMULATED_DEMO_REVIEWER` demonstrates the state transition; it is not user approval.
The real UI review action is separate.

LP03 is GBP 50,000 reported, GBP 37,500 expected, GBP 12,500 overcharged,
`REVIEW_REQUIRED`. LP01/LP02/LP05 pass; LP04 is another discrepancy; LP06 is
`CANNOT_VERIFY` because its required side letter is absent. No answer JSON is read.

## Run BEACON against the backend

```sh
PYTHONPATH=backend backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```sh
cd frontend
VITE_API_MODE=live VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:4173`, choose the synthetic example or upload the generated
originals. Review the source-linked findings, record a human review decision, and
download RELAY artifacts. The backend provides the existing `/api/v1` BEACON facade;
no duplicate frontend is introduced. The runtime is synchronous, so the first
progress poll reports completed stages rather than simulated live progress.

## Service and two-route API

```python
from app.runtime import run_case
result = run_case(case_id, user_instruction, normalized_documents)
```

`POST /api/cases/{case_id}/run` takes `user_instruction`, `normalized_documents`
(Atlas JSON), and optional `mode: "DEMO_FIXTURE"`. `GET /api/cases/{case_id}/result`
returns the latest complete structured result. Amounts in this contract are exact
decimal **strings**. A request for an unconfigured `MODEL` gets 503, never a silent
fixture fallback. The raw normalized-input endpoint is an internal/demo trust
boundary: clients must supply the real Atlas output, not authored evidence. The
BEACON upload route establishes that boundary by actually normalizing file bytes.

`FixtureAnalyst` is a clearly labelled, narrow deterministic clause interpreter.
`ModelAnalyst(callback)` invokes an injected real model caller with normalized
evidence and the Pydantic response schema. It has no provider dependency or fake
credential-backed claim. Pass it to `run_case(..., analyst=adapter)` or configure
the `ReviewService` with it. Unsupported clause vocabulary fails closed. This V0
does not claim general legal interpretation of arbitrary contracts.

## Trust and repair

`evidence.py` captures a validated, immutable JSON copy of the Atlas evidence set.
The analyst only receives independent copies and can cite existing IDs, not create
source records. Quote, locator, document ID and hash must resolve exactly to the
captured set. This is source binding, not cryptographic original-document signing.

`assurance.py` independently reconstructs terms, challenges claims and citations,
and calculates with `Decimal`, half-up to one penny. Difference means reported
minus expected; tolerance comes from the governing evidence. The analyst's
arithmetic is never trusted. Red-team source checks and fixture interpretation
share a deliberately limited clause vocabulary; adversarial coverage tests protect
that boundary, but this is not an independent hosted-model red team.

`pipeline.py` has one conditional repair branch, no recursive/unbounded loop.
After a challenge, missing evidence, or failed amount check, it permits exactly one
repair attempt and performs final source/arithmetic checks. Unresolved results are
`NEEDS_HUMAN_REVIEW`. A confirmed fee discrepancy is not repaired away by changing
reported values. Trace entries contain operational summaries, never hidden reasoning.

`snapshot.py` is a minimal adapter to the existing Atlas `ReviewSnapshot`; RELAY's
existing adapter owns export conversion. Runtime `PASS` becomes Atlas `MATCH`;
supported financial `REVIEW_REQUIRED` becomes `DISCREPANCY`; unresolved proposed
interpretation becomes `UNSUPPORTED`; missing sources remain `CANNOT_VERIFY`.
All rule, calculation and finding references resolve to the same source catalog.

`service.py` increments immutable snapshot versions on human review. Financial
statuses and calculated amounts do not change. Existing audit events are included
in the new snapshot version while older frozen snapshots stay unchanged. A source
change creates a fresh run; unsourced term corrections return 501.

## Email and operational limits

RELAY owns exports, draft preparation and explicit confirmed sending. The legacy
BEACON dialog cannot supply the safe recipient/version/token/idempotency contract,
so its `emailSend` capability is false. Use RELAY's documented versioned API for a
separately authorized send; this demo never calls a transport.

Run one local worker. UI review records and runtime results are process-local;
RELAY frozen snapshots and artifacts persist on disk. Restarting the server loses
active UI review lookup state. No authentication, multi-tenant isolation, production
rate limiting, job queue, durable review DB or public deployment is included.
Keep the server bound to localhost. Uploads are limited to 40 files, 25 MiB per
file and 100 MiB per batch. Raw upload bytes are temporary; normalized source-linked
evidence survives in active review records. No persistent original-blob archive or
source-download endpoint is claimed. Decimal is authoritative in runtime/Atlas;
existing UI and RELAY output view use presentation numbers.

## Tests

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_*.py' -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend backend/.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/relay
```

Runtime tests cover fee results, source binding and tampering, incorrect claims and
arithmetic, one successful/failed repair, no-data and model-failure safety, actual
Atlas uploads, immutable human review, the two-route API and RELAY generation.
