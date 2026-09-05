# V0 runtime and application integration handoff

STATUS: IMPLEMENTED AND INTEGRATED

SOURCE WORKSPACE: A clean temporary clone of `YaoSunHello/CrazyMonkey`, based on the pushed `Leo` branch. The shared Desktop checkout's other-agent changes were not stashed, copied or overwritten.

SOURCE BRANCH: `Leo`

CRAZYMONKEY BRANCH: `Leo`

FILES ADDED: `backend/app/runtime/` (contracts, evidence interpretation, analyst boundary, independent assurance, bounded pipeline, shared-snapshot adapter, local service, two-route API, BEACON facade, executable demo and README); four `backend/tests/test_runtime_*.py` suites; this handoff.

FILES MODIFIED: `backend/app/main.py` only for additive runtime/BEACON routers and compatible local CORS defaults after integrating RELAY's application wiring.

FILES INTENTIONALLY NOT MIGRATED: Old YLOOKUP/FundOps application files, baseline/history, private documents, credentials, generated output bundles, virtual environments, and frontend code owned by BEACON. ATLAS parsing, stable IDs, normalized/source contracts and fixture generation are reused unchanged.

DEPENDENCIES ADDED: None by the runtime. It uses existing Python/Pydantic/Decimal/FastAPI and RELAY's installed export stack.

## What is integrated

Original PDF/XLSX/CSV files go through canonical ATLAS. Structured analyst
proposals go through independent source challenge and deterministic Decimal
verification. One conditional repair is allowed, followed by final verification.
Source-bound results become the canonical Atlas `ReviewSnapshot` consumed by
RELAY. BEACON's existing HTTP adapter can upload/start/read/review/export through
the new backend facade. Human review freezes a new version without changing
financial findings. RELAY creates immutable PDF, Excel, JSON and draft EML output.

The offline analyst is explicitly `DEMO_FIXTURE`; it parses only documented,
supported financial clauses from normalized evidence. It does not load expected
answers or pretend to invoke a language model. `ModelAnalyst(callback)` is an
injectable real-execution interface; no hosted provider is configured by default.

LP03: reported GBP 50,000; applicable base GBP 10,000,000; annual rate 0.015;
period factor 0.25; expected GBP 37,500; difference GBP 12,500;
`REVIEW_REQUIRED`. LP01, LP02 and LP05 pass. LP04 is a second discrepancy.
LP06 is `CANNOT_VERIFY` because its expected side letter is not supplied.

## Tests and adversarial fixes

Final clean-checkout run after integrating RELAY `b0a881f`:
`pytest -q -p no:cacheprovider backend/tests` passed **189 tests and 116 subtests**.
Only two dependency deprecation warnings were emitted. The standalone integrated
demo also completed from this single checkout with all four RELAY artifacts.

Existing ATLAS/QA tests are preserved. New tests exercise exact money, correct
and incorrect agent proposals, no-data/model-error behavior, independent catalog
copies, nonexistent/tampered evidence, source/cell/claim binding, one successful
or failed repair, source-aware date selection and missing evidence. Adversarial
tests found and fixed ignored extra fee clauses, cross-period factors, duplicate
headers, conflicting investor names, ambient Decimal precision and numeric
overflow. Unsupported substantive terms, table fields or unscoped notes now fail
closed for human interpretation rather than silently assuming the demo rule.

Integration tests use freshly generated originals and actual ATLAS/runtime/RELAY
code, inspect PDF text, workbook rows, JSON values, EML attachments and content
hashes, and check immutable v1/v2/v3 review history. They also exercise actual
multipart uploads, both runtime routes, the BEACON review path and safe draft
preparation. No test or demo sends email.

## Known limits and integration notes

- One local API worker; active UI records/results are process-local. RELAY's frozen
  snapshots/artifacts persist. No production auth, queue or durable review DB.
- Original upload bytes are temporary; normalized source-linked evidence stays in
  active records. No original-file archive or download endpoint is implied.
- The supported-clause interpreter is deliberately narrow, not general financial
  or legal reasoning. Unsupported/ambiguous terms remain `CANNOT_VERIFY`.
- `confidence` is `NOT_SCORED`, not an invented probability. `severity` comes only
  from linked canonical challenger concerns.
- Human `REVIEWED` is a workflow marker, not approval of a discrepancy. It does not
  make LP03 pass or manufacture LP06's missing evidence.
- Unsourced term edits return 501; `termCorrection` is false. Supply source evidence
  and rerun instead. Run IDs are new; historical outputs are retained.
- Legacy BEACON email sending remains disabled because that form lacks RELAY's
  recipient/version/confirmation/idempotency contract. Drafts work; separately
  authorized transport configuration and explicit confirmation are needed to send.
- Existing RELAY artifact/header product labels are governed by RELAY's brief;
  this does not import the old YLOOKUP repository or its application baseline.
- Runtime/Atlas money is Decimal. Existing UI/RELAY presentation adapters serialize
  display numbers; the runtime JSON retains exact decimal strings.
- See `backend/app/runtime/README.md` for the exact demo, API and UI commands.

OLD YLOOKUP CODE INCLUDED: NO
