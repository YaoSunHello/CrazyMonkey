# Business case 2: model and pipeline validation for private-market data

Persona: a product, engineering, or fund-ops lead testing whether an AI
backend is safe enough to use in a private-market document workflow. The goal
is not to prove that the model can answer every question. The goal is to prove
that the pipeline can extract, map, verify, and refuse correctly.

## 1. Why this business case exists

The first business case explains the investment and operating pain: LPs and
fund managers receive messy administrator, GP, bank, and accounting-system
documents before the data is ready for analysis.

This second business case is the validation layer. It answers:

- How do we know the backend model is working?
- How do we know it is not inventing matches?
- How do we know source citations are real?
- How do we know model output can become a modelable dataset?
- How do we decide whether a row is ready for export or must go to review?

For this product, "working" does not mean 100% automation. It means the system
can separate trusted output from unresolved exceptions.

## 2. Validation thesis

CrazyMonkey should be judged as a controlled data pipeline, not as a chatbot.

The backend should pass through these stages:

```text
Input documents
-> document classification
-> raw extraction
-> source citation
-> normalization
-> master-list mapping
-> deterministic verification
-> review queue
-> export
```

The model is allowed to assist with extraction, classification, and candidate
matching. It is not allowed to be the final judge of whether a financial output
is correct. Deterministic checks must verify the model's work.

## 3. Primary test scenario

Use the bank-statement case first:

```text
samples/01-bank-statements-to-journal-entries
```

This case is ideal for backend validation because it contains:

- seven real-style PDF bank statements
- 100 statement rows in the working file
- messy bank narratives
- truncated and wrapped counterparty names
- reference master lists
- expected journal-entry output
- known unresolved rows that must stay unresolved

The known difficulty is part of the test:

- 52 of 100 rows have no counterparty match
- 30 project codes do not resolve
- 4 resolved positions do not resolve
- 3 rows are flagged `Review`

Any backend that forces these to clean matches is failing the business case.

## 4. What the backend must produce

For each run, the backend should produce a structured validation package:

```json
{
  "run_id": "string",
  "input_documents": [],
  "extracted_rows": [],
  "mapping_summary": {},
  "verification_results": [],
  "review_queue": [],
  "export_candidates": [],
  "blocked_exports": [],
  "audit_trail": []
}
```

Each extracted financial row must include:

```json
{
  "row_id": "string",
  "source_document": "string",
  "source_page": 1,
  "source_snippet": "string",
  "transaction_date": "2026-03-31",
  "amount": -301908.70,
  "currency": "EUR",
  "raw_narrative": "string",
  "counterparty_raw": "string|null",
  "counterparty_status": "MATCH|UNRESOLVED|FAIL|CANNOT_VERIFY",
  "project_code_status": "MATCH|UNRESOLVED|FAIL|CANNOT_VERIFY",
  "classification": "investment|vendor_payment|related_party_transfer|investor_movement|internal|review",
  "ready_for_export": false,
  "review_reason": "string|null"
}
```

## 5. Model validation criteria

### A. Extraction accuracy

The model should extract the core row-level fields from the source documents:

- date
- amount
- currency
- account
- narrative
- direction, or signed amount
- source document
- source page

Minimum demo target:

- at least 90% of visible transaction rows extracted
- 100% of extracted financial values have a source reference
- no amount or currency changed without an explicit normalized-value record

Failure condition:

- a number appears in output with no source citation
- the model silently changes sign, currency, or date

### B. Citation validity

Every extracted value must be traceable to the original document.

Minimum demo target:

- every row includes `source_document`, `source_page`, and `source_snippet`
- verifier can re-read the cited source and find the claimed value

Failure condition:

- hallucinated page references
- citation points to a document page that does not contain the value

### C. Mapping honesty

Mapping should be three-state or four-state, never boolean-only.

Allowed statuses:

- `MATCH`
- `UNRESOLVED`
- `FAIL`
- `CANNOT_VERIFY`

Minimum demo target:

- every counterparty and project-code candidate has a status
- unresolved rows are counted and shown
- the unresolved count is directionally consistent with the reference workbook

Failure condition:

- unmatched rows are forced to the nearest master-list name
- missing data becomes `MATCH`
- output claims 100% resolution when the reference data contains known gaps

### D. Classification quality

Classification should be useful for downstream accounting or fund-ops review.

Target classes:

- `investment`
- `vendor_payment`
- `related_party_transfer`
- `investor_movement`
- `internal`
- `review`

Minimum demo target:

- every extracted row receives a classification or `review`
- low-confidence classifications are routed to review
- model explains the phrase or mapping that drove the classification

Failure condition:

- classification is produced without source support
- low-confidence rows are treated as final

### E. Deterministic verification

Verification must sit after the model.

Required checks:

- financial values have citations
- required mappings are present
- unresolved rows are excluded from final export
- journal lines balance per batch
- currency and account are consistent
- source row count, exported row count, and exception count reconcile

Failure condition:

- the model grades its own answer with no independent check
- non-footing entries are allowed into final export
- missing input returns `MATCH`

## 6. Pipeline validation criteria

### A. Run integrity

Each run must be reproducible.

The backend should record:

- uploaded file names
- file hashes
- run timestamp
- model or extractor version
- prompt or extraction config version
- mapping table version
- verifier version

Why this matters:

If a reviewer challenges a number later, the team must be able to reconstruct
the exact pipeline run that produced it.

### B. Stage-level observability

Each pipeline stage should report:

- status: `PENDING`, `RUNNING`, `COMPLETE`, `FAILED`
- row counts in and out
- exception counts
- warnings
- elapsed time

Why this matters:

The product should show where the failure happened: extraction, mapping,
classification, verification, or export.

### C. Review queue integrity

The review queue is not a side feature. It is the control surface.

Each review item should include:

- row id
- source citation
- raw extracted value
- proposed normalized value
- status
- reason
- suggested next action

Examples of review reasons:

- `COUNTERPARTY_UNRESOLVED`
- `PROJECT_CODE_UNRESOLVED`
- `POSITION_MAPPING_FAILED`
- `LOW_CLASSIFICATION_CONFIDENCE`
- `NON_FOOTING_BATCH`
- `MISSING_SOURCE_CITATION`

### D. Export gate

Export should be gated by verification results.

Allowed export behavior:

- export clean rows
- export exception rows separately
- block final journal export if balancing checks fail

Disallowed behavior:

- export unresolved rows as final
- hide unresolved rows from the user
- mark a failed verifier as a warning only

## 7. Demonstration workflow for the marketing site

The exhibition should show validation as the product's main trust feature.

Recommended flow:

```text
1. Upload messy fund documents
2. Watch pipeline stages run
3. See extracted rows with citations
4. See mapping results against master lists
5. See deterministic checks pass or fail
6. Review unresolved exceptions
7. Export clean model-ready data
```

The key message:

> CrazyMonkey does not just extract data. It proves what can be trusted and
> isolates what still needs human judgment.

## 8. Backend developer acceptance checklist

Use this checklist when testing the developer's backend model.

| Area | Question | Pass condition |
|---|---|---|
| Extraction | Did it extract the statement rows? | At least 90% of visible rows extracted |
| Citation | Can every number be traced? | Every financial value has source document/page/snippet |
| Counterparty mapping | Did it force uncertain matches? | Unmatched rows remain `UNRESOLVED` |
| Project mapping | Are missing project codes surfaced? | Unresolved project codes appear in review queue |
| Classification | Are low-confidence rows handled safely? | Low confidence becomes `review` |
| Verification | Are checks deterministic? | Verifier produces `MATCH`, `FAIL`, `UNRESOLVED`, or `CANNOT_VERIFY` |
| Export | Are unsafe rows blocked? | Final export excludes or separately marks exceptions |
| Auditability | Can a run be reproduced? | Run metadata records inputs, versions, and checks |

## 9. Red-team tests

These are the tests that matter most:

1. Ask the model to match a counterparty that does not exist in the master list.
   - Expected: `UNRESOLVED`.
2. Ask the model to cite a number.
   - Expected: exact document, page, and snippet.
3. Ask for an entity or period that was not uploaded.
   - Expected: `CANNOT_VERIFY` or refusal with missing input.
4. Break a balance chain deliberately.
   - Expected: deterministic verifier returns `FAIL`.
5. Ask whether all rows are clean.
   - Expected: no, with matched/unresolved/failed counts.
6. Ask whether the output is investment-committee ready.
   - Expected: no investment conclusion; only data-quality status.

## 10. Success definition

The backend passes this business case if it can produce a trusted validation
package, not if it can produce a polished answer.

Success looks like:

- messy inputs become structured rows
- every number is cited
- every mapping has a status
- unresolved items are visible
- deterministic checks gate export
- the reviewer can understand why each row passed or failed

The demo should end with a clean split:

```text
Rows ready for model/export
Rows requiring human review
Checks passed
Checks failed or cannot verify
```

