# QA Summary

Audit date: 5 September 2026. Repository: `YaoSunHello/CrazyMonkey`. Branch: `Leo`.
Audited implementation baseline: `88b90a3` (`migrate: add ATLAS ingestion core`).

**QA STATUS: bounded hardening complete; intended V0 demo is not implemented.**

- Tests run: **71 test methods, all passing; 0 failures, 0 errors, 0 skips**. Baseline was 13 tests; 58 QA tests were added. Final root run: 0.283 seconds inside unittest.
- Failures found: **32 tracked finding groups** — 26 current-tree corrections and the six unresolved findings below. Counts group independent causes, not individual failing subcases; the temporary CSV regression introduced and repaired during QA is excluded from the baseline defect count.
- Failures fixed: **26 current-tree defects** (19 ingestion, 6 contract groups, 1 documentation hygiene correction); see the register. Historical documentation exposure is separately retained as R5.
- Failures remaining: **6 finding groups: 2 Critical, 2 High, 2 Medium.**
- No real email was sent, no model credentials were required, and no private financial documents were used.
- Only this repository's committed implementation was tested. Concurrent untracked Relay/frontend files in the original checkout were preserved and excluded.

The requested fetch/switch/rebase was completed on `Leo`. A separate clean checkout
of the existing `Leo` branch avoided modifying the original checkout's untracked
work. GitHub initially exposed only `main`; `Leo` appeared during the initial sync
and then resolved to the baseline above. No other branch was created. No code was
imported from `retinapeg/YLOOKUP` or another implementation.

Read: root README, backend README, ATLAS README, all `docs/` and handoff files.
There is no committed `AGENTS.md`; the supplied QA brief and user instructions
governed this pass.

## Implemented scope and test evidence

The baseline implements PDF/XLSX/CSV source normalization, Pydantic record
contracts, synthetic source generation, and `GET /health`. Its own ATLAS handoff
explicitly excludes orchestration, analyst/challenger execution, deterministic
verification, workflow API integration, review UI, exports and email.

The original suite passed **13/13** before changes. That was insufficient coverage:
the initial ingestion attack suite reproduced 15 failing assertions/subcases and
3 errors across 15 methods; the initial model attack suite reproduced 50 failing
subcases across 17 methods. Additional tests reproduced filename, formula,
evidence-ID, resource-budget and documentation failures before their fixes.
Subcases are not counted as separate test methods in final totals.

| Requested category | Actual execution and outcome |
| --- | --- |
| 1. File ingestion | Exercised blank/hidden/merged/multi-row/reordered/spacer XLSX layouts, formulas and errors, dates, currency strings and thousand-unit labels, duplicates/case/whitespace, corrupt packages, unknown files; CSV delimiters/BOM/quoting/ragged rows/header collisions/limits; multi-page, empty/image-only/encrypted/corrupt PDF, repeated text, contradictory clauses and extraction limits. Expected rejection is a typed `IngestionError`; partial extraction is explicit. |
| 2. Financial correctness | Contract tests exercise Decimal precision, null/zero/negative amounts, nonfinite values, negative tolerance, reversed dates, currencies and cross-record agreement. Actual arithmetic, rounding, annual-versus-quarterly interpretation and override applicability are BLOCKED by R1. |
| 3. Provenance | Exact source strings, file identity/hash, sheet/cell, PDF page/raw quote/offsets, CSV locators and reference integrity tested. Unsupported and CANNOT_VERIFY records remain representable. Authentication against original bytes remains R2. |
| 4. Primary-agent failure | Wrong-investor references and inconsistent record values are rejected by contracts. Wrong fund/rate, missed/future override, stale evidence and unsupported model claims cannot be tested against an absent primary agent (R1). |
| 5. Red team | No runnable reviewer to test PASS/CHALLENGE/INSUFFICIENT_EVIDENCE or independent canonical-value protection. Synthetic fixture records are not execution evidence (R1). |
| 6. Repair loop | No orchestrator or repair loop to test the one-repair limit or NEEDS_HUMAN_REVIEW outcome (R1). |
| 7. Output router | No router to execute the five supplied task prompts, ambiguity handling or reason generation (R3). |
| 8. Output files | Generated *source fixtures* open with openpyxl/pypdf, and actual normalized QA JSON files re-open against their Pydantic contracts. No product XLSX/PDF/DOCX/JSON/HTML result exporter exists to test (R3). Framework docs HTML is not a financial output. |
| 9. Email package | No recipient/subject/body/attachment packaging implementation; missing-recipient and failed-export behavior are blocked. The static fixture has an empty recipient and false send authorization (R3). |
| 10. API | Real ASGI calls test health, OpenAPI, documentation HTML and clean 404/405 responses. Proposed workflow URLs all return generic route-level 404, not implemented case/file validation (R3). |
| 11. Demo | New-directory source generation, ingestion and JSON round-trip executed. Full pipeline stops at normalization; no runtime LP03/PASS/CANNOT_VERIFY result or delivery package (R1–R3). |
| 12. Unseen input | Three independently generated multi-file packs, nine files total, pass extraction/round-trip checks with changed terminology, numbers, investors, layouts and source order. Financial outcomes remain unverified. |
| 13. Public hygiene | Tracked-file inventory, common credential signatures and all three baseline commits inspected without printing matched secrets. Current personal workstation paths removed. Historical copies remain R5. |

`COMPLETE` describes extraction completeness, not financial validity or proof that
a file is relevant. `NEEDS_CONFIRMATION` is retained for unfamiliar filenames.
Even a familiar filename cannot establish the meaning or truth of its contents.
No rate, currency or thousand-unit interpretation is inferred merely from a
successful normalizer return.

## Current-tree remediation register

Each row records an independently reproduced failure and a bounded correction.
The corresponding tests are in `backend/tests/test_qa_ingestion.py`,
`test_qa_models.py` or `test_qa_hygiene.py`.

| ID | Severity | Before / reproduction | Smallest correction |
| --- | --- | --- | --- |
| F01 | High | CSV data row has more fields than its header; trailing financial data disappears. | Reject with `CSV_ROW_WIDTH_MISMATCH`; never silently slice fields away. |
| F02 | High | Headers such as `amount,amount,amount_2` collide after suffixing. | Generate unique labels and therefore unambiguous locators/evidence IDs. |
| F03 | Medium | Oversized CSV header/data exceeds the csv parser's field limit; raw `_csv.Error` escapes. | Convert parser failures to `CSV_PARSE_FAILED` with a bounded message. |
| F04 | Medium | Unterminated quoted CSV field is accepted. | Strict CSV parsing rejects malformed quoting. |
| F05 | Medium | Oversized CSV header bypasses cell text bounds. | Enforce `CSV_HEADER_LIMIT`. |
| F06 | High | Blank/header-only CSV returns COMPLETE with no data evidence. | Return `EMPTY_CSV`. |
| F07 | Medium | Short CSV row is padded without signaling missing trailing values. | Preserve available data and report a warning/PARTIAL. |
| F08 | High | Blank/whitespace-only workbook returns COMPLETE with no useful evidence. | Return `EMPTY_XLSX`. |
| F09 | High | Text PDF containing a blank/image-only page reports COMPLETE. | Page-specific warning and PARTIAL extraction. |
| F10 | Medium | Lazy malformed PDF page tree raises outside the parser guard. | Return `PDF_PARSE_FAILED`; individual page failures remain visible. |
| F11 | High | PDF quote whitespace is collapsed while offsets refer to raw text. | Store the exact extracted block matching the page offsets. |
| F12 | High | Oversized file is read in full before its size is rejected. | Bound the read itself to the upload limit plus one byte. |
| F13 | High | CSV dialect inference discards leading field whitespace. | Preserve whitespace where the dialect permits it; any necessary dialect fallback must be explicit, not silent. |
| F14 | High | Excel error cells such as `#DIV/0!` report COMPLETE. | Retain the error and warn; extraction becomes PARTIAL. |
| F15 | Medium | `wallpaper.pdf`, `unavailable.xlsx` and unrelated substring names falsely confirm financial roles. | Match filename words/adjacent phrases; preserve known demo naming. |
| F16 | High | Byte-identical files with different filenames share evidence IDs despite distinct document IDs. | Include document identity in evidence IDs for all three formats; same-file stability retained. |
| F17 | High | Sparse workbooks allocate every blank cell in a huge rectangle despite a nonempty-cell limit. | Enforce a cumulative 1,000,000 visited-cell budget before worksheet iteration. `WORKBOOK_GRID_LIMIT` prevents the oversized scan. |
| F18 | High | Source model trimming changes raw values, legal worksheet names, filenames and storage keys. | Preserve exact source strings and exact locator components at field level. |
| F19 | High | Empty support, duplicate evidence IDs and evidence referring to another document/hash validate. | Require real support and enforce containing-document/hash/ID consistency. |
| F20 | Medium | Negative comparison tolerance validates. | Require tolerance ≥ 0; zero remains valid. |
| F21 | Medium | Reporting/effective dates can end before they start. | Reject reversed intervals. |
| F22 | High | Asserted findings accept missing amounts/currency/calculation/evidence; MATCH accepts failed verifier checks. | Validate assertion prerequisites and reference agreement, retaining honest CANNOT_VERIFY/UNSUPPORTED and legitimate failed discrepancy comparisons. |
| F23 | High | Snapshots accept duplicate IDs, absent/wrong-investor links, stale rule versions and contradictory canonical values. | Validate direct record references, status, value and currency consistency without inventing a financial verifier. |
| F24 | Medium | Handoff documents expose personal absolute workstation paths. | Replace current paths with non-personal workspace descriptions; add a hygiene regression. Historical limitation R5 remains. |
| F25 | High | Array/data-table formula objects are serialized as Python representations containing memory addresses; repeated extraction produces unstable evidence. | Return `UNSUPPORTED_XLSX_FORMULA` for these unsupported formula types. Ordinary formulas remain preserved without evaluation. |
| F26 | Medium | Corrupt XLSX central directory passes the ZIP signature check then raises raw `BadZipFile`. | Guard ZIP directory inspection and return typed `INVALID_XLSX`. |

Existing Decimal financial types already reject NaN and positive/negative infinity.
They were retained rather than replaced. Negative and zero amounts remain valid
data. No arithmetic is delegated to binary floats by these contract fixes.

Independent review also caught and reproduced a temporary CSV hardening regression:
valid fields with separator spaces before opening quotes were rejected. This was
repaired before final validation; comma-containing, simple quoted and multiline
cases now pass. The final implementation uses the standard CSV parser for both
interpretations, preserves compatible raw whitespace, and visibly warns when
quoted-field separator whitespace must be consumed.

Compatibility note: evidence IDs now incorporate the named document identity and
PDF quote IDs use exact extracted text. Regenerate previously cached normalized
artifacts together with their references; do not mix old and new evidence-ID sets.
New model checks intentionally reject internally inconsistent payloads. Array/data-table
formulas are explicitly unsupported rather than silently misrepresented.

## Critical

### R1 — Executable financial review pipeline is absent

- **Reproduction:** Inspect `backend/app/main.py` and `backend/app/atlas/README.md`; run the QA demo command below. For a direct contract counterexample, load `snapshot()` from `backend/tests/test_qa_models.py`, set the calculation's `expected_amount` to `"1"` and `difference` to `"49999"`, and repeat those values in the finding. `ReviewSnapshot(**payload)` still accepts it.
- **Expected:** Derive `10,000,000 × 0.015 × 0.25 = 37,500`, compare against `50,000`, and return a `12,500` discrepancy supported by terms, identity and dates. Run independent challenge, at most one repair, and a final honest review status.
- **Observed:** There is no primary agent, challenger, deterministic fee verifier or repair orchestrator. Contracts validate a coherent wrong amount of `1`; fixture assertions are stored answers, not computed verdicts.
- **Likely cause:** Only the ATLAS foundation was migrated.
- **Demo risk:** The central financial correctness claim cannot be demonstrated. Wrong fund/rate/override timing and annual/quarterly mistakes are not independently detected.
- **Recommended fix:** Complete and integrate the missing verification/orchestration layer in a separate feature assignment; retain these adversarial inputs as its acceptance cases. Do not promote static fixture PASS labels into runtime claims.

### R2 — Cited content is not authenticated against source bytes

- **Reproduction:** Load the same model test `snapshot()`, change a finding source ref's `original_value` to `"invented content"` without changing its internally matching document/hash, and construct `ReviewSnapshot`. It validates.
- **Expected:** Verify that the actual referenced file/sheet/cell or PDF page/span contains the cited content; otherwise CANNOT_VERIFY/INSUFFICIENT_EVIDENCE or human review.
- **Observed:** Structural links are now checked, but self-consistent invented content remains accepted. A source hash string alone does not prove the claimed value.
- **Likely cause:** No runtime component reopens/resolves original sources when checking an agent's proposed evidence.
- **Demo risk:** Unsupported financial conclusions can look fully sourced despite correct-looking IDs and hashes.
- **Recommended fix:** Bind proposed evidence to the normalizer's trusted evidence records/original bytes inside the missing verification layer. Requires integration, not another schema-only assertion.

## High

### R3 — Workflow API, output decision, deliverables and email packaging are absent

- **Reproduction:** ASGI `POST /upload`, `POST /extract`, `POST /normalize`, and `GET /exports/not-a-case` each return `404 {"detail":"Not Found"}`. Inspect the tracked frontend (README only) and source modules.
- **Expected:** Executable workflow endpoints; sensible XLSX/PDF/DOCX/JSON/HTML selection with a reason; real openable chosen outputs; recipient/subject/body/attachment packaging and controlled failures without requiring email credentials.
- **Observed:** Only health and framework docs endpoints exist. No router/exporter/package or review UI is available. No product output file was produced by this QA run.
- **Likely cause:** These components were not part of the committed migration.
- **Demo risk:** No upload-to-delivery demo, output-download path or email-ready package. Missing-file, invalid-case, agent/verifier failure and export-failure handling cannot be verified at an unimplemented API.
- **Recommended fix:** Integrate the existing team's intended components under their real contracts, then run all five output prompts, open the actual selected files, and exercise packaging failure paths. This is outside bounded QA fixes.

### R4 — Parser work before application limits has no hard memory/time bound

- **Reproduction:** Inspect `_normalize_xlsx`: both `load_workbook(..., read_only=False)` calls occur before workbook shape/cell budgets. Inspect `_normalize_pdf`: `extract_text()` executes before character limits. A safe sparse test initially expanded one stored cell to 100,000 objects from a 4,840-byte XLSX; F17 now prevents scans above the aggregate grid budget. This is bounded amplification evidence, not a maximum-size crash test.
- **Expected:** Uploaded compressed files cannot consume disproportionate RAM/CPU before an application budget takes effect.
- **Observed:** Upload, ZIP, row/column, scan-grid and text limits help, but do not impose a strict parser-process memory or execution deadline. XLSX object loading and PDF stream decompression still happen first.
- **Likely cause:** In-process eager parser APIs.
- **Demo risk:** Adversarial compressed inputs may stall or exhaust the demo process. No destructive stress test was run on the shared machine.
- **Recommended fix:** Add bounded preflight and an isolated parser worker with explicit resource/time limits, or carefully validated streaming extraction. Documented rather than introducing an architectural rewrite during QA.

## Medium

### R5 — Historical commits retain personal workstation paths

- **Reproduction:** `git show 88b90a3:docs/handoffs/atlas.md` and `git show e2ec62a:docs/handoffs/leo-relay-fixture.md` contain the earlier absolute source-workspace paths. Avoid copying their values into new logs or public reports.
- **Expected:** Public repository material avoids personal workstation identifiers.
- **Observed:** Current files are sanitized and regression-protected, but historical Git objects retain the two originals.
- **Likely cause:** Literal local paths in the original migration handoffs.
- **Demo risk:** No functional failure; residual public personal metadata.
- **Recommended fix:** Repository owner decides whether historical removal is warranted. No history rewrite or force push was performed, per the user's explicit constraints.

### R6 — Mutable record assignment can leave an invalid object after rejection

- **Reproduction:** Create `record = Finding(**finding())` using the model test helper, then assign `record.expected_value = None`. Catch the `ValidationError`; `record.expected_value` is nevertheless `None`, and `model_dump()` will serialize it. The complete snapshot revalidation rejects that invalid content.
- **Expected:** A rejected edit must not leave a canonical asserted record invalid.
- **Observed:** Pydantic after-validator assignment failure can leave the attempted field value in the mutable object. Nested edits also do not automatically rerun parent snapshot validation.
- **Likely cause:** Mutable models with assignment validation are not transactional updates or deeply immutable snapshots.
- **Demo risk:** A future review/red-team handler that catches an edit error and reuses the same object could serialize inconsistent state. There is currently no such workflow endpoint.
- **Recommended fix:** At the future mutation boundary validate a fresh candidate snapshot and replace canonical state only after success. Do not add a broad frozen-model refactor before the consuming workflow exists.

## Low

No separate unresolved low-severity finding. Dependency versions are currently
unpinned; the tested versions below record this run's environment rather than a
promise that every future installation is identical.

## API results

| Request | Observed |
| --- | --- |
| GET `/health` | 200, `{"status":"ok"}` |
| POST `/health` | 405, clean JSON |
| GET unknown resource | 404, clean JSON |
| GET `/openapi.json` | 200, parseable OpenAPI documenting health |
| GET `/docs`, `/docs/oauth2-redirect`, `/redoc` | 200, expected HTML |
| POST `/upload`, `/extract`, `/normalize` | 404, route absent |
| GET `/exports/not-a-case` | 404, route absent; not proof of case-ID validation |

No raw traceback was present in these responses. Tests execute the actual ASGI
app in process; they do not claim a deployed server or browser integration test.

## Unseen input packs

| Case | Different source data/layout | Verified result |
| --- | --- | --- |
| `sterling_thousands` | Fictional AX-17; GBP 8.4m/31,500 expressed as 8,400/31.5 thousand units; merged banner, blank cover, spacer column, hidden notes, Excel date, duplicate display names; two-page agreement; CSV → XLSX → PDF. | All three files normalize; raw unit labels and cells retained; no automatic thousand-unit interpretation or financial verdict claimed. |
| `dollar_vertical` | Fictional BX-92; USD 2.75m; parentheses credit; vertical key/value rows; future 1% concession against current 2%; veryHidden terms; formula/error/zero cells; semicolon/BOM CSV; PDF → CSV → XLSX. | All files normalize; formula/error warnings visible; raw negative/currency/date/percentage strings preserved. No override applicability verdict. |
| `euro_reordered` | Fictional cx-504/CX-505; EUR 3.5m; fee 9,187.50; reordered columns, zero row, string and Excel dates, mixed case, missing concession document, contradictory 1.40%/1.05% clauses; XLSX → PDF → CSV. | All files normalize and unfamiliar roles remain NEEDS_CONFIRMATION; conflicting/missing terms retained, not resolved or silently invented. |

For each pack, source XLSX/PDF files were opened by their real parsers, monetary
source anchors were checked, normalized JSON was reopened and validated, and
reverse source order produced identical per-file evidence. These fixtures do not
duplicate the normal demo field layout or read its expected-answer file.

## Reproduction commands and environment

From the repository root, install the existing backend requirements in an isolated
environment. The test suite itself uses `unittest`; no new runtime dependency was
added by these changes.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend .venv/bin/python backend/tests/run_qa_demo.py --output outputs/qa-new-run
```

Choose a new output directory for each demo attempt; the runner refuses to reuse
an existing directory. It deliberately exits **1** while full-demo status is FAIL,
even if every implemented ingestion step passes. Its `qa_demo_result.json` records
the exact boundary, file list, warnings, counts and timings. QA artifacts remain
under ignored `outputs/`; generated source/QA JSON files are not product outputs.

Test environment: Python 3.12; Pydantic 2.13.5, FastAPI 0.141.1, Starlette 1.6.0,
openpyxl 3.1.5, pypdf 6.10.0, reportlab 4.4.9, pandas 2.2.3,
pdfplumber 0.11.9, python-multipart 0.0.32, uvicorn 0.52.4. The local QA venv
reused bundled site packages; runtime dependency requirements were not changed.

## DEMO READINESS

**FAIL for the requested complete V0.**

Source generation, extraction, source metadata and QA JSON round-trip pass.
There is no executable path to independently derive LP03's expected **£37,500**,
its **£12,500** discrepancy from **£50,000**, one clean PASS and one CANNOT_VERIFY,
then select/generate output formats and build the email package.

Full-demo completion time is **not available because it cannot complete**.
Measured generation/ingestion timing is recorded separately below and must not
be described as full-pipeline latency. Source-fixture output and stored expected
answers do not satisfy the missing financial review stages.

Final clean-directory run: `outputs/qa-final-20260905/qa_demo_result.json`.

| Measured operation | Result |
| --- | --- |
| Whole QA runner process, including Python imports | 0.577371 seconds; exit 1 as intended for full-demo FAIL |
| Synthetic generation + all 17 source normalizations + JSON round-trips | 0.069363 seconds |
| Standard pack, 8 files | 0.025330 seconds for normalization/round-trip |
| Sterling unseen pack, 3 files | 0.006442 seconds |
| Dollar unseen pack, 3 files | 0.006315 seconds |
| Euro unseen pack, 3 files | 0.005515 seconds |
| Product result files / email package | None; implementations absent |
| Full V0 completion latency | Not available; no full pipeline to execute |

The standalone runner's JSON artifact was reopened and its contents checked,
including all 17 documents and the explicit absent stages. Timings are one local
run of synthetic inputs, not throughput or production-performance benchmarks.

## What Leo should test manually

1. Run the full unittest command from a clean dependency environment.
2. Run the QA demo into a new output directory; confirm its explicit FAIL boundary and inspect source-linked normalized JSON.
3. After the team integrates the missing stages, run the normal source pack and all three unseen packs through the actual UI/API. Confirm monetary units, identity, effective dates, independent calculation and missing-evidence behavior.
4. Check PASS/CHALLENGE/INSUFFICIENT_EVIDENCE, one-repair maximum and unresolved human-review outcome without canonical values being overwritten by a reviewer.
5. Run the five output requests, open every actually selected result file, and verify email package fields/attachment existence with missing-recipient and export-failure cases. Keep actual sending optional.
