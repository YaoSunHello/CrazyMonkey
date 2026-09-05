# CrazyMonkey

  [![Ylookup Sponsor](brand/ylookup/ylookup-badge.svg)](https://www.ylookup.ai/)
  ![Privacy First](https://img.shields.io/badge/Privacy-First-111827?style=for-the-badge)
  ![Claude](https://img.shields.io/badge/Claude-AI_Extraction-D97757?style=for-the-badge&logo=claude&logoColor=white)
  ![Codex](https://img.shields.io/badge/Codex-Build_Agent-000000?style=for-the-badge&logo=openai&logoColor=white)
  ![Private Markets](https://img.shields.io/badge/Private_Markets-Fund_Data-0F766E?style=for-the-badge)
  ![Encode](https://img.shields.io/badge/Encode-Hackathon-2563EB?style=for-the-badge)
  

CrazyMonkey is a hackathon product for fund managers and investment teams. It helps transform messy investment documents into clean, model-ready datasets.

See [BEACON](frontend/BEACON.md) for the frontend and review workflow.

The MVP focuses on the part of the research pipeline before IC materials: taking PDFs, statements, NAV packs, portfolio reports, and similar files, then extracting traceable structured data that analysts can validate and export.

## Run the connected V0

The existing profile-driven CLI/backend remains available. The same FastAPI
process now also mounts the ATLAS, verified-runtime, BEACON, and RELAY routes
used by the browser.

From the repository root:

```bash
uv sync
uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd frontend
npm ci
VITE_API_MODE=live VITE_API_BASE_URL=http://127.0.0.1:8000 \
  npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:4173`. Use one backend worker for V0 because active
review state is process-local. Generated review snapshots and exports are
written under the ignored `outputs/relay/` directory. Real email sending is
disabled by default; the browser prepares a draft only.

## Product Agenda

- Ingest messy documents such as PDFs, financial statements, NAV packs, and investor reports.
- Extract raw text, tables, periods, entities, metrics, and source references.
- Normalize values into consistent schemas for modeling.
- Give users a review workflow for low-confidence fields.
- Export clean CSV, Excel, or JSON datasets.

## MVP Workflow

1. Upload a messy fund document.
2. Classify the document type.
3. Extract tables and key financial metrics.
4. Normalize fields, dates, units, currencies, and entities.
5. Review extracted values with source snippets or page references.
6. Export a modelable dataset.

## Team Agenda

### Teammate 1: Document Ingestion

- Own upload and file handling.
- Extract text and tables from PDFs.
- Add OCR fallback for scanned documents if time allows.
- Preserve source metadata such as file name, page, and table location.

### Teammate 2: Data Normalization

- Define canonical schemas for fund and portfolio data.
- Map messy labels to standardized metric names.
- Normalize dates, currencies, signs, units, and periods.
- Add validation rules and export formats.

### Teammate 3: AI Extraction

- Build prompts or extraction calls for document classification and key fields.
- Add confidence scoring and uncertainty flags.
- Return source-linked values for human review.
- Avoid summary-only output; focus on auditable numbers.

### Teammate 4: Frontend and Demo

- Build the upload and processing dashboard.
- Display extracted tables and review states.
- Add edit, accept, reject, and export actions.
- Own demo story, submission flow, and fallback demo assets.

## Suggested Repo Structure

```text
backend/
  app/
    ingestion/
    extraction/
    normalization/
    schemas/
frontend/
  src/
samples/
outputs/
```

## Hackathon Milestones

- Hour 0-2: Repo setup, schema definition, sample documents.
- Hour 2-6: File upload, raw extraction, first JSON output.
- Hour 6-12: AI extraction and normalization pipeline.
- Hour 12-18: Review UI and export workflow.
- Hour 18-24: Polish demo, README, slides, and submission.
