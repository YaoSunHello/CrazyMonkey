# Run console

A small console for the runs the backend has already produced: **replay a recorded run**, read the
**report** it produced, and **start a new one**.

Not the product frontend — that is [`../../frontend/`](../../frontend) (BEACON). This shares nothing
with it: no build, no dependencies, no npm, no network. It reads `outputs/`, `examples/`,
`profiles/` and `samples/` by path and imports nothing from `app.*`, which is what lets the whole
thing live in one directory.

## Run it

```bash
python backend/test-simple-frontend/serve.py
```

It prints a URL and opens a browser. The left rail fills with every run under `outputs/runs/`,
newest first, grouped into the batches they ran in — `5 / 7` on a batch means five of its seven
statements were accepted.

| flag | |
|---|---|
| `--port 8080` | somewhere else |
| `--no-new-runs` | refuse to start runs at all; the console says so instead of offering it |
| `--no-open` | do not open a browser |

Opening `index.html` off the filesystem also works, but a `file://` page may not fetch its own
siblings, so it can only render a file you drop on it. `?run=<run id>` and `?src=<path>` both work
when it is served.

## Replay

Pick a run. It plays from that run's `trace.jsonl` — the same events
[`app/trace.py`](../app/trace.py) printed while it was running, in the same layout, so what you are
watching is the run rather than a retelling of it.

- **the stage rail** — extract → resolve → journal, one pip per attempt, green accepted, red
  rejected. The counters beside it tick up out of the events already played, so scrubbing backwards
  shows what was known at that point rather than the final total.
- **transport** — play/pause, 1× / 4× / 16× / all, and a scrubber over the event index.
- **collapsed time** — a run is twenty events inside a tenth of a second and then ninety seconds of
  the model writing code. Honoured literally the screen freezes; scaled uniformly the bursts smear.
  So gaps are capped and labelled: `⋯ model · generating extract.py · 107s collapsed`.
- **the code's own output** folds. While it is printing you see the last eight lines the way a
  terminal shows them; when it stops they fold to `⎿ 592 lines of output`, which opens.
- **every line is clickable.** The right-hand panel says what that step was, why it matters, and
  shows the raw event as recorded. On a verdict it explains each check by name.

At the end you get the run's card — accepted or rejected, rows, checks, attempts, elapsed — and a
button through to the report.

## The report

- **the chain** — `balance − amount = expected | next row | ✓`, all four columns. The product's
  claim is that the numbers foot; a reader who can see the subtraction does not have to trust
  anybody. Only a broken link is coloured, because a broken chain is a broken link.
- **transactions**, with the page each was read from and what each match resolved against.
- **journal entries**, grouped into batches, debits and credits side by side, with the balance
  stated per batch.
- **the checks**, three statuses kept apart — `PASS` holds, `FAIL` blocks output and is retried,
  `UNRESOLVED` means it parsed fine but a value has no match and a person decides. Each one opens
  its evidence, an explanation of what it tests, and **show this in the log →**, which jumps back
  into the replay at the verdict that produced it.
- **the review queue**, ordered by exposure — a 15.7m suspense row and a rounding gap are not equal
  work — with statement-level items last rather than first.

Three things it will not smooth over. A `MATCH` that cannot name its source list renders as an
error, not as clean. A **rejected** run's output is labelled as refused rather than presented as a
deliverable. And if the page's own export gate disagrees with the envelope's count, it says so at
the top instead of showing a number nobody can reconcile.

## Starting a run

The **New run** tab picks a statement and a profile, shows you the exact command, and only then
offers to run it — two steps, because a run spends model calls and takes about seven minutes.
`trace.jsonl` is written in one go at the end, so while it works you see the CLI's own output; when
the run directory lands, the console offers the real replay.

## Adding to it

| file | |
|---|---|
| `serve.py` | the API. Standard library only, imports nothing from `app.*` |
| `js/adapters.js` | three input shapes → one internal shape. A fourth profile is one entry here |
| `js/explain.js` | all the copy. A new step in the backend is one entry, nothing else |
| `js/harness.js` | the replay clock, the transport, the terminal renderer |
| `js/output.js` | chain, transactions, journal, checks, queue, evidence |
| `js/app.js` | state, routing, and the wiring between the two views |
| `assets/tokens.css` | every colour, size and radius, decided once |

Classic `<script src>` rather than modules, on purpose: `type="module"` is blocked on `file://`
too, and losing the drop-a-file path to save a line of boilerplate is a bad trade for a viewer whose
job is being easy to open.
