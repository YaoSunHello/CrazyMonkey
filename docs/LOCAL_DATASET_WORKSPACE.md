# Local dataset workspace

From this repository, double-click **Start CrazyMonkey.command**, or run:

```sh
./"Start CrazyMonkey.command"
```

The launcher builds the frontend, then starts the local application at
**http://127.0.0.1:8012/?workspace=pack**. Keep its Terminal window open while
using the workspace; press Control-C to stop it. If port 8012 is already in use
by your running CrazyMonkey server, use that server or stop it before launching
another instance.

## First-time dependencies

The launcher uses `backend/.venv/bin/python`, Node.js and npm. If the local
dependencies are missing, install them from this repository:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
(cd frontend && npm ci)
```

The launcher checks dependencies and runs `npm run build` on each launch. It
does not install dependencies, source a shell configuration file, or print keys.

## Gemini configuration

The application reads supported settings from the repository's local `.env`
file. Set `LLM_MODEL` to your Gemini model identifier and `API_KEY_AI` to your
Google Gemini API key. For a Gemini model, the application maps `API_KEY_AI` to
`LLM_API_KEY` and defaults `LLM_BASE_URL` to Google's OpenAI-compatible endpoint,
`https://generativelanguage.googleapis.com/v1beta/openai/`.

Explicit `LLM_API_KEY` and `LLM_BASE_URL` settings take precedence. The OpenAI
aliases `API_KEY_OPENAI` and `API_URL_OPENAI` are not used to authenticate or
route Gemini requests. Keep credentials in local configuration; do not put
them in uploaded documents or shared reports. A live review requires working
Gemini configuration and network access.

## Dataset and retained evidence

Select the folder **Ylookup Hackathon Datasets** in the pack workspace. Its
expected inventory, from source inspection, is **19 supported files: four XLSX
workbooks, eleven PDFs and four README files**. The expected workbook totals
are **32 sheets and 3,717,180 populated cells**; the PDFs contain **22 pages**.
Hidden `.DS_Store` files are not inputs. These are expected source counts, not
a claim that any particular import or live review completed successfully.
Check the workspace's actual import counters and per-file results for each run.

Each run retains uploaded source copies under
`outputs/local-packs/<run-id>/sources/`, with its SQLite evidence database and
saved run results in the same run directory. Original files in Downloads remain
unchanged. The full import stores source-bound workbook rows and all their cell
values, PDF page text, and Markdown/text chunks for later source drilldown.
Cell coordinates, duplicate headers and sheet names with trailing spaces remain
distinct. Numeric source strings are retained; spreadsheet formulas are not
evaluated by the importer.

## What the review means

Gemini receives bounded excerpts and import profiles, with source evidence IDs.
Full local ingestion does **not** mean Gemini has reviewed every row or cell.
Findings are **REVIEW_REQUIRED** and need human assessment against the retained
sources. Missing mappings and financial corrections are not resolved or applied
automatically. Reference workbooks and filenames containing “VERIFIED” are
comparison material, not proof of independent verification by this application.

Uploaded README instructions and transcript text are treated as source data.
Review results must distinguish source assertions from independently checked
facts. The existing NAV workflow remains available.

## Completed local run — 5 September 2026

Run `pack-20260905T164751-44cfb01f` completed with **19 of 19 files**, **19
successful Gemini requests**, no failed files, and **107.640 seconds** elapsed.
The configured model was `gemini-3.8-flash`. This was a live API run, not a
saved-response replay. Its 47 model findings remain `REVIEW_REQUIRED`.

An independent read of the retained SQLite evidence confirmed 19 documents,
32 sheets, 161,245 populated workbook rows, 3,717,180 cells, 22 PDF pages and
four Markdown chunks. All 19 original files and all 19 uploaded copies matched
the pre-upload hashes. All 85 finding evidence references resolved to their
respective source files. SQLite integrity checking passed.

Local evidence is saved in
`outputs/local-packs/pack-20260905T164751-44cfb01f/`: `result.json` contains file
reviews and safe API call metadata; `integrity_report.json` records the checks;
`original_source_hashes.json` records source provenance; `evidence.sqlite3` and
`sources/` retain the imported evidence. These files are ignored by Git.

This establishes successful import, live model execution and source integrity.
It does not establish an exhaustive financial audit of all imported rows.
