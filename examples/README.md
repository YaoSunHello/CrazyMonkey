# Example output

Two real runs over the seven bank statements in
[`../samples/01-bank-statements-to-journal-entries`](../samples/01-bank-statements-to-journal-entries),
committed so the output can be read without running anything.

Same documents, same passes, same checks — two different envelopes. That is the
point of them being here together: if the second one had needed code rather than
a JSON file, the profile split would not be real.

| File | Profile | Specified by |
|---|---|---|
| `batch-20260905-191130-journal-entries.json` | `journal-entries` | [`../docs/backend-model-evaluation.md`](../docs/backend-model-evaluation.md) |
| `batch-20260905-191924-pipeline-validation.json` | `pipeline-validation` | [`../docs/business-case-2-model-pipeline-validation.md`](../docs/business-case-2-model-pipeline-validation.md) |

Both: **7 of 7 statements accepted, 100 rows, every pass green on its first
attempt.** Model was Gemini Flash; each statement ran in its own disposable
Daytona sandbox, five at a time.

## Reading one

```jsonc
{
  "batch": "20260905-191130",
  "profile": "journal-entries",
  "accounts": [
    {
      "account": "GBP_3252",
      "run_id": "...",          // the recorded run, replayable
      "accepted": true,
      "envelope": { ... }       // the profile's own output shape
    }
  ]
}
```

Every row carries the page it was read from and the narrative it came from, so
any number can be traced back to the statement. Every resolution carries a
status — `MATCH`, `UNRESOLVED`, `CANNOT_VERIFY` — and a `MATCH` names the
reference list it came from.

## What the numbers say

Extraction is exact: **100 of 100 rows join to the human's working file** on
balance, and every arithmetic check passes on all seven statements.

Resolution is deliberately conservative. Against the human's own answers:

| | agent | human |
|---|---|---|
| counterparty read out of a narrative | 38 | 55 |
| counterparty matched to a list | 15 | 48 |
| project code matched | 27 | 70 |

It commits to less than the human does, and where it commits it is almost always
right: across 100 rows there were **six counterparty differences, and five of
them are the same company under a different list's name** —
`NI ABF I SCSp` against `Nordvik Infrastructure Advanced Bioenergy Fund I SCSp`,
`Trentbeck` against `Trentbeck Audit`. One genuine error: `Ranfjord` where the
human had `Ranfjord II`.

Classification agrees with the human on roughly half the rows. It is judgement
with no oracle, so it is reported as agreement and never as accuracy — the
workbook itself carries rows a person marked `Review`.

**Nothing is invented.** Every match names a row that exists in a named list,
every extracted string is a literal substring of its own document, and
everything else is `UNRESOLVED` or `CANNOT_VERIFY` with a citation.

## Reproducing them

```bash
cd backend
uv run python -m app.cli agent --all --parallel 5 --profile journal-entries
uv run python -m app.cli agent --all --parallel 5 --profile pipeline-validation
uv run python -m app.cli score --batch <batch-id>      # against the workbook
```

A model writes the parser each time, so the code differs run to run. What does
not differ is the verifier: nothing is emitted until the arithmetic holds.
