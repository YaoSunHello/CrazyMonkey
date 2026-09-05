# Turbo Audit

Turbo Audit shares one normalized ATLAS evidence index across concurrent contract,
relationship, consistency and anomaly discovery. A finite Decimal DSL verifies
the proposed checks. Source applicability and independent review determine which
discrepancies can become correction proposals.

Run these commands from the repository root using the environment installed from
`backend/requirements.txt`.

For a new fictional demo pack, first generate the source files in an unused
directory (or substitute your existing source folder in the commands below):

```bash
PYTHONPATH=backend .venv/bin/python -m app.atlas.fixtures --output outputs/investigator-sources
```

## Live audit and corrected workbook copies

Configure `LLM_API_KEY`, `LLM_BASE_URL` and `LLM_MODEL` in the process environment.
The client requires all three variables. The base URL must be
`https://generativelanguage.googleapis.com/v1beta/openai/` (the trailing slash is
optional), and requests use the exact configured model. Credentials are never
accepted as command arguments or written into audit artifacts. A missing setting
or failed model request produces an error; it does not select a synthetic mode.

```bash
PYTHONPATH=backend .venv/bin/python -m app.fast_audit run \
  --input outputs/investigator-sources \
  --instruction "Find material financial discrepancies in this fund pack." \
  --apply-verified-fixes \
  --save-case lp03-demo
```

`run` defaults to `LIVE_MODEL`. Omit `--apply-verified-fixes` to calculate findings
and correction proposals without creating corrected workbooks. Successful live
runs with accepted findings and complete ingestion save a case under
`outputs/cases/<case-id>`; the ID is generated when `--save-case` is omitted.
Existing case IDs are rejected.

The output directory defaults to a fresh `outputs/fast-audit/<run-id>` directory.
Use `--output` to choose another output directory. Artifacts include `result.json`,
`evidence-index.json`, and, when requested and supported, new `*_FIXED.xlsx`
workbook copies. Each corrected copy contains an `Audit Trail` sheet recording
the exact original and replacement values, target cell, finding, reason and
evidence IDs. Original source files are hash-checked and remain unchanged.

## Explicit synthetic demonstration

```bash
PYTHONPATH=backend .venv/bin/python -m app.fast_audit run \
  --input outputs/investigator-sources \
  --mode SYNTHETIC_DEMO
```

This mode uses bounded local discovery and makes zero Gemini calls. It cannot
save a verified live case. Its results do not demonstrate live model discovery.

## Saved cases and replay

```bash
PYTHONPATH=backend .venv/bin/python -m app.fast_audit list

PYTHONPATH=backend .venv/bin/python -m app.fast_audit replay \
  --case outputs/cases/lp03-demo \
  --apply-verified-fixes
```

Replay is labelled `VERIFIED_REPLAY` and uses zero model calls. It reruns the
saved accepted deterministic checks against source evidence and relies on the accepted
semantic review saved with the case. It is not a new model investigation or a
new independent semantic review. A source-integrity mismatch stops replay.
`--output` selects a fresh destination; omitting `--apply-verified-fixes` leaves
corrections as proposals.

Every case contains `manifest.json`, `normalized_evidence.json`,
`verification_plan.json`, `verifier_result.json`, `red_team_result.json`,
`patch_proposal.json`, `trace.json`, and `source_hashes.json`. The manifest binds
the files and accepted plans with SHA-256 hashes. Replay resolves every cited
evidence ID, checks source hashes, executes both deterministic financial
verifiers again, and mints fresh patch proposals through the same safety gates.
Saved numerical results serve as consistency checks; they are never substituted
for recomputation. Previously withheld findings remain historical review context
and cannot become corrections during replay.

Changed originals stop replay with `SOURCE_CHANGED_REQUIRES_FRESH_AUDIT`.
Missing originals also require a fresh audit. There is no source-change override.
Each replay creates a fresh output directory, so the corrected workbook can keep
its `<original_stem>_FIXED.xlsx` name without replacing an earlier copy.

The case store retains operational call metadata and concise source-linked
review decisions. It stores no provider credentials or hidden chain of thought.
`list` reports `VERIFIED` only for a readable case whose saved files and currently
available sources pass integrity checks; its findings count is the number of
accepted discrepancies.

## Compatibility

The earlier Turbo command without a subcommand remains supported. It defaults
to `LIVE_MODEL` and applies supported fixes to new copies:

```bash
PYTHONPATH=backend .venv/bin/python -m app.fast_audit \
  --input outputs/investigator-sources
```

The serial investigator also remains available:

```bash
PYTHONPATH=backend .venv/bin/python -m app.runtime.audit \
  --input outputs/investigator-sources \
  --mode LIVE_MODEL
```

Use `run --help`, `replay --help`, or `list --help` on `app.fast_audit` to inspect
the current CLI options.

## Check interpretation and limits

- Contract and relationship discovery use Gemini through the OpenAI Python SDK.
  Parallel calls have explicit stage metadata. The client disables automatic
  retries and redirects and bounds requests to 512 KiB, responses to 1 MiB and
  generated output to 16,384 tokens. SDK errors are sanitized.
- Deterministic consistency discovery checks quantity times unit price, gross
  less deductions, explicit total/subtotal rows and unambiguous date ordering.
  A same-day inclusive period does not fail a strict date-ordering check. Totals
  cite at most 16 detail operands and do not count subtotal rows again in grand
  totals. Missing, formula-backed, invalid percentage or inconsistent currency
  values produce diagnostics or withheld checks.
- A rate entered in a workbook is not contractual authority. Consistency
  discovery validates its numeric representation but does not calculate a
  contractual charge from the entered rate.
- Duplicate identifiers and repeated nonzero monetary values are scoped to the
  same document, sheet and table header. Repeated-amount signals require at
  least three distinct entities. These are `REVIEW_REQUIRED` findings and never
  establish a correction, even when equality is deterministically confirmed.
- Each deterministic discovery helper returns at most 40 checks and 100 notes.
  Its vocabulary is finite. The DSL supports equality, inequality, addition,
  subtraction, multiplication, division, sums, percentages and date predicates.
  It never executes generated Python or accepts a model-supplied final answer.
- Conflicting relationships, incomplete evidence, unresolved applicability and
  missing review prevent a verified correction. Arithmetic success alone is
  not semantic approval. Reported coverage is limited to discovered checks.

The result records Gemini call metadata, measured stage durations, task intervals
and peak concurrency. These measurements describe that particular run; they do
not establish an unmeasured speedup against a serial baseline. Unit tests and
mocked SDK transport tests are not evidence of a successful live Gemini run.
