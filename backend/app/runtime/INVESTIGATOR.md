# Autonomous financial error investigator

The `audit` CLI discovers checks from a folder of original XLSX/PDF/CSV sources,
normalizes them through the existing ATLAS implementation, executes a bounded
verification DSL with Decimal, and independently challenges each proposed result.
It does not read expected-answer fixtures. It is separate from the existing V0
review/API pipeline and does not change its frontend, exports or email behavior.

## One-command audit

From the CrazyMonkey repository root, with backend requirements installed and
the Python environment activated:

```bash
PYTHONPATH=backend python -m app.runtime.audit \
  --input /path/to/files \
  --instruction "Find material financial discrepancies in this fund pack."
```

The command prints each check, its actual source cell/page, the Decimal
calculation, difference, final status and challenge result. A new directory under
`outputs/runtime-audit/` contains `result.json` and the ATLAS normalized documents.
Use `--output /path/to/new-output-folder` to select an empty output directory.
Outputs must be outside the input folder. Input JSON files, including fixture
manifests and expected-answer files, are never interpreted as evidence.

To generate the existing LP03 synthetic source pack once:

```bash
PYTHONPATH=backend python -m app.atlas.fixtures --output outputs/investigator-sources
PYTHONPATH=backend python -m app.runtime.audit \
  --input outputs/investigator-sources \
  --instruction "Find material financial discrepancies in this fund pack."
```

LP03 is computed as GBP 10,000,000 × 0.015 × 0.25 = GBP 37,500;
reported GBP 50,000 minus expected GBP 37,500 = GBP 12,500, `DISCREPANCY`,
red team `PASS`. These numbers appear here as observed acceptance results, not
as inputs to the investigator. A regression changes the contractual rate to
1.7% and verifies a new runtime answer of GBP 42,500 despite a stale answer sidecar.

## Planning and execution

`planner.py` inspects evidence before selecting a check. With a configured model,
the model receives the complete bounded ATLAS evidence set, the user's instruction,
and the Pydantic plan schema. It selects source IDs, terms and operations, and
explains the relationship. It cannot supply a final answer or executable Python.

Without credentials, output is explicitly `OFFLINE_DISCOVERY`. This conservative
fallback recognizes a finite vocabulary and discovers annual-charge calculations,
quantity × unit-price checks, and gross-less-deductions checks only where their
operands exist. It does not claim unrestricted financial or legal interpretation.
An unknown vocabulary/layout can produce `CANNOT_VERIFY` with no checks.

`contracts.py` defines a small DSL: multiply, add, subtract, divide, min and max.
Operands are named evidence inputs or nested operations. Plans are limited to
20 checks, 16 inputs per check, 48 expression nodes and depth 6. The reported
amount cannot participate in its expected-value expression. `executor.py` uses
Decimal with 50-digit working precision and no `eval`, `exec`, generated code,
network access or file writes. There is no need for a Python sandbox subprocess
because the runtime never executes model-authored code.

Source numeric tokens must resolve to exact ATLAS evidence. Workbook/CSV inputs
use their full cell values; prose tokens must be exact bounded substrings. Formula
caches, nonfinite values, unsupported scaling and ambiguous numbers are rejected.
Money rounds half-up to 0.01. The default absolute tolerance is 0.01; `--tolerance`
sets a trusted run-level comparison threshold, not an inferred contractual term.

`challenger.py` has an independent arithmetic implementation and independently
reads source scope, dates, rate clauses and contradictions; it never calls the
planner or executor. It checks investor, fund, currency, effective date, base,
factor, operand roles, omitted competing terms and expected missing agreements.
With a model, a separate review call receives the original evidence and proposed
plan/calculation, with no analyst conversation. A model-proposed relationship
outside the offline semantic templates requires that separate review as well as
all deterministic structural/arithmetic checks. Model approval cannot override a
deterministic contradiction. All cited review IDs must resolve to ATLAS evidence.

One model repair batch is allowed for challenged checks. The repair must retain
the check ID, entity, fund and reported source. It is re-executed and challenged.
Unresolved findings remain `CANNOT_VERIFY`; failed proposals are retained separately
from accepted calculations. No repair loop runs without a model.

## Runtime model configuration

The CLI automatically uses `OPENAI_API_KEY` if present, otherwise
`ANTHROPIC_API_KEY`. Set `OPENAI_MODEL` or `ANTHROPIC_MODEL` to override the default
provider model. `--offline` explicitly disables calls. Credentials come from the
process environment; the CLI does not load `.env` files. No credentials were
available during the recorded acceptance run, so no live model call was verified.

The adapter sends normalized financial evidence to the selected provider's fixed
official HTTPS endpoint. It excludes local storage paths, rejects redirects and
custom base URLs, and never logs keys or raw error responses. Each request/response
is limited to 512 KiB; output is limited to 4,096 tokens. Socket operations have a
30-second timeout and response reads check elapsed time; this is not a strict
whole-run wall-clock guarantee. Malformed/truncated responses fail closed without
silent fallback to fixture answers. Transport tests use mocked responses.

## Blind heldout case

A separate agent authored a workbook/PDF pair and withheld its oracle until the
first investigator output was saved. The input filenames, terminology, investor,
values and layout differ from LP03. Reproduce the source pair using only existing
Python dependencies:

```bash
python backend/tests/runtime_unseen_factory.py --output outputs/investigator-heldout
PYTHONPATH=backend python -m app.runtime.audit \
  --input outputs/investigator-heldout/input \
  --instruction "Find material financial discrepancies in this fund pack."
```

Give the investigator only `input/`. The sibling `control/oracle.json` and
`control/input_hashes.json` are evaluation material and never runtime evidence.
The first blind run normalized 2 files / 39 evidence records, generated **zero
checks**, and returned **CANNOT_VERIFY**. It missed the planted EUR 12,000 undercharge
(expected EUR 38,400; booked EUR 26,400). This is the explicitly permitted abstention,
not successful unseen error detection. No post-reveal tuning is counted as blind success.

## Bounds and result interpretation

- At most 32 source files and 8,000 evidence records; provider requests may hit
  their byte limit earlier. Oversized packs require splitting, not silent truncation.
- Failed document ingestion or meaningful incomplete extraction prevents final
  certification of a partially read pack. Filename-role uncertainty alone does
  not establish or invalidate financial applicability; content must support it.
- Original file hashes are checked before planning and before accepting results.
  Evidence IDs and exact source references are resolved from the normalized store.
- `coverage` counts final generated checks. `cannot_verify` also records run-level
  discovery abstentions, so a zero-check run is not a clean financial report.
- Exit 0 means at least one verified check completed (including discrepancies).
  Exit 2 means no checks were accepted. Exit 1 means setup/execution failed.
- A `MATCH` applies to the specific tested relationship only. This bounded
  hackathon runtime does not certify a fund pack, determine legal enforceability,
  or prove there are no other discrepancies.

## Tests

```bash
PYTHONPATH=backend python -m unittest discover -s backend/tests -p 'test_*.py' -v
PYTHONPATH=backend python -m pytest -q backend/tests/relay
```

New tests cover LP03, changed source values, non-fee relationship discovery,
source mutation, unsupported inputs, Decimal arithmetic, DSL rejection,
unresolved IDs, one bounded repair, wrong investor/fund/currency, period and
rate conflicts, missing agreements, provider failures and heldout fixture isolation.
