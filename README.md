# CrazyMonkey

[![Ylookup Sponsor](brand/ylookup/ylookup-badge.svg)](https://www.ylookup.ai/)
![Privacy First](https://img.shields.io/badge/Privacy-First-111827?style=for-the-badge)
![Private Markets](https://img.shields.io/badge/Private_Markets-Fund_Data-0F766E?style=for-the-badge)
![Claude](https://img.shields.io/badge/Claude-AI_Extraction-D97757?style=for-the-badge&logo=claude&logoColor=white)
![Codex](https://img.shields.io/badge/Codex-Build_Agent-000000?style=for-the-badge&logo=openai&logoColor=white)
![Encode](https://img.shields.io/badge/Encode-Hackathon-2563EB?style=for-the-badge)

CrazyMonkey is a data administrator and data engineer for private-market workflows.

It takes messy fund documents, detects their data structure, extracts modelable data, verifies whether the numbers and mappings can be trusted, and flags missing information before it becomes analysts problem.

## The Problem

Private-market analysts and fund-ops teams still spend days turning administrator output into usable data. They manually screen PDFs and spreadsheets, copy values into workbooks, rebuild mapping tables, and only later discover that some information was missing, unmatched, or impossible to verify.

The painful part is not only extraction. It is knowing:

- which data is present
- which structure the files follow
- which values tie back to the source
- which mappings are unresolved
- which checks passed or failed
- which questions cannot be answered yet

That work can take 5-6 days before the data is ready for modelling or review.

## What CrazyMonkey Does

CrazyMonkey is built as a controlled data-quality pipeline. It can ingest private-market source material such as PDFs, Excel workbooks, images, and folders, then produce structured output for downstream modelling and review.

The end goal is to answer a defined set of business questions from the uploaded data, while clearly separating:

- answers supported by source-cited data
- information that is missing
- rows that are unresolved
- checks that failed
- next actions for a human reviewer

The product is deliberately conservative. It should not invent a match, silently fill a missing field, or mark a row as complete when the data does not support that conclusion.

## Agent Pipeline

The data agents work as a staged pipeline:

```text
1. Detect
-> 2. Extract
-> 3. Resolve
-> 4. Verify and Emit
```

**1. Detect**

Identify document type, file structure, account, currency, reporting period, relevant tables, and the business workflow the input belongs to.

**2. Extract**

Read rows, values, narratives, dates, balances, entities, and source citations from the original documents.

**3. Resolve**

Map extracted values against reference data such as legal entities, counterparties, investors, project codes, deals, positions, and chart-of-account tables.

**4. Verify and Emit**

Run deterministic checks, classify output as trusted or unresolved, generate a review queue, and emit a production-grade dataset only where the evidence supports it.

## What The Output Shows

CrazyMonkey's output is not just a cleaned spreadsheet. It is a validation package:

- model-ready rows
- source document and page references
- mapping status per row
- `PASS`, `FAIL`, `UNRESOLVED`, or `CANNOT_VERIFY` check results
- data-quality summary
- blocked export rows
- human review queue
- suggested next steps

At business level, the final dashboard should answer:

- What data did we receive?
- What business questions can we answer from it?
- How confident are we in those answers?
- Which numbers link back to the source?
- Which mappings are incomplete?
- What must a human collect, confirm, or escalate next?

## Failure Classification

The pipeline separates failure into three categories.

| Type | Meaning | Product behavior |
|---|---|---|
| Pipeline failure | The system could not process the files or complete a required stage | Should be rare; retry, log, and escalate to engineering |
| Data failure | Source data is missing, inconsistent, unmatched, or does not source | Flag clearly in the review queue and block unsafe export |
| Human follow-up | The answer requires more context, documents, or business judgement | State the missing information and suggest the next action |

This distinction matters because a missing investor mapping is not the same as a broken pipeline. It is useful business information that should be surfaced early.

## Current Demo Cases

The repository includes anonymised Ylookup hackathon datasets and two active backend profiles.

| Profile | Purpose | Spec |
|---|---|---|
| `journal-entries` | Convert bank statement PDFs into journal-ready transaction rows | [`docs/backend-model-evaluation.md`](docs/backend-model-evaluation.md) |
| `pipeline-validation` | Produce a validation package showing trusted rows, blocked rows, checks, and audit trail | [`docs/business-case-2-model-pipeline-validation.md`](docs/business-case-2-model-pipeline-validation.md) |

The first dataset is:

```text
samples/01-bank-statements-to-journal-entries
```

It contains seven bank statement PDFs and a reference workbook. The workflow tests the core product thesis: extract rows, resolve mappings, verify arithmetic, and keep unresolved cases visible.

## Why This Matters For Fund Managers

CrazyMonkey gives fund managers and LP teams a pre-screening layer before data enters a model or investment review.

Instead of waiting until the end of a manual process to discover that a file is incomplete, the pipeline detects the relevant structure against the business request upfront. It explains what is usable, what is missing, and who needs to provide more information.

The practical value is:

- fewer manual copy-paste cycles
- fewer late-stage review surprises
- clearer data-quality evidence
- faster escalation to the right party
- structured data ready for modelling

## Repository Map

```text
backend/     agent loop, extraction kits, verification, scoring, API surface
frontend/    fund-review UI and frontend integration work
profiles/    workflow definitions for journal entries and pipeline validation
samples/     anonymised Ylookup hackathon datasets
examples/    recorded backend outputs for replay and demo
docs/        business cases, frontend contract, validation plans
brand/       sponsor and project brand files
```

## Run Locally

Backend:

```bash
uv sync
cd backend
uv run python -m app.cli verify
uv run python -m app.cli profiles
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Demo Message

CrazyMonkey turns messy private-market documents into source-cited, verified, model-ready datasets.

It does not claim every row is clean. It proves which rows can be trusted, shows which rows cannot, and gives the human reviewer a clear path to complete the work.
