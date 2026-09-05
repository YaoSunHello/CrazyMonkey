# Wiring the backend to a UI

A guide, not an implementation. The backend already emits everything a UI needs; this describes
the contract and how to render it well. No framework is assumed.

Every JSON example below is copied from a real recorded run
(`outputs/runs/20260905-154740-GBP_3252/`), not invented.

---

## 1. The event contract

`backend/app/trace.py` emits one `Event` per discrete thing the agent does. Every event is a flat
object with the same seven fields, so a client can switch on `kind` and ignore the rest:

| field | type | notes |
|---|---|---|
| `kind` | `think \| tool \| code \| stdout \| stderr \| verdict \| state \| result` | the only field you must switch on |
| `label` | string | tool name, file path, or phase. Often empty |
| `detail` | string | short human-readable line. Often empty |
| `status` | `running \| ok \| fail \| skip` | meaningful on `tool` and `verdict`; `ok` elsewhere |
| `body` | string | code source, a log line, or a chunk of reasoning |
| `meta` | object | kind-specific payload |
| `at` | float | unix seconds — see §3, the pacing is not uniform |

### `state` — run phase changed

```json
{"kind": "state", "label": "starting", "status": "ok", "body": "", "meta":
 {"statement": "20260331_NI_V_SCSP_CALDER_GBP_3252.pdf", "model": "gemini-3.8-flash",
  "max_attempts": 4, "run": "20260905-154740-GBP_3252"}, "at": 1788619660.0}
```

Labels: `starting`, `attempt`, `accepted`, `rejected`, `exhausted`. Drive a status strip from
these; `attempt` carries `{n, of}`.

### `tool` — the agent did something

```json
{"kind": "tool", "label": "sandbox", "detail": "creating · python:3.11-bookworm",
 "status": "running", "meta": {}, "at": 1788619661.4}
```

A row in an activity rail. `status: "running"` then a second event with the same `label` and
`ok`/`fail`. Labels seen in practice: `sandbox`, `model`, `run_python`, `run_checks`, `output`.

### `code` — the model wrote a file

```json
{"kind": "code", "label": "/work/parse.py", "detail": "160 lines",
 "body": "import re\nimport kit\n\n\ndef parse():\n    num_pages = kit.page_count()…",
 "meta": {"preview_lines": 14}, "at": 1788619754.3}
```

`body` is the complete source. Syntax-highlight it, collapsed to `meta.preview_lines` by default.

### `stdout` / `stderr` — output from the agent's code

```json
{"kind": "stdout", "body": "Traceback (most recent call last):…", "at": 1788619755.8}
```

Ephemeral. Show them streaming past and discard them; they are already in `trace.jsonl` if anyone
needs them again.

### `verdict` — the verifier ran

```json
{"kind": "verdict", "status": "ok", "meta": {"passed": true, "checks": [
  {"name": "balance_chain", "scope": "GBP_3252", "status": "PASS",
   "detail": "15/15 links hold", "evidence": ""}]}, "at": 1788619857.9}
```

**The main panel.** Each check has `status` of `PASS`, `FAIL` or `UNRESOLVED` — see §5.

### `think` — the model's reasoning

Two shapes. Deltas as it streams, then one summary:

```json
{"kind": "think", "body": "…the header row gives column positions, so…",
 "meta": {"delta": true}, "at": 1788619700.1}

{"kind": "think", "detail": "2,100 characters of reasoning",
 "body": "…the last 1200 characters…", "meta": {"chars": 2100}, "at": 1788619740.6}
```

See §4. **May be absent entirely** — the run above contains no `think` events at all, because the
model was configured with no reasoning channel.

---

## 2. Getting the events out

`Trace.subscribe(callback)` is the relay hook. **The callback must not block** — it runs inline
while the agent is working, and blocking it stalls the run.

```python
# backend/app/main.py — sketch, not shipped
import asyncio
from fastapi.responses import StreamingResponse

@app.get("/api/runs/{run_id}/events")
async def events(run_id: str):
    queue: asyncio.Queue = asyncio.Queue()
    trace.subscribe(queue.put_nowait)          # append only, returns immediately

    async def pump():
        while True:
            event = await queue.get()
            yield f"data: {event.to_json()}\n\n"

    return StreamingResponse(pump(), media_type="text/event-stream")
```

```js
const source = new EventSource(`/api/runs/${runId}/events`);
source.onmessage = (m) => render(JSON.parse(m.data));
```

That is the whole integration. The agent knows nothing about HTTP.

---

## 3. Live versus replay

Runs are recorded to disk, one directory each:

```
outputs/
  latest                          the newest run id
  runs/20260905-154740-GBP_3252/
    trace.jsonl                   the event stream — the same objects as §1
    rows.json                     the structured output + the checks that judged it
    attempt-1.py                  the code the model wrote
    attempt-2.py                  …and its next try, after the verifier rejected the first
    summary.json                  account, model, attempts, accepted, rows, seconds
```

A run id is `<timestamp>-<account>`. Documents run together as a batch **share the timestamp**, so
`20260905-154520-*` is one batch and groups on that prefix.

```python
@app.get("/api/runs")                          # from app.runs.list_runs()
@app.get("/api/runs/{run_id}/events")          # live queue, or trace.jsonl line by line
@app.get("/api/runs/{run_id}/rows")            # the structured output
@app.get("/api/runs/{run_id}/attempts/{n}")    # the code the model wrote
```

### The client cannot tell the difference, and should not try

Both sources produce **identical event objects on the same channel**. Serve `trace.jsonl` line by
line and every renderer works unchanged. There is no replay mode to write.

### But you must not replay at wall-clock speed

Measured inter-event gaps from the run above, in seconds:

```
0.0 ×20    0.1 ×2    0.3 ×2    0.9    1.1 ×3    1.2    1.4    1.7    2.7    2.8    86.2    97.0
```

Almost everything is instantaneous; two gaps are ~90 seconds of the model generating. Honouring
those literally means the screen freezes for three minutes across a four-minute demo.

**Collapse the gaps rather than scaling them uniformly:**

```js
const gap = Math.min(original * 0.35, 1200);   // ms
```

Bursts stay legible, long pauses cap out, and a four-minute run plays in about ninety seconds with
nothing skipped. Where you collapse a long gap, **say so** — a `⋯ thinking 97s` marker is both
more honest and more impressive than silently deleting the time.

`app/cli.py::command_replay` already implements this; `--speed` scales it further.

### Honesty

Replay a *genuine* recorded run, never a hand-written fixture, and label it as a replay on screen.
Everything in `runs/` is a real run against real statements, so there is no reason to fake one.

---

## 4. Parsing the reasoning stream

Reasoning arrives as `think` events with `meta.delta === true`, roughly every 250 characters.
Concatenating every delta's `body` reproduces the reasoning exactly. A final `think` event with no
`delta` flag carries `meta.chars` (the total) and the last ~1,200 characters in `body`.

```js
let reasoning = "";

function onThink(event) {
  if (event.meta?.delta) {
    reasoning += event.body;
    showRollingWindow(reasoning);      // last few lines only — see below
  } else {
    hideRollingWindow();               // done; event.meta.chars is the total
    recordSummary(event.meta.chars);
  }
}
```

**Four things that will bite you:**

- **It may never arrive.** A model configured without a reasoning channel emits no `think` events
  at all. Do not render a "thinking…" placeholder that never resolves.
- **It can be enormous.** One measured run produced **120,000 characters of reasoning and no
  answer**. Never accumulate it into the DOM — keep a rolling window of the last few lines, as the
  terminal renderer does, and let the summary event report the total.
- **Reasoning is not the answer.** `think` bodies are the model's private working. The code it
  actually produces arrives separately, as a `code` event. Do not concatenate the two.
- **Provider naming differs.** vLLM streams reasoning on `delta.reasoning`; LiteLLM maps it to
  `reasoning_content`. `app/llm.py` reads both, so by the time it reaches you as a `think` event
  the difference is gone — but it explains why a client talking to the model directly might see
  nothing.

Deltas are recorded via `Trace.record()` rather than `emit()`, so the terminal can paint its own
in-place window while the recording still gets the stream. That is why a replay streams the
reasoning instead of dumping one block.

---

## 5. Rendering the chain — the part that matters

The product's claim is that the numbers foot. The UI has to **show** that, not assert it.

One row per transaction, in statement order, with the arithmetic visible:

```
                                    balance      − amount     = expected      next row
  0  31 Mar  TT ABC414K0BGIBU     103,014.97       −5.21      103,020.18    103,020.18   ✓
  1  31 Mar  TT ABC414K0BGIBU     103,020.18  −15,701,940.20  15,804,960.38 15,804,960.38 ✓
```

- The identity is `balance − amount == next row's balance`. Show all four columns. A reader who
  can see the subtraction does not have to trust you.
- On failure colour **that one link** red, not the whole table. A broken chain is a broken link.
- The `evidence` string on a failing check carries the delta and a citation:
  `p1 @ (35,348)-(725,355)` — page, then the bounding box on that page. Parse it, deep-link into
  the PDF and highlight the row. This is the highest-value single component you can build for this
  audience, and the customer's own process document asks for it by name.
- Show the closing balance and each `Balance brought forward` marker as anchors in the same
  column, so the chain visibly starts and ends somewhere real.

### Three statuses, three treatments

Do not collapse these into pass/fail. The distinction is the product's honesty.

| status | colour | wording | placement |
|---|---|---|---|
| `PASS` | green | silent — a tick | inline |
| `FAIL` | red | "does not foot — off by £100.00" | blocks output; top of the panel |
| `UNRESOLVED` | amber | "no match in the reference data" | a **review queue**, not an error list |

`UNRESOLVED` means the row parsed correctly but a value has no match. 52 of the 100 rows in the
supplied dataset genuinely have no counterparty match — that is the difficulty of the exercise,
not a defect. Present those as work to do with candidates ranked, never as something broken.

---

## 6. Batches

`agent --all` runs every statement with five Daytona sandboxes at a time. Each document has its
own sandbox and its own trace, so a batch is **N independent event streams**, not one interleaved
feed. Give each document its own row or panel and subscribe per run — merging them into a single
stream destroys the thing worth watching, which is that they progress and fail independently.

A real batch of seven finished 3 accepted, 4 rejected. The UI should make that legible at a
glance, because four rejections caught by the verifier is the product working, not the product
failing.

---

## 7. Design constraints

The rubric scores UI at 25%, with "no AI slop" and "a non-technical fund manager is the user".
The specific traps:

- **No indigo→purple gradient.** It is the loudest generated-UI tell there is.
- **Not Inter.** Choose a typeface deliberately.
- **`font-variant-numeric: tabular-nums` is mandatory.** This entire UI is a column of numbers,
  and digits that do not align read as amateur instantly to someone who works in Excel all day.
- **Dense, not airy.** 32–36px rows, ~25 rows visible without scrolling. Generous whitespace reads
  as a toy here, not as clean.
- **Master–detail, not a card grid.** Accounts on the left, the chain on the right.
- **Almost no motion.** 120ms colour and opacity only. No hover lift, no staggered fade-in.
- Left nav lists **accounts and documents**, not features.
