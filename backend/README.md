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
uv run pytest                                   # 14 tests
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
| `python -m app.cli agent --account GBP_3252` | Let the model write the parser and satisfy the verifier |
| `python -m app.cli replay` | Replay the last recorded agent run, no model needed |

Progress goes to stderr, JSON to stdout, so `... > out.json` gives a clean file and a readable log.
Exit code 1 on any `FAIL`.

## Layout

```
app/
  ingestion/statements.py   pdfplumber → rows, with page + bbox on every value
  verification/checks.py    the checks. No LLM, no sandbox, no network
  kit/statement_kit.py      uploaded into the sandbox for the agent to build on
  sandbox.py                Daytona (disposable) or a local subprocess
  llm.py                    one streamed completion
  agent.py                  the write → run → verify → retry loop
  trace.py                  the event stream, and its terminal renderer
  cli.py                    entry point
tests/                      run offline, no credentials needed
```

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

Not committed — see [`../samples/README.md`](../samples/README.md). Tests that need it skip
cleanly, so a clone without the dataset still runs green.
