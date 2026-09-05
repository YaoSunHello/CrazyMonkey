# Backend

Bank statement PDFs in, journal-ready transaction rows out — and nothing is emitted until a
deterministic verifier says the arithmetic holds.

## Why it works this way

From the fund manager interview in the dataset (`03-call-transcripts/call-1`):

> "There is a quality control gap where **nobody reads it and asks whether this number foots to
> that number.** … Nobody at the administrator is doing that, and that is what creates the review
> burden."

> "**I cannot trust any number I get from them, so I have to check everything.**"

So the product is not "extract the data". It is "extract the data **and prove it**". The proof is
the statement's own running-balance chain: each row's balance minus its amount must equal the next
row's balance. If the parse is right the chain closes; if it is wrong it does not. That makes it an
oracle — the pipeline can tell whether it did well without being told.

## Quick start

```bash
uv sync
uv run pytest                                   # 91 tests
cd backend
uv run python -m app.cli verify                 # all seven statements
```

Expect `38 passed · 0 failed · 4 unresolved`.

## Commands

| Command | What it does |
|---|---|
| `python -m app.cli verify` | Parse and check every statement |
| `python -m app.cli verify --account GBP_3252` | Just one |
| `python -m app.cli verify --account GBP_3252 --corrupt 3` | Damage a row on purpose; watch the verifier reject it |
| `python -m app.cli parse --account GBP_3252` | Print the rows with their PDF citations |
| `python -m app.cli profiles` | List the tracks a run can be started on |
| `python -m app.cli agent --account GBP_3252` | Let the model write the parser and satisfy the verifier |
| `python -m app.cli agent --all --profile pipeline-validation` | Every statement, on the other track |
| `python -m app.cli emit --run <id> --profile <id>` | Present a recorded run in a profile's envelope |
| `python -m app.cli replay` | Replay the last recorded agent run, no model needed |

## Profiles

A profile is a JSON document in [`../profiles/`](../profiles) saying what a use
case is. The engine knows nothing about banks; it mounts what the profile
declares, asks a model for a script, runs it, and judges it with checks the
profile names. Four keys and nothing else:

```
inputs   which documents and reference tables to mount
passes   per pass: the prompt, the kit, and the checks that judge it
output   how the finished run is projected into this case's envelope
label    what a person picking between tracks should see
```

Two ship today, over the same seven statements:

| Profile | Emits | Specified by |
|---|---|---|
| `journal-entries` | statement rows, mapping results, journal entries, review queue | [`../docs/backend-model-evaluation.md`](../docs/backend-model-evaluation.md) |
| `pipeline-validation` | export candidates, blocked exports, mapping summary, audit trail | [`../docs/business-case-2-model-pipeline-validation.md`](../docs/business-case-2-model-pipeline-validation.md) |

The second **adds no Python**. It inherits the first's inputs, passes and checks
and overrides one key, `output`. That is the test the design has to keep
passing: a use case that needs code is a use case the abstraction has not
understood.

`GET /api/profiles` serves the same list, so a frontend can offer them as tracks
rather than hard-coding one.

### Passes

A profile splits its work into passes, and each pass is the same
write → run → verify → retry loop with its own kit, checks and attempt budget:

| Pass | Writes | Judged by |
|---|---|---|
| `extract` | rows from the PDF | the six arithmetic checks in `verification/checks.py` |
| `resolve` | counterparty, project code, classification | the parameterised checks in `verification/generic.py` |

Separate budgets matter: a resolution that will not come good cannot spend the
extraction that already did.

### Nudges

A profile can carry guidance on *how* to go about something — never on what
counts as correct. Nudges are scoped, because advice about a check nobody failed
is noise competing with the failure that needs fixing: always, for named
documents, or only on a retry where a named check failed.

The firewall is mechanical rather than conventional: `verification/` imports
nothing from `profiles.py`, so a nudge cannot disable a check or move a
tolerance.

Progress goes to stderr, JSON to stdout, so `... > out.json` gives a clean file and a readable log.
Exit code 1 on any `FAIL`.

## Layout

```
profiles/*.json             what a use case is — inputs, passes, output
app/
  profiles.py               load them, and compose the layered prompt
  ingestion/statements.py   pdfplumber → rows, with page + bbox on every value
  reference/tables.py       any spreadsheet → named lookup tables
  verification/checks.py    the arithmetic checks
  verification/generic.py   provenance · membership · completeness · vocabulary
  kit/statement_kit.py      uploaded into the sandbox for the extraction pass
  kit/reference_kit.py      …and for the resolution pass
  emit.py                   a finished run → whichever envelope a profile asks for
  sandbox.py                Daytona (disposable) or a local subprocess
  llm.py                    one streamed completion
  agent.py                  the write → run → verify → retry loop
  trace.py                  the event stream, and its terminal renderer
  cli.py                    entry point
tests/                      run offline, no credentials needed
```

`kit/reference_kit.py` is imported by both the sandbox and the host. One `Table`
implementation means a lookup that succeeds in the agent's code cannot fail in
the verifier over a different whitespace rule — a silent divergence there is
exactly the class of bug this pipeline exists to catch.

**`verification/` imports nothing from `agent.py` or `sandbox.py`, and never will.** Its tests pass
with `openai-agents` and `daytona` uninstalled. That is the mechanical guarantee that the agent is
judged by exactly the code the CLI runs, rather than by a second implementation that has drifted.

## Three check outcomes, not two

| | meaning | who acts |
|---|---|---|
| `PASS` | the check holds | nobody |
| `FAIL` | arithmetic or structure is wrong | the pipeline retries |
| `UNRESOLVED` | parsed fine, but no match in the reference data | a person, with a citation |

The third state is the point. 52 of the 100 rows in the supplied dataset genuinely have no
counterparty match, 30 project codes do not resolve, 4 positions do not. The organisers preserved
those on purpose — *"they are the difficulty of the exercise, not defects to clean up."* A boolean
would have to either block output that is legitimately complete, or quietly launder missing
evidence into a confident answer. Neither is honest.

## The agent loop

The model gets the statement text, a sandbox with a toolkit, and a verifier it cannot reach. It
writes `parse.py`; we run it; the same checks the CLI runs decide whether the output is acceptable.
On rejection the exact failures — row index, expected, actual, delta, citation — go into the next
attempt. Four attempts, then it stops.

Retries are per **attempt**, not per turn. A turn-by-turn tool loop was tried first and was the
wrong shape here; `app/agent.py` documents why, with the measurements.

## Configuration

Copy `.env.example` to `.env` at the repository root. Notes that will save you an hour:

- **`LLM_ENABLE_THINKING=false`.** The served model reasons before answering. Left on, it produced
  **120,000 characters of reasoning in 28 minutes and zero lines of code**. Off, the same prompt
  returns working code in ~80s.
- **Streaming is not optional.** The endpoint is behind Cloudflare, which closes an idle origin
  request at ~100s with a 524. Streamed, the first token arrives in under a second.
- **The User-Agent decides whether you are served at all.** No header, `Python-urllib` and the
  OpenAI SDK's own string are all rejected 403. `app/llm.py` sets it in the one place every request
  passes through.
- **`DAYTONA_TARGET`** must be set, or sandbox creation is rejected unless the organisation has a
  default region.

Without `DAYTONA_API_KEY` the agent falls back to a local subprocess, which has **no isolation** and
must be opted into explicitly with `--allow-local-execution`.

## Data

The pipeline runs on the organisers' anonymised dataset
[`01-bank-statements-to-journal-entries`](../samples/01-bank-statements-to-journal-entries):
seven bank statement PDFs across four currencies and four legal entities, plus the 15-sheet
working file that turns them into journal entries. It is committed to the repository, so a clone
runs the real thing with no extra setup:

```
samples/01-bank-statements-to-journal-entries/
  statements/   the seven *.pdf files
  workbook/     Bank statement to journal entries - working file (anonymised).xlsx
```

A local drop-in at `samples/statements/` is still honoured if one is present — the CLI and the
tests check the committed location first and fall back to it. Tests that need the statements skip
cleanly when neither is there, so a clone without the data still runs green.

See [`../samples/README.md`](../samples/README.md) for how the anonymisation works and why the
reversal keys must not travel with the datasets.

### What the seven statements contain

| File | Entity | Currency | Rows |
|---|---|---|---|
| `…_NI_A_B__FUND_II_CALDER_DKK_4319.pdf` | NI ABF II SCSP | DKK | 10 |
| `…_NI_A_B__FUND_II_CALDER_EUR_8102.pdf` | NI ABF II SCSP | EUR | 16 |
| `…_NI_ABF_I_SCSP_CALDER_EUR_0894.pdf` | NI ABF I SCSP | EUR | 16 |
| `…_NI_GMF_II_SCSP_CALDER_USD_4373.pdf` | NI GMF II SCSP | USD | 19 |
| `…_NI_V_SCSP_CALDER_DKK_0541.pdf` | NI V SCSP | DKK | 5 |
| `…_NI_V_SCSP_CALDER_EUR_030041.pdf` | NI V SCSP | EUR | 18 |
| `…_NI_V_SCSP_CALDER_GBP_3252.pdf` | NI V SCSP | GBP | 16 |

100 transactions, six business days, 23–31 March 2026.

### The imperfections are deliberate

The organisers preserved the original files' unmatched rows exactly — 52 of the 100 rows have no
counterparty match at all, 30 project codes do not resolve, 4 positions do not resolve, and 3 rows
are flagged for review. Quoting their README: *"They are the difficulty of the exercise, not
defects to clean up."*

That is why a check has three outcomes rather than two. Those rows are `UNRESOLVED`: parsed
correctly, but with no match in the reference data. They are handed to a human with a citation, not
guessed at and not reported as failures.
