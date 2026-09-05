# Current integration and merge-readiness QA

Audit date: 5 September 2026. Canonical checkout: `~/Desktop/crazymonkey`.
Repository: `YaoSunHello/CrazyMonkey`; branch: `Leo`.

## QA STATUS

**PASS for the supported local offline V0. SAFE TO OPEN PR TO MAIN: YES within that scope.**
No main merge was performed. No real email was sent. Hosted-model execution and
production readiness are not claimed.

## Phase 1: audited Git state before any source modifications

- `pwd` and `git rev-parse --show-toplevel` both identified the requested Desktop checkout.
- Branch: `Leo`.
- Initial `HEAD` and fetched `origin/Leo`: `5fbcb80fd5393403755853e17fa099a34a71322b`.
- `origin/main`: `aebc028be9265f7bf9eb5e0bea98a25b6280d2d3`.
- Origin fetch/push URL: `https://github.com/YaoSunHello/CrazyMonkey.git`.
- `git merge-base --is-ancestor 88b90a356943fa7579b56a1e84b5eccbfdc02dd5 Leo`: **exit 0**.
- `git rev-list --left-right --count HEAD...origin/Leo`: **0 / 0**.
- `git rev-list --left-right --count origin/main...HEAD`: **0 / 4**.
- Initial committed diff versus main: **56 files, 13,323 insertions, 1 deletion**.
- Full status, local diff, branch graph, diff statistics and full committed diff were inspected. The generated lockfile and bulk stylesheet dominate the diff; runtime boundaries were inspected separately in their actual source files.

Committed work, oldest first:

| Commit | Work |
| --- | --- |
| `e2ec62a` | Synthetic pipeline contract fixture and safety checks |
| `88b90a3` | Canonical ATLAS ingestion, evidence models and synthetic source generator |
| `8ea8f2e` | ATLAS hardening, 58 additional QA tests and prior QA report |
| `5fbcb80` | BEACON review frontend, adapters, fixture, tests and handoff |

Initial local tracked modifications:

- `backend/app/main.py`: mounts RELAY and adds CORS configuration; **other-agent work**.
- `backend/requirements.txt`: adds XlsxWriter, jsonschema, httpx and pytest; **other-agent work**.

Initial untracked work: **27 files**, all treated as valuable RELAY-owned work:

```text
backend/.env.example
backend/app/relay/__init__.py
backend/app/relay/api.py
backend/app/relay/contracts.py
backend/app/relay/demo.py
backend/app/relay/email_delivery.py
backend/app/relay/export_service.py
backend/app/relay/json_export.py
backend/app/relay/models.py
backend/app/relay/pdf_export.py
backend/app/relay/snapshot_store.py
backend/app/relay/utils.py
backend/app/relay/xlsx_export.py
backend/app/schemas/review_export.schema.json
backend/fixtures/synthetic_review_snapshot.json
backend/tests/__init__.py
backend/tests/relay/__init__.py
backend/tests/relay/artifact_assertions.py
backend/tests/relay/conftest.py
backend/tests/relay/test_api.py
backend/tests/relay/test_atlas_adapter.py
backend/tests/relay/test_export_bundle_and_email.py
backend/tests/relay/test_json_export.py
backend/tests/relay/test_pdf_export.py
backend/tests/relay/test_snapshot_contract.py
backend/tests/relay/test_spreadsheet_literals.py
backend/tests/relay/test_xlsx_export.py
```

The initial porcelain view grouped these as directories; explicit file inventory
confirmed 64 tracked and 27 untracked files. A SHA-256 manifest of 91 tracked/untracked
source files was captured before testing. During the audit, RELAY's owner changed
`xlsx_export.py`, its test and `pdf_export.py`; those changes were observed and never reverted.
The owner also added `docs/handoffs/relay.md` during the audit, bringing preserved
untracked other-agent work to 28 files before the owner committed it.

During final QA, the RELAY owner committed all 30 of its intended files as
`b0a881ffa94d83324548dc56ffa1460480eb698f` (`migrate: add RELAY output delivery layer`).
QA left its staging area untouched until that commit completed. At that intermediate checkpoint, QA had changed only its own diagnostic/runbook files. The owner
commit is not attributed to QA. No unrelated uncommitted files remained at this
checkpoint.

The fetched `origin/main` also advanced independently to
`2f27441a18f48328d9220b6e98c0f1de1f762619` (three README badge commits). At that RELAY-only
intermediate checkpoint, Leo was 5 commits ahead and 3 behind that main, with 85 changed files,
18,941 insertions and 2 deletions in the merge-base diff. QA did not merge main.

## Current integrated checkpoint

The runtime owner subsequently pushed `ede953ed7bf30a72e37b0498bf702c6857130da0`
and fast-forwarded the canonical checkout without overwriting QA changes. This
adds the real runtime, BEACON facade and CORS correction. QA restarted the actual
application and repeated integration checks. Earlier missing-route observations
are preserved below as found-and-resolved history, not the final product state.

The final QA source is `ede953e` plus the explicitly listed bounded QA fixes.
Final pre-commit refs were HEAD/origin/Leo `ede953ed7bf30a72e37b0498bf702c6857130da0`
and origin/main `f90a22552f0204b77471069962767be0b589448a`. Leo was 6 commits ahead
and 5 behind main; the pre-QA committed merge-base diff contained 102 files,
22,094 insertions and 2 deletions. Main's additional commits affect README/branding.
RELAY and runtime implementation commits belong to their respective owners.
The earlier `docs/QA_REPORT.md` remains historical ATLAS evidence; this report
supersedes its whole-product availability statements.

## TEST RESULTS

| Check | Verified result |
| --- | --- |
| Initial ATLAS ingestion/model suite | **8 passed** |
| Initial full backend with local RELAY | **129 passed, 106 subtests passed** |
| Final integrated backend regression | **216 passed, 116 subtests passed**; two dependency deprecation warnings |
| Added backend QA regressions | **27 new tests** beyond the owner's integrated 189-test baseline |
| Installed dependencies | Backend `pip check`: no broken requirements; frontend `npm ls --depth=0`: no missing/invalid dependencies |
| Final frontend typecheck / lint | **PASS / PASS** |
| Final frontend tests | **7 files, 24 tests passed**; 12 additional tests |
| Frontend production build | **PASS**, 30 modules, production output outside the checkout |
| Actual canonical HTTP smoke | **112 checks passed against the final QA source** using the mounted app and freshly generated original files |
| Actual runtime CLI | **PASS**, exit 0; 8 originals, one bounded repair, 6 financial findings, 4 RELAY artifacts |
| Ingestion-only diagnostic | **PASS** for 4 packs / 17 source files and reopened normalized JSON; downstream stages correctly `NOT_TESTED` in that narrower runner |
| Browser fixture path | Labelled mock review, LP03 evidence and human state, unsent draft verified |
| Browser live path after fixes | Source-generated review, visible synthetic/offline notice, correct LP03 result, updated immutable review version, disabled unsupported correction, version-bound exports and unsent draft |
| Report validation | PDF/XLSX/JSON/EML reopened, values and hashes checked; v1 remained byte-identical after v2 |
| PDF visual review | All nine source-heavy pages inspected; expected-fee wording corrected and regenerated report reviewed |
| Email safety | Malformed, legacy and unconfirmed requests rejected; transport disabled/hard-blocked; **no email sent** |

Backend regression passed after each logical fix. Tests use the installed
`backend/.venv` Python 3.11.5; frontend uses Node 26.8.1/npm 11.19.0. A fresh
dependency installation was not performed, and existing unpinned Python
requirements remain a reproducibility limitation. The frontend lockfile was
preserved. The final response records any additional clean-snapshot verification.

The two warnings are Starlette's deprecated httpx TestClient integration and the
deprecated AnyIO BlockingPortal alias. They are not failing tests. Sandbox-only
`EPERM` errors affected localhost access and Vite's bundled config cache;
authorized localhost execution and `--configLoader native` resolved those.

Use **pytest for the complete suite**. `unittest discover` omits module-level
pytest cases. `PYTHONPATH=backend` is required; no pytest project configuration
sets it automatically. Current startup reads `os.getenv`; `.env.example` is a
reference, not an automatically loaded configuration file.

## WHAT WORKS RIGHT NOW

| Stage | Status | Actual evidence |
| --- | --- | --- |
| Original financial files → normalized ATLAS evidence | **PASS** | Eight fresh PDF/XLSX/CSV originals uploaded; byte hashes matched independent normalization and source references |
| Evidence → analyst proposal | **PASS for offline supported clauses** | Actual bounded deterministic interpreter, explicitly `DEMO_FIXTURE`; no expected-answer snapshot loaded |
| Red-team/source challenge | **PASS for deterministic checks** | Source, citation, investor, term and claim checks; no independent hosted-model red team claimed |
| Deterministic verification / bounded repair | **PASS** | Decimal arithmetic, one repair maximum, final verification, unresolved findings retained |
| Frontend review | **PASS** | Real HTTP adapter; evidence details; independent human-review state; refreshed version |
| PDF / Excel / JSON export | **PASS** | Real immutable version-bound downloads with matching hashes and correct content |
| Email draft / EML | **PASS** | Blank recipient, three real attachments, explicitly unsent |
| Confirmed real email delivery | **PARTIAL / NOT LIVE-TESTED** | Confirmation boundary tested using disabled/recording transport; no real provider call |
| Complete local supported-source V0 | **PASS** | Originals → ATLAS → offline analysis/challenge → Decimal verification → human review → real exports/draft |

The generated pack produces **3 matches, 2 discrepancies and 1 cannot verify**.
LP03 is **GBP 50,000 reported, GBP 37,500 expected, GBP 12,500 difference**.
LP04 is GBP 50,000 / 40,000 / 10,000. LP06 has no expected or difference value
because its required side letter is absent. Marking LP03 reviewed does not turn
its discrepancy into a pass. Human review freezes a new snapshot version.

An actual upload run followed this trace:
`INGESTED → ANALYSED → RED_TEAMED → VERIFIED → REPAIRED → RED_TEAMED → FINAL_VERIFIED → OUTPUT_PLANNED`.
Version 1's four downloads remained byte-identical after version 2; requesting a
version 1 email draft also retained its original hash while version 2 existed. The version 2
PDF had nine pages; the workbook contained Summary, Findings, Investor Terms,
Calculations, Sources and Audit Trail. EML had no `To` header and three attachments
matching the PDF/XLSX/JSON bytes. Generated sources and outputs are fictional QA
material, not live client financial records.

## BUGS FOUND / BUGS FIXED

| ID | Reproduced defect | Final outcome |
| --- | --- | --- |
| I01 | Vite 4173 rejected by CORS defaults intended for 5173; preflight 400 | **Fixed by runtime owner**; POST/PATCH default preflights now pass |
| I02 | `POST /api/v1/demo/reviews` and workflow routes returned 404 | **Integrated by runtime owner**, then independently tested against the actual app |
| I03 | `findings:null`, BEACON `version:"oops"`, empty finding `{}` caused HTTP 500 via TypeError/ValueError/KeyError | **Fixed by QA**: known adapter input failures become controlled 422; storage/export failures are not swallowed |
| I04 | BEACON LIVE_OFFLINE/LIVE_MODEL rejected by RELAY mode enum | **Fixed by QA**: map to LIVE, retaining original execution mode in provenance; fixtures stay synthetic |
| I05 | Wrong-investor calculations, nonreciprocal links and unknown term evidence accepted | **Fixed by QA**: cross-reference checks reject contradictions while preserving unresolved missing-evidence cases |
| I06 | Invalid SMTP_PORT crashed imports even with email disabled | **Fixed by QA**: disabled delivery skips SMTP initialization; actual app import/health tested |
| I07 | Independently authored BEACON/RELAY static fixtures reuse one run ID/version and conflict | Immutable rejection retained; integrated runtime creates unique run IDs, so the verified product path avoids this collision |
| I08 | UI retained v1 after backend saved v2; exports/drafts selected latest rather than displayed version | **Fixed by QA**: refresh full review; downloads use immutable version route; draft requests specify version. Tests cover another client advancing to v3 while UI stays bound to v2 |
| I09 | RELAY accepted supplied financial values without independently recalculating them | Architectural scope retained: RELAY exports; the integrated runtime now performs source-bound verification before exporting. Raw snapshot/normalized-input APIs remain trusted local boundaries |
| I10 | Disabled-send message falsely said a configured confirmation secret was mandatory | **Fixed by QA**: message matches actual opt-in/SMTP prerequisites. Existing random process-local signing secret and all confirmation gates retained |
| I11 | Separate `crazymonkey.pipeline-review.v1` sample rejected by RELAY | Intentional unsupported contract; integrated product uses the supported ATLAS snapshot adapter |
| I12 | Ingestion runner hard-coded downstream absence and whole-product failure | **Fixed by QA**: scoped ingestion evidence, path-presence inventory and downstream NOT_TESTED |
| I13 | Old full-suite commands missed pytest tests; root README lacked usable current commands | **Fixed by QA**: this runbook and root navigation link |
| I14 | Runtime termCorrection:false ignored; UI offered a correction that returns 501 | **Fixed by QA**: disabled with explanation; fixture behavior preserved |
| I15 | ATLAS synthetic/offline source notice hidden; summary could imply model execution | **Fixed by QA**: execution-mode label and upstream notice visible |
| I16 | A successful review PATCH followed by failed refresh was reported as unsaved | **Fixed by QA**: both notification and form accurately report saved action / failed refresh |
| I18 | Unsent draft dialog claimed the RELAY endpoint was disconnected when send was intentionally disabled | **Fixed by QA**: accurately says sending is disabled for this review |
| I17 | PDF appended expected value after prose ending “difference = reported minus expected,” implying wrong difference | **Fixed by QA**: separate explicit “Expected fee:” label; amount tables unchanged |

## WHAT IS PARTIAL / NOT IMPLEMENTED / KNOWN BLOCKERS

- **Hosted model: NOT INTEGRATED/configured.** An injectable model interface exists;
  unconfigured MODEL requests return 503 and leave no successful result. There is
  no silent fallback. A hosted-model red team has not been executed.
- **General document interpretation: PARTIAL.** The deterministic interpreter
  supports a narrow clause vocabulary and fails closed on unsupported/ambiguous
  terms. These results do not establish general contract-understanding accuracy.
- **Unsourced term correction: NOT IMPLEMENTED.** Backend returns 501 and the live
  UI disables it. Supply source evidence and rerun; prior outputs remain intact.
- **OCR, original-document archive/download, durable review DB, background queue,
  authenticated users, multi-tenant isolation and production deployment: NOT
  IMPLEMENTED in this V0.** Run one worker on localhost. Restarting loses active
  UI/runtime lookup records; frozen RELAY artifacts persist.
- **Real email delivery: NOT LIVE-TESTED.** Frontend send remains disabled. A real
  send requires separately configured transport and explicit recipient/version/
  signed-token/confirmation/action/idempotency data. QA never supplied real mail
  credentials or contacted a provider. Confirmation state is process-local.
- **Trust boundary:** direct normalized/snapshot APIs accept caller-authored
  structures. The tested upload path establishes evidence from actual file bytes;
  direct endpoints are not authenticated original-document certification.
- **Presentation:** runtime/ATLAS retain Decimal; existing UI/RELAY use display
  numbers. The PDF source appendix is dense and has some spacious continuation
  pages. XLSX cells/content were checked; its runtime workbook was not visually
  rendered in a spreadsheet application during this audit.
- **Release scope:** no known blocker remains for the tested local offline demo.
  The limitations above block describing it as production-ready, a configured
  hosted-model system or verified real email delivery.

## DEMO RUN COMMANDS

From the canonical checkout, use the installed environment and keep email off:

```bash
cd ~/Desktop/crazymonkey
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend \
CRAZYMONKEY_ENABLE_EMAIL_SEND=false \
CRAZYMONKEY_RELAY_OUTPUT_DIR=/tmp/crazymonkey-judge-demo \
SMTP_HOST= SMTP_PORT= SMTP_USERNAME= SMTP_PASSWORD= SMTP_FROM= \
backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd ~/Desktop/crazymonkey/frontend
VITE_API_MODE=live VITE_API_BASE_URL=http://127.0.0.1:8000 \
  npm run dev -- --configLoader native --host 127.0.0.1
```

Open `http://127.0.0.1:4173/`. Choose **Load synthetic demo**, open LP03, inspect
its evidence and calculation, enter a reviewer name, mark reviewed, return to
findings and download PDF/Excel/JSON or prepare an unsent email draft. The status
stays Discrepancy. Stop any existing Vite server first; port 4173 is strict.

For a real upload demonstration, generate fictional originals and select all
eight PDF/XLSX/CSV files in the UI:

```bash
cd ~/Desktop/crazymonkey
PYTHONPATH=backend backend/.venv/bin/python -m app.atlas.fixtures \
  --output /tmp/crazymonkey-judge-originals-new
```

The complete standalone demo generates originals, normalization, runtime result,
versioned review and all four outputs. It labels its human action simulated:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend CRAZYMONKEY_ENABLE_EMAIL_SEND=false \
  backend/.venv/bin/python -m app.runtime.demo --output /tmp/crazymonkey-v0-demo
```

The older ingestion-only diagnostic remains available separately:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend backend/.venv/bin/python \
  backend/tests/run_qa_demo.py --output /tmp/crazymonkey-ingestion-new
```

Use a fresh directory for that diagnostic. Successful ingestion writes PASS /
NOT_TESTED JSON and deliberately exits 1 because it does not exercise the full
product. Other exceptions also return nonzero; inspect its JSON and error text.

Regression commands:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend CRAZYMONKEY_ENABLE_EMAIL_SEND=false \
  SMTP_HOST= SMTP_PORT= SMTP_USERNAME= SMTP_PASSWORD= SMTP_FROM= \
  backend/.venv/bin/python -m pytest backend/tests -q -p no:cacheprovider
cd frontend
npm ls --depth=0
npm run typecheck
npm run lint
npm test -- --cache=false --configLoader native
npm run build -- --configLoader native --outDir /tmp/crazymonkey-qa-build-new
```

## SAFE GIT / MERGE READINESS

Only QA-owned changes are staged by explicit path, then `git diff --cached` and
`git diff --cached --check` are reviewed. No reset, clean, deletion, force push,
amendment or merge into main is used. Owner commits are preserved as ancestors.
The final response records the actual commit, remote equality, exact changed
paths and final divergence from refreshed main. No PR or main merge is performed.

**SAFE TO OPEN PR TO MAIN: YES for the explicitly scoped local offline V0**, with the validation and operational limits recorded above. This does not authorize
main merge, public deployment, hosted-model claims or real email sending.


## FILES INCLUDED IN THE QA COMMIT

- `README.md`
- `backend/app/relay/api.py`
- `backend/app/relay/contracts.py`
- `backend/app/relay/email_delivery.py`
- `backend/app/relay/models.py`
- `backend/app/relay/pdf_export.py`
- `backend/tests/run_qa_demo.py`
- `backend/tests/test_qa_demo_runner.py`
- `backend/tests/test_qa_email_configuration.py`
- `backend/tests/test_qa_pdf_calculation_label.py`
- `backend/tests/test_qa_relay_contracts.py`
- `backend/tests/test_qa_relay_references.py`
- `backend/tests/test_qa_snapshot_delivery.py`
- `docs/CURRENT_INTEGRATION_QA.md`
- `frontend/src/App.integration.test.tsx`
- `frontend/src/App.tsx`
- `frontend/src/api/httpReviewAdapter.test.ts`
- `frontend/src/api/httpReviewAdapter.ts`
- `frontend/src/api/mockReviewAdapter.test.ts`
- `frontend/src/api/mockReviewAdapter.ts`
- `frontend/src/components/EmailDialog.tsx`
- `frontend/src/components/FindingDetail.tsx`
- `frontend/src/components/ReviewSummary.tsx`
- `frontend/src/types.ts`

All pre-existing owner changes were preserved and committed by their owners. The
remaining QA changes are explicitly owned, guarded against concurrent modification,
and included above. Generated QA inputs, exports and renderings stay outside Git.
