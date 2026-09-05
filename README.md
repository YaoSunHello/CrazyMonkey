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

## Phase 1 Pipeline (Built)

What exists today is Phase 1: a loop-engineered pipeline of agents that supervise each other through document ETL, rather than one model doing everything in a single pass.

A user states the intended outcome as a **declarative goal** for the run (which business question this batch answers, which profile/checks apply). From there the pipeline works in a supervised loop against reference master lists — resolving, classifying, and building out the dataset — until every row is either trusted or explicitly held out, then reconciles the result back to the fund manager / end user as the final answer.

```text
1. Detect
-> 2. Extract
-> 3. Resolve (looped against master lists, agent-supervised)
-> 4. Verify and Emit
-> Reconciled back to the fund manager
```

**1. Detect**

Identify document type, file structure, account, currency, reporting period, relevant tables, and the business workflow the input belongs to.

**2. Extract**

Read rows, values, narratives, dates, balances, entities, and source citations from the original documents.

**3. Resolve**

Loop against reference data — legal entities, counterparties, investors, project codes, deals, positions, chart-of-account tables — classifying and building out each row. One agent proposes, another checks; a row only advances once it clears, and a row that can't be resolved stays visibly unresolved rather than being forced through.

**4. Verify and Emit**

Run deterministic checks, classify output as trusted or unresolved, generate a review queue, and emit a production-grade dataset only where the evidence supports it.

The output of Phase 1 is a single artifact: a **structured, model-ready dataset** that is high-quality, validated against deterministic checks, and fully auditable back to its source documents.

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

## Vision: Phase 2 and Beyond

Phase 1 proves the core loop on one document type and three profiles. It is not the full product. The bullets below distinguish remaining roadmap work from the connected local V0 documented later in this README.

- **Wider document coverage.** NAV packs, portfolio reports, capital-call notices, and scanned or photographed statements (with an OCR fallback), not just bank statement PDFs.
- **Broader interactive review (roadmap).** The connected V0 now provides folder/file inventory, profile selection, bounded job progress, source-linked findings, separate human-review state, and only backend-supported downloads. A due-diligence questionnaire, broader row-edit/accept/reject workflows, and additional document families remain roadmap work.
- **A broader profile library.** One profile per business question a fund manager actually asks — see [`docs/business-case.md`](docs/business-case.md) for the due-diligence questions (mandate fit, track record, fees, legal/governance, operational quality) still to become profiles beyond `mandate-fit`, `journal-entries`, and `pipeline-validation`.
- **An in-context AI assistant.** A chat surface over a run's structured dataset that answers from the extracted data only, and explicitly says so when a question is out of scope — never fabricates an answer or a citation.
- **Cross-fund and cross-administrator comparison.** The mapping problem at portfolio scale: reconciling definitional drift (e.g. what "net IRR" means) across multiple GPs at once, not just one fund's statements.
- **Production hardening.** Auth, persistent run storage, audit-log retention, and cost/latency controls on the agent loop.

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

## Run the connected V0

See [BEACON](frontend/BEACON.md) for the browser workflow and API contract.
The existing profile-driven backend remains intact. The same FastAPI process
also mounts the ATLAS ingestion, verified runtime, BEACON, and RELAY routes
used by the browser.

For the complete browser and backend together, use the guarded launcher:

```bash
./scripts/start-v0.sh
```

It checks both ports before starting, never stops an existing service, and
shuts down only the two processes it started. If the default ports are already
occupied, choose unused ones explicitly:

```bash
CRAZYMONKEY_BACKEND_PORT=8030 CRAZYMONKEY_FRONTEND_PORT=4200 ./scripts/start-v0.sh
```

Open the printed frontend URL. The default **Profile workflows** workspace runs
the live local UI bridge: select **Bank statement validation**, upload one or
more original text PDFs, and select **Start review**. A reference workbook is
optional. The browser sends the selected bytes to FastAPI; ATLAS normalizes and
source-links each input before the existing statement parser and deterministic
verifier run. Results include the actual rows, arithmetic checks, exact original
source downloads, source hashes, human-review state, and a downloadable JSON
record.

This default bridge is deliberately labelled **Local deterministic**. It does
not run the model-backed resolution/classification passes, and the result
reports `agent_resolution: NOT_RUN` rather than implying otherwise. The
existing NAV review and RELAY export/email-draft surfaces remain available from
the workspace switch; replay data appears only when a reviewer explicitly opens
a recorded replay and is never a silent live fallback.

From the repository root, start the backend:

```bash
uv sync
uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

In a second terminal, start the frontend in live mode:

```bash
cd frontend
npm ci
VITE_API_MODE=live VITE_API_BASE_URL=http://127.0.0.1:8000 \
  npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:4173` for Profile workflows or
`http://127.0.0.1:4173/?workspace=nav` for NAV review. Use one backend worker for V0 because active
review state is process-local. In Profile workflows, accepted jobs, sources,
review state, and JSON artifacts are also process-local. In NAV review,
generated snapshots and exports are written under the ignored
`outputs/relay/` directory; real email sending is disabled by default and the
browser prepares a draft only. In live mode a backend failure is shown as
`Backend unavailable`; the browser does not substitute fixture results.

## Backend CLI

The profile-driven CLI remains available:

```bash
uv sync
cd backend
uv run python -m app.cli verify
uv run python -m app.cli profiles
```

## Demo Message

CrazyMonkey turns messy private-market documents into source-cited, verified, model-ready datasets.

It does not claim every row is clean. It proves which rows can be trusted, shows which rows cannot, and gives the human reviewer a clear path to complete the work.
