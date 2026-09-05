# Samples

The pipeline runs on the organisers' anonymised dataset
**`01-bank-statements-to-journal-entries`**: seven bank statement PDFs across four currencies and
four legal entities, plus the 15-sheet working file that turns them into journal entries.

## The data is not committed

The dataset is anonymised client work. Its own README says it is *"safe to hand to contestants"*,
which is not the same as safe to publish in a public repository, so it is held out until an
organiser confirms otherwise. `.gitignore` covers `samples/statements/` and `samples/workbook/`.

## Drop it in

Unzip `Ylookup Hackathon Datasets.zip` (pinned in the event Discord) and copy dataset 01 across:

```
samples/
  statements/   the seven *.pdf files from 01-bank-statements-to-journal-entries/statements/
  workbook/     Bank statement to journal entries - working file (anonymised).xlsx
```

Then, from the repository root:

```bash
uv sync
uv run pytest            # the verifier's tests
```

Tests that need the samples skip cleanly when they are absent, so a clone without the data still
runs green rather than erroring.

## What the seven statements contain

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

## The imperfections are deliberate

The organisers preserved the original files' unmatched rows exactly — 52 of the 100 rows have no
counterparty match at all, 30 project codes do not resolve, 4 positions do not resolve, and 3 rows
are flagged for review. Quoting their README: *"They are the difficulty of the exercise, not defects
to clean up."*

That is why a check has three outcomes rather than two. Those rows are `UNRESOLVED`: parsed
correctly, but with no match in the reference data. They are handed to a human with a citation, not
guessed at and not reported as failures.
