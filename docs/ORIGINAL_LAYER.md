# Original V0 layer

This entry point runs the original **ATLAS → runtime → BEACON/RELAY** NAV workflow
from this exact checkout:

`/Users/leonardaarons-ditson/Desktop/crazymonkey`

It uses backend port **8013** and frontend port **4174**. Existing servers on
8011 and 8012 remain running. The launcher uses Vite development mode, does not
rebuild `frontend/dist`, and does not install dependencies or edit local API
configuration. Each launch gets a separate RELAY output directory under
`outputs/original-layer-servers/`. Its Vite development cache is also stored in
that session directory, leaving `node_modules` unchanged.

## Start the original interface

Double-click `Start Original Layer.command`, or run:

```sh
cd '/Users/leonardaarons-ditson/Desktop/crazymonkey'
bash './Start Original Layer.command'
```

After both servers report that they are ready, open
**http://127.0.0.1:4174/?workspace=nav**. Keep the Terminal open. Control-C stops
the two child servers launched by this command. If either required port is
already occupied, the launcher stops without terminating its owner.

The default mode is **OFFLINE**, using the original bounded deterministic
interpreter with zero model calls. The original NAV interface remains intact;
its label says **Original V0 · offline** and the Full pack switch is hidden.

To enable the existing Gemini adapter for reviews you choose to start:

```sh
cd '/Users/leonardaarons-ditson/Desktop/crazymonkey'
bash './Start Original Layer.command' --live-model
```

This mode sends financial source evidence to **Google Gemini** when a review is
started. Server startup itself does not run an audit or make a model request.
Configuration stays in the backend's existing local environment. The UI label
**Original V0 · Gemini** describes the selected configuration; recorded model
calls and the result establish whether a particular analysis succeeded.

## Iterate the entire supplied folder

Use a separate Terminal while the interface remains open:

```sh
cd '/Users/leonardaarons-ditson/Desktop/crazymonkey'
PYTHONPATH=backend backend/.venv/bin/python -m app.legacy_folder \
  --input '/Users/leonardaarons-ditson/Downloads/Ylookup Hackathon Datasets' \
  --mode OFFLINE
```

The iterator attempts files individually through the original normalizer and
retains each outcome. A rejected file must remain in the report; it must not
silently disappear or cause later files to be omitted. Inspect the command's
reported output directory and result before treating anything as processed.
The CLI is a separate run from a review started in the NAV interface.
It runs independently in Python; the browser and HTTP servers do not need to be
running for the folder command to work. Each invocation creates a fresh output
directory under `outputs/legacy-folder/`. `--output /path/to/new-directory` can
choose that location explicitly; existing output directories are refused.

For a smaller repeatable selection, add one or more `--match` patterns relative
to the supplied input folder. Quote patterns so the shell does not expand them:

```sh
PYTHONPATH=backend backend/.venv/bin/python -m app.legacy_folder \
  --input '/Users/leonardaarons-ditson/Downloads/Ylookup Hackathon Datasets' \
  --mode OFFLINE \
  --match '01-bank-statements-to-journal-entries/*'
```

For one file, use its full relative path as the pattern:

```sh
PYTHONPATH=backend backend/.venv/bin/python -m app.legacy_folder \
  --input '/Users/leonardaarons-ditson/Downloads/Ylookup Hackathon Datasets' \
  --mode OFFLINE \
  --match '01-bank-statements-to-journal-entries/statements/20260331_NI_V_SCSP_CALDER_DKK_0541.pdf'
```

Replace `--mode OFFLINE` with `--mode LIVE_MODEL` only when you intend to send
source evidence to Gemini. Live transport failures, request-size limits and
unsupported evidence must remain visible; they are not successful model checks.

## What the old layer can establish

The original normalizer accepts text PDFs, XLSX and CSV. The supplied dataset has
19 meaningful files: 11 PDFs, four XLSX workbooks and four README Markdown files.
The Markdown files are unsupported by that normalizer. The three large
investor-loader workbooks exceed original workbook size limits; their exact
normalization failures must be retained. The old limits include 20,000 rows per
sheet, 100,000 populated cells per workbook, and one million scanned grid cells.

The original NAV workflow requires a NAV workbook, a governing LPA and an
investor register, with supported fee fields and source-linked terms. The supplied
bank-statement, loader and transcript folder does not become such a pack merely
by assigning those role labels. Missing LPA/register evidence should remain
**CANNOT_VERIFY** or an explicit unsupported outcome. Imported workbook rows are
not completed transaction mappings, generated journals or verified accounting.

The model adapter passes the complete normalized evidence for each selected file;
it does not silently sample or trim it. The existing 512 KiB model request limit
still applies, so the bank workbook's full normalized payload is too large for a
live request. This is reported as `MODEL_INPUT_TOO_LARGE` with zero provider calls.
The old verifier supports a narrow management-fee contract. Successful parsing
or a successful Gemini call does not broaden that contract.

The original API and UI remain synchronous: a review is created after processing,
and subsequent progress polling reports completed stages. This is not a live
stream of execution. RELAY exports preserve the resulting review snapshot;
no email is sent by this launcher or the folder command.

## Verified local execution — 5 September 2026

The launcher was executed in OFFLINE mode. Backend 8013 returned
`layer: ORIGINAL_V0`; frontend 4174 returned HTTP 200 and displayed
`Original V0 · offline`. The original synthetic review ran through its HTTP
workflow and displayed three matches, two discrepancies and one cannot-verify
finding. LP03 showed reported GBP 50,000, expected GBP 37,500 and difference
GBP 12,500. The separate full-pack server on 8012 stayed available, and the new
pack routes are absent from the original server.

The actual 19-file folder iteration is saved in
`outputs/legacy-folder/entire-pack-20260905/`:

| Outcome | Files |
|---|---:|
| Original runtime executed; `CANNOT_VERIFY` | 12 |
| Markdown unsupported by original normalizer | 4 |
| Original workbook limit rejected during streaming preflight | 3 |
| Worker crashes or timeouts | 0 |
| Source files changed | 0 |
| Model calls in this OFFLINE folder run | 0 |

All 19 files have persisted results and before/after source hashes. Twelve files
means eleven PDFs and the bank workbook. The three rejected workbooks reported
`WORKBOOK_CELL_LIMIT`, `WORKSHEET_DIMENSION_LIMIT` and
`XLSX_DECOMPRESSED_LIMIT`. All 19 original hashes were independently rechecked.
The loop completed, but none of these single-file tests establishes a verified
NAV review: governing LPA/register/NAV evidence is missing or separate.

A separate real Gemini test used only eight newly generated fictional ATLAS
control files, never this Ylookup folder. Its first request returned an invalid
response; the original pipeline's one allowed repair returned valid structured
output. Two provider requests were recorded. LP03 arithmetic was recomputed
correctly, but the deterministic verifier challenged the model's evidence
bindings, leaving the result `REVIEW_REQUIRED`. This proves the adapter can
contact Gemini and preserves failures; it is not a clean live acceptance pass.
Details are in
`outputs/original-layer-control/demo-06f2d0f69ecf/gemini_control_summary.json`.

Final regression checks passed: 468 backend tests plus 256 subtests, 37 frontend
tests, TypeScript and ESLint. The original ATLAS, V0 runtime and RELAY source
modules remain unchanged. `crazymonkey-main-fresh` was not accessed or modified.
