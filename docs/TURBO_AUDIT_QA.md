# Turbo Audit and verified replay validation

Validated on 2026-09-05 on branch `Leo`. ATLAS implementation files were unchanged.

## Test evidence

```bash
PYTHONPATH=backend:backend/tests .venv/bin/python -m pytest backend/tests -q
```

Result: **403 passed, 229 subtests passed**, with one existing Starlette/AnyIO
deprecation warning. This includes 23 verified-replay tests, the existing ATLAS,
runtime and RELAY suites, Gemini SDK transport tests, all ten DSL operations,
parallel discovery/verification, precision-boundary regressions, and workbook
copy safety. `pip check` reported no broken requirements.

Replay tests prove that both deterministic executors run again, zero model
clients are constructed, all referenced evidence and source hashes are checked,
patch proposals are minted again, fresh corrected workbooks open successfully,
the Audit Trail is present, and original workbook bytes are unchanged. Changed
sources, missing evidence, corrupted saved results/plans/proposals, and unsupported
financial inputs are rejected. CLI tests cover `replay` and `list` output.

The replay fixtures have explicitly mocked model provenance and are created
only inside temporary test directories. They are not live Gemini audit cases.

## Observed local LP03 run

```bash
PYTHONPATH=backend .venv/bin/python -m app.fast_audit run \
  --input /tmp/crazymonkey-atlas-fixtures \
  --instruction "Find and repair material financial discrepancies." \
  --mode SYNTHETIC_DEMO \
  --apply-verified-fixes \
  --output outputs/turbo-demo-local
```

The existing pack yielded 8 normalized files and 128 evidence records. Seven
checks were scheduled, with peak verification concurrency of seven. Results:
3 matches, 1 discrepancy, 2 cannot-verify checks and 1 review-required anomaly.
The conflicting LP04 fee base and missing LP06 agreement remained withheld.

LP03 was recomputed from the original workbook base, PDF rate and period factor:
`10000000 × 0.015 × 0.25 = 37500.00`. The reported value was `50000`, giving a
`12500.00` difference. The generated
`outputs/turbo-demo-local/Administrator_NAV_Q3_2026_FIXED.xlsx` reopened with
`Investor Fees!F6 = 37500` and the eight specified Audit Trail columns. Original
and corrected-file hashes were rechecked against the audit result.

Measured pipeline timings for this run:

| Stage | Seconds |
|---|---:|
| Ingestion | 0.0799 |
| Investigation | 0.0520 |
| Verification | 0.0783 |
| Red team | 0.0002 |
| Patch | 0.0468 |
| Total | 0.2620 |

This was explicitly `SYNTHETIC_DEMO`, with **zero Gemini calls**. These timings
exclude provider latency and do not establish a live or serial-baseline speedup.

## Live and unseen status

The requested first live command with `--save-case lp03-demo` was attempted. It
normalized the original pack, then failed visibly because this execution process
has no `LLM_API_KEY`, `LLM_BASE_URL` or `LLM_MODEL`. No credential values were
printed, no synthetic fallback was selected, and no `outputs/cases/lp03-demo`
case was created. The standalone live smoke test also skipped because its key
was absent. A real Gemini-backed audit and subsequent saved-case demo remain
unverified until that process environment is configured.

The independently generated unseen two-file pack was run with the same Turbo
command in explicit synthetic mode. It yielded 35 evidence records, zero
discovered checks, and `CANNOT_VERIFY: No reliable financial relationship was
discovered`. No correction was generated. Its new terminology exceeds the
bounded offline discovery vocabulary; this is an observed abstention, not proof
of live semantic generalization.

See [FAST_AUDIT.md](../backend/app/runtime/FAST_AUDIT.md) for the live `run`,
`replay` and `list` commands and case-file format.
