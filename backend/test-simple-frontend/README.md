# Run viewer — throwaway

One static HTML file for looking at the JSON in [`../../examples/`](../../examples)
and judging whether it would actually help the person doing the work.

**Not the product frontend.** That is [`../../frontend/`](../../frontend) (BEACON).
This shares nothing with it — no build, no dependencies, no network — and is meant
to be deleted once it has answered the question.

## Open it

Double-click `index.html`, then drag either file from `examples/` onto the page:

- `batch-…-journal-entries.json`
- `batch-…-pipeline-validation.json`

The same page renders both. The two profiles name things differently
(`statement_rows` against `extracted_rows`, `checks` against
`verification_results`), so the loader normalises on the way in and the rendering
never branches — which is also a quiet check that the two envelopes really are
two views of one run.

A `file://` page cannot fetch a sibling file, so drag-and-drop is the path that
always works. If you happen to be serving the directory, `?src=<path>` also works.

## What to look at

- **the split** — ready for export against needs a person, top of the page
- **the check report** per statement. `15/15 links hold` is the line that makes
  the rest credible
- **click any row** for its evidence: the page it was read from, the narrative as
  the bank wrote it, and which reference list each match came from
- **the review queue**, ordered by exposure rather than by file order

Three things it deliberately does not smooth over: a `MATCH` that cannot name its
source list renders as an error rather than as clean; `UNRESOLVED` and
`CANNOT_VERIFY` look different, because "we looked and found nothing" is a
person's problem and "the document named nobody" is not; and if the page's own
export gate ever disagrees with the run's envelope, it says so at the top instead
of showing a number nobody can reconcile.
