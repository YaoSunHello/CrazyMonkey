# Backend Model Evaluation Plan

This plan turns the Ylookup business case into a concrete backend test target.

## Business Case Focus

CrazyMonkey should not try to produce an investment recommendation. The demo should prove that the backend can transform messy private-markets operating documents into modelable, source-cited, reviewable data.

The best first test case is:

```text
samples/01-bank-statements-to-journal-entries
```

Reason: it is small enough for a hackathon demo, has PDFs as messy input, has a verified workbook as reference output, and includes deliberate unmatched rows. This tests the most important product promise: extract what can be trusted, flag what cannot.

## Step 1 Backend Test

### Input

Use the seven PDFs in:

```text
samples/01-bank-statements-to-journal-entries/statements/
```

Use the workbook as reference truth:

```text
samples/01-bank-statements-to-journal-entries/workbook/Bank statement to journal entries - working file (anonymised).xlsx
```

Relevant workbook sheets:

- `Process`
- `Staging Sheet`
- `DIU`
- `Allocation Rule`
- `CoA`
- `Account Map`
- `Bank Account Report`
- `Legal Entity Master List`
- `Investor Master List`
- `Vendor Master List`
- `Vendor Codes`
- `Project Code Report`
- `Deal & Position Master List`
- `Related Party Master`

### Expected Backend Output

The backend should return a structured JSON payload with these sections:

```json
{
  "run_id": "string",
  "document_set": "bank_statements_to_journal_entries",
  "source_files": [],
  "statement_rows": [],
  "mapping_results": [],
  "journal_entries": [],
  "checks": [],
  "review_queue": [],
  "summary": {}
}
```

Each extracted transaction row should include:

```json
{
  "source_file": "string",
  "source_page": 1,
  "account_short_code": "string",
  "currency": "EUR",
  "transaction_date": "2026-03-31",
  "value_date": "2026-03-31",
  "raw_narrative": "string",
  "amount": 123.45,
  "direction": "debit|credit",
  "counterparty_raw": "string|null",
  "counterparty_match": {
    "status": "MATCH|UNRESOLVED|FAIL",
    "matched_name": "string|null",
    "confidence": 0.0
  },
  "project_code_match": {
    "status": "MATCH|UNRESOLVED|FAIL",
    "matched_code": "string|null",
    "confidence": 0.0
  },
  "classification": "investment|vendor_payment|related_party_transfer|investor_movement|internal|review",
  "source_citation": {
    "page": 1,
    "snippet": "string"
  }
}
```

## Acceptance Criteria

### 1. Extraction Coverage

The backend should extract the statement rows from the seven PDFs and preserve source file/page references.

Minimum target for demo:

- Extract at least 90% of statement transaction rows visible in the PDFs.
- Every extracted row must carry `source_file` and `source_page`.
- Every extracted amount must preserve sign or debit/credit direction.

Hard fail:

- Output contains financial values without a source reference.
- Output changes amounts, dates, or currencies without flagging a transformation.

### 2. Counterparty Matching

The backend must report match outcomes honestly.

Reference condition from the sample README:

- 52 of 100 staging rows have no counterparty match.

Minimum target for demo:

- Return explicit `MATCH`, `UNRESOLVED`, or `FAIL` for every row.
- Do not force all rows to `MATCH`.
- Produce an unresolved counterparty count close to the reference workbook.

Hard fail:

- Any unmatched counterparty is silently assigned to a clean master-list name.
- The model returns a boolean-only `matched: true/false` with no reason or source.

### 3. Project Code Resolution

Reference condition from the sample README:

- 30 project codes in the staging sheet do not resolve to the project code report.

Minimum target for demo:

- Return explicit project-code resolution status per transaction.
- Put unresolved project codes into the review queue.

Hard fail:

- Missing or unresolved project codes are treated as valid matches.

### 4. Classification

The model should classify rows into operationally useful buckets:

- `investment`
- `vendor_payment`
- `related_party_transfer`
- `investor_movement`
- `internal`
- `review`

Minimum target for demo:

- Classify every extracted row.
- Any classification below the confidence threshold must become `review`.
- `review` rows should include a reason.

Hard fail:

- Low-confidence rows are exported as final journal entries without review status.

### 5. Journal Entry Generation

The backend should generate two journal lines per valid transaction batch where mapping is sufficient.

Minimum target for demo:

- Generate journal entries only for rows that pass required mappings.
- Preserve a link from each journal line back to the extracted statement row.
- Exclude or separately stage `UNRESOLVED` rows.

Hard fail:

- Journal entries are generated from unresolved counterparties, unresolved project codes, or failed checks without an exception flag.

### 6. Deterministic Checks

The model must not grade itself. The backend needs deterministic checks after extraction.

Required checks:

- Amount sign and currency are present.
- Source citation exists for each financial value.
- Required mapping status is not missing.
- Debit/credit journal lines balance per batch.
- Unresolved rows are excluded from final export or marked as exceptions.

Hard fail:

- A missing input defaults to `MATCH`.
- A non-footing journal batch is marked as passed.
- A check result has only `true/false` instead of `MATCH`, `FAIL`, `UNRESOLVED`, or `CANNOT_VERIFY`.

## Red-Team Prompts

Use these to test whether the backend model fabricates answers:

1. Ask for a counterparty that does not resolve to the master list.
   - Expected: `UNRESOLVED`, with raw narrative and source citation.
2. Ask why a generated journal line exists.
   - Expected: source statement row, mapping chain, and journal rule.
3. Ask for a fund/entity/period not uploaded in the run.
   - Expected: refusal with missing input listed.
4. Ask whether the output is IC-ready.
   - Expected: no investment conclusion; only data quality and exception summary.
5. Ask whether every row matched.
   - Expected: no; report exact matched/unresolved/failed counts.

## Demo Success Definition

For the first backend demo, success is not perfect extraction. Success is:

- The pipeline reads real messy PDFs.
- It creates structured rows.
- It shows source citations.
- It identifies unresolved mappings.
- It generates only safe journal entries.
- It produces an exception queue a human can review.

The strongest demo story is:

```text
Messy bank statements -> extracted transactions -> mapping status -> safe journal entries -> exception list
```

