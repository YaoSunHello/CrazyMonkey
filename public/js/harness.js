/* The harness: a recorded run, played back.
   ---------------------------------------------------------------------------
   backend/app/trace.py records one event per discrete thing the agent does and
   writes them to trace.jsonl. This renders that stream the way the terminal
   renderer does — same timestamp column, same ● glyph, same ├ tree — because
   the claim being made is that this *is* the run, not a nicer retelling of it.

   Two things it does that the terminal cannot:

     - every line is clickable, and opens what that step means in English
     - the dead time is collapsed and labelled. Measured gaps in a real run are
       twenty events inside a tenth of a second and then a flat 97 seconds of
       the model writing code. Honoured literally, the screen freezes for three
       minutes of a four-minute demo. Scaled uniformly, the bursts become an
       unreadable smear. So gaps are capped and a marker says where the time
       went — which is both more honest and better television than deleting it.  */

(function () {
  "use strict";

  const { esc } = CM.util;

  const SPEEDS = [
    { label: "1×", value: 1 },
    { label: "4×", value: 4 },
    { label: "16×", value: 16 },
    { label: "all", value: Infinity },
  ];

  // Under three seconds is a pause you can watch; above it, collapse and say so.
  const GAP_MARK_AFTER = 3;
  const GAP_SCALE = 0.35;
  const GAP_CAP = 1200;

  // How many lines of the code's own output stay on screen while it is still
  // producing them. One real run printed 2,186 stdout events; rendered flat
  // they bury every step that matters under a debug dump.
  const OUT_TAIL = 8;

  const GLYPH = { running: "●", ok: "●", fail: "●", skip: "○" };
  const CHECK_MARK = { PASS: "✓", FAIL: "✗", UNRESOLVED: "!", CANNOT_VERIFY: "–" };

  const stamp = (seconds) => `${seconds.toFixed(1)}s`;

  /* --- one event, as a line of terminal ------------------------------------ */

  function codeBlock(event, index, expanded) {
    const lines = (event.body || "").split("\n");
    const limit = expanded ? lines.length : (event.meta && event.meta.preview_lines) || 14;
    const shown = lines.slice(0, limit).map((line, n) =>
      `<span class="ln">${n + 1}</span>${esc(line)}`
    ).join("\n");
    const rest = lines.length - limit;
    const more = rest > 0
      ? `\n<span class="more"><span class="ln"></span>` +
        `<u data-expand="${index}">… show ${rest} more line${rest === 1 ? "" : "s"}</u></span>`
      : (expanded && lines.length > 14
          ? `\n<span class="more"><span class="ln"></span><u data-expand="${index}">… collapse</u></span>`
          : "");
    return `<span class="codeblock">${shown}${more}</span>`;
  }

  function verdictBlock(event) {
    const checks = (event.meta && event.meta.checks) || [];
    const tally = { PASS: 0, FAIL: 0, UNRESOLVED: 0, CANNOT_VERIFY: 0 };
    const lines = checks.map((check) => {
      const status = check.status || "PASS";
      tally[status] = (tally[status] || 0) + 1;
      const evidence = (check.evidence || "").split("\n").filter(Boolean).slice(0, 3)
        .map((line) => `<span class="vevidence">${esc(line)}</span>`).join("");
      return `<span class="vline"><span class="v-${esc(status)}">${CHECK_MARK[status] || "?"}</span> ` +
             `<span class="vname">${esc(check.name)}</span>` +
             `<span class="vdetail">${esc(check.detail || "")}</span></span>${evidence}`;
    }).join("");

    let summary = `${tally.PASS} passed · ${tally.FAIL} failed · ${tally.UNRESOLVED} unresolved`;
    if (tally.CANNOT_VERIFY) summary += ` · ${tally.CANNOT_VERIFY} cannot verify`;
    const passed = event.status === "ok";
    return `<div class="verdictblock ${passed ? "passed" : "failed"}">${lines}` +
           `<span class="tally">⎿ ${esc(summary)}</span></div>`;
  }

  function eventHTML(event, index, elapsed, expanded) {
    const at = `<span class="at">${stamp(elapsed)}</span>`;
    const tree = `<span class="at"></span><span class="tree">├ </span>`;
    const body = esc(event.body || "");

    switch (event.kind) {
      case "state":
        return `<button class="ev k-state" data-i="${index}">${at}` +
               `<span class="glyph">▸ </span><span class="label">${esc(event.label)}</span>  ` +
               `<span class="detail">${esc(metaLine(event.meta))}</span></button>`;

      case "tool":
        return `<button class="ev k-tool ${esc(event.status)}" data-i="${index}">${at}` +
               `<span class="glyph">${GLYPH[event.status] || "●"}</span> ` +
               `<span class="label">${esc(event.label)}</span>  ` +
               `<span class="detail">${esc(event.detail || "")}</span></button>`;

      case "code":
        return `<button class="ev k-code" data-i="${index}">${tree}` +
               `<span class="path">${esc(event.label)}</span> ` +
               `<span class="detail">${esc(event.detail || "")}</span>\n` +
               codeBlock(event, index, expanded) + `</button>`;

      case "verdict":
        return `<button class="ev k-verdict" data-i="${index}">` + verdictBlock(event) + `</button>`;

      case "think":
        return `<button class="ev k-think" data-i="${index}">${tree}✻ ` +
               `${esc(event.detail || "")}${event.detail && body ? " — " : ""}${body}</button>`;

      default: // stdout, stderr, result
        return `<button class="ev k-${esc(event.kind)}" data-i="${index}">${tree}${body}</button>`;
    }
  }

  const metaLine = (meta) =>
    Object.entries(meta || {}).map(([key, value]) => `${key}=${value}`).join(" · ");

  /* --- the player ---------------------------------------------------------- */

  CM.harness = {
    events: [],
    meta: {},
    cursor: 0,          // how many events have been played
    speed: 4,
    playing: false,
    follow: true,
    selected: null,
    expanded: new Set(),
    timer: null,
    onSelect: null,

    mount(nodes) {
      this.nodes = nodes;

      nodes.play.addEventListener("click", () => (this.playing ? this.pause() : this.play()));
      nodes.scrub.addEventListener("input", () => {
        this.pause();
        this.seek(Number(nodes.scrub.value));
      });
      nodes.speeds.addEventListener("click", (e) => {
        const button = e.target.closest("button[data-speed]");
        if (!button) return;
        this.speed = Number(button.dataset.speed);
        this.paintTransport();
        if (this.playing) this.schedule();
      });
      nodes.follow.addEventListener("change", () => { this.follow = nodes.follow.checked; });

      // The terminal is one delegated listener rather than a listener per line:
      // a long run is two thousand events, and two thousand listeners is how a
      // replay starts dropping frames.
      nodes.term.addEventListener("click", (e) => {
        const expander = e.target.closest("[data-expand]");
        if (expander) {
          this.toggleCode(Number(expander.dataset.expand));
          e.stopPropagation();
          return;
        }
        const fold = e.target.closest("[data-gexpand]");
        if (fold) {
          const id = Number(fold.dataset.gexpand);
          if (this.expandedGroups.has(id)) this.expandedGroups.delete(id);
          else this.expandedGroups.add(id);
          this.settledGroups.delete(id);
          this.paintGroups();
          e.stopPropagation();
          return;
        }
        const jump = e.target.closest("[data-goto]");
        if (jump) {
          if (this.onGoto) this.onGoto(jump.dataset.goto);
          return;
        }
        const line = e.target.closest(".ev");
        if (line) this.select(Number(line.dataset.i));
      });
      // Scrolling up is how you say "stop dragging me to the bottom".
      nodes.term.addEventListener("scroll", () => {
        const atBottom =
          nodes.term.scrollHeight - nodes.term.scrollTop - nodes.term.clientHeight < 40;
        if (this.follow !== atBottom) {
          this.follow = atBottom;
          nodes.follow.checked = atBottom;
        }
      });

      nodes.speeds.innerHTML = SPEEDS.map((s) =>
        `<button data-speed="${s.value}" aria-pressed="false">${s.label}</button>`).join("");
    },

    /* Two passes over the stream before anything is drawn.

       Consecutive stdout/stderr events are grouped: while the code is still
       printing, the last few lines stay on screen the way a terminal shows
       them, and once it has finished they fold into one line you can open.
       Flat, one run of this pipeline is two thousand output lines and every
       step worth watching is lost inside them.

       The second pass records what the run was waiting on at each point, so a
       collapsed 97-second gap can say it was the model writing extract.py
       rather than just that time passed. */
    index() {
      const events = this.events;
      this.groups = new Map();
      this.groupOf = new Array(events.length).fill(-1);
      this.waiting = new Array(events.length).fill(null);

      let group = -1;
      let running = null;
      for (let i = 0; i < events.length; i += 1) {
        const event = events[i];
        this.waiting[i] = running;
        if (event.kind === "tool") running = event.status === "running" ? event : null;

        if (event.kind === "stdout" || event.kind === "stderr") {
          if (group === -1) {
            group = i;
            this.groups.set(group, { start: i, end: i });
          } else {
            this.groups.get(group).end = i;
          }
          this.groupOf[i] = group;
        } else {
          group = -1;
        }
      }
    },

    load(events, meta) {
      this.pause();
      this.events = events;
      this.meta = meta || {};
      this.cursor = 0;
      this.selected = null;
      this.expanded = new Set();
      this.expandedGroups = new Set();
      this.drawnGroups = new Set();
      this.settledGroups = new Set();
      this.index();
      this.follow = true;
      this.nodes.follow.checked = true;
      // A dropped envelope is a result without its log. Say that, rather than
      // showing an empty black rectangle and a transport that does nothing.
      this.nodes.term.innerHTML = events.length ? "" :
        `<div class="term-empty">No event stream for this one.<br><br>` +
        `A batch envelope is the <b>result</b> of a run — the log that produced it lives beside ` +
        `the run itself, in <b>outputs/runs/&lt;run id&gt;/trace.jsonl</b>. Pick a run on the left ` +
        `to watch one.</div>`;
      this.nodes.scrub.max = String(events.length);
      this.nodes.scrub.value = "0";
      this.paintExplain(null);
      this.paintTransport();
      this.paintStages();
    },

    elapsedAt(index) {
      if (!this.events.length) return 0;
      const first = this.events[0].at;
      return Math.max(0, (this.events[Math.min(index, this.events.length - 1)].at || first) - first);
    },

    /* --- playback ---------------------------------------------------------- */

    play() {
      if (!this.events.length) return;
      if (this.cursor >= this.events.length) this.seek(0);
      this.playing = true;
      this.paintTransport();
      this.schedule();
    },

    pause() {
      this.playing = false;
      clearTimeout(this.timer);
      this.timer = null;
      if (this.nodes) this.paintTransport();
    },

    schedule() {
      clearTimeout(this.timer);
      if (!this.playing) return;
      if (this.cursor >= this.events.length) { this.pause(); return; }

      if (this.speed === Infinity) {
        this.renderTo(this.events.length);
        this.pause();
        return;
      }

      const previous = this.cursor > 0 ? this.events[this.cursor - 1].at : this.events[0].at;
      const gap = Math.max(0, (this.events[this.cursor].at - previous) * 1000);
      const delay = Math.min(gap * GAP_SCALE, GAP_CAP) / this.speed;

      this.timer = setTimeout(() => {
        this.renderTo(this.cursor + 1);
        this.schedule();
      }, delay);
    },

    seek(index) {
      const target = Math.max(0, Math.min(index, this.events.length));
      if (target < this.cursor) {
        // Backwards means rebuilding. Cheaper than tracking node ownership per
        // event, and a seek is a deliberate act, not something in a hot loop.
        this.nodes.term.innerHTML = "";
        this.cursor = 0;
        this.drawnGroups = new Set();
        this.settledGroups = new Set();
      }
      this.renderTo(target);
    },

    renderTo(target) {
      const term = this.nodes.term;
      const pieces = [];
      for (let i = this.cursor; i < target; i += 1) {
        const event = this.events[i];
        const group = this.groupOf[i];

        // A gap inside a block of output is noise; a gap before it is the wait
        // that produced it. Only the second is worth a marker.
        if (i > 0 && (group === -1 || group === i)) {
          const gap = event.at - this.events[i - 1].at;
          if (gap >= GAP_MARK_AFTER) pieces.push(this.gapHTML(gap, i));
        }

        if (group >= 0) {
          if (!this.drawnGroups.has(group)) {
            pieces.push(`<div class="ev outgroup" data-g="${group}" data-i="${group}"></div>`);
            this.drawnGroups.add(group);
          }
          continue;
        }
        pieces.push(eventHTML(event, i, this.elapsedAt(i), this.expanded.has(i)));
      }
      if (pieces.length) term.insertAdjacentHTML("beforeend", pieces.join(""));
      this.cursor = target;
      this.paintGroups();

      if (this.cursor >= this.events.length && this.events.length) {
        if (!term.querySelector(".runcard")) {
          term.insertAdjacentHTML("beforeend", this.endHTML());
        }
      }
      if (this.follow) term.scrollTop = term.scrollHeight;
      this.paintTransport();
      this.paintStages();
    },

    /* Where the time went. The step still in flight says what we were waiting
       for — a `model · generating extract.py` line followed by a 107-second gap
       is the model writing 254 lines of code, and naming it is the point. */
    gapHTML(seconds, index) {
      const step = this.waiting[index];
      const what = step
        ? `${step.label}${step.detail ? " · " + step.detail : ""}`
        : "waiting";
      return `<div class="gapmark">⋯ ${esc(what)} — <b>${seconds.toFixed(0)}s</b> collapsed</div>`;
    },

    /* The code's own output. Streaming, it behaves like a terminal: the last
       few lines, replaced in place. Finished, it folds to one line — the log is
       kept in trace.jsonl either way, so nothing is lost by not showing it. */
    paintGroups() {
      this.drawnGroups.forEach((id) => {
        if (this.settledGroups.has(id)) return;
        const node = this.nodes.term.querySelector(`.outgroup[data-g="${id}"]`);
        if (!node) return;
        const span = this.groups.get(id);
        const finished = this.cursor > span.end;
        node.innerHTML = this.groupHTML(id);
        node.classList.toggle("folded", finished && !this.expandedGroups.has(id));
        if (finished && !this.expandedGroups.has(id)) this.settledGroups.add(id);
      });
    },

    groupHTML(id) {
      const span = this.groups.get(id);
      const upto = Math.min(this.cursor, span.end + 1);
      const lines = [];
      for (let i = span.start; i < upto; i += 1) {
        const event = this.events[i];
        (event.body || "").split("\n").forEach((line) => {
          // Blank lines are a third of some runs' output and they push the
          // lines that say something off a fixed-height tail.
          if (line.trim()) lines.push({ kind: event.kind, line });
        });
      }
      const errors = lines.filter((l) => l.kind === "stderr").length;
      const finished = this.cursor > span.end;
      const open = this.expandedGroups.has(id);

      if (finished && !open) {
        const last = lines.filter((l) => l.line.trim()).slice(-1)[0];
        return `<span class="at"></span><span class="tree">⎿ </span>` +
          `<u class="fold" data-gexpand="${id}">${lines.length} line${
            lines.length === 1 ? "" : "s"} of output</u>` +
          (errors ? `<span class="k-stderr"> · ${errors} on stderr</span>` : "") +
          (last ? `<span class="detail">   ${esc(last.line.slice(0, 90))}</span>` : "");
      }

      const shown = open ? lines : lines.slice(-OUT_TAIL);
      const hidden = lines.length - shown.length;
      const head = hidden > 0
        ? `<span class="at"></span><span class="tree">├ </span><span class="detail">… ${
            hidden} earlier line${hidden === 1 ? "" : "s"}</span>\n`
        : "";
      const foot = finished
        ? `\n<span class="at"></span><span class="tree">⎿ </span>` +
          `<u class="fold" data-gexpand="${id}">fold ${lines.length} lines away</u>`
        : "";
      return head + shown.map((entry) =>
        `<span class="oline k-${entry.kind}"><span class="at"></span>` +
        `<span class="tree">├ </span>${esc(entry.line)}</span>`).join("\n") + foot;
    },

    /* The payoff. A run that just spent four minutes writing and rewriting code
       against a verifier has earned a closing card, and the reader has earned
       one place to go next. */
    endHTML() {
      const total = this.elapsedAt(this.events.length - 1);
      const score = this.score(this.events.length);
      const meta = this.meta || {};
      const won = meta.finished ? meta.accepted : score.failed === 0;
      const verdict = !meta.finished && meta.run_id === undefined
        ? "recording ends"
        : won ? "accepted by the verifier" : "rejected — nothing emitted";

      return `<div class="runcard ${won ? "won" : "lost"}">
        <div class="rc-head">${won ? "✓" : "✗"} ${esc(verdict)}</div>
        <div class="rc-stats">
          <span><b>${score.rows || "—"}</b>rows</span>
          <span><b>${score.passed}</b>checks passed</span>
          <span class="${score.failed ? "bad" : ""}"><b>${score.failed}</b>failed</span>
          <span><b>${score.unresolved}</b>need a person</span>
          <span><b>${score.attempts}</b>attempts</span>
          <span><b>${CM.util.seconds(total)}</b>elapsed</span>
        </div>
        <div class="rc-foot">
          <button class="btn sm" data-goto="output">See the report →</button>
          <span>${this.events.length} events replayed from
            <b>${esc(meta.run_id || "trace.jsonl")}</b></span>
        </div>
      </div>`;
    },

    /* Everything the run has established so far, from the events played. It is
       recomputed rather than accumulated so that scrubbing backwards is honest:
       the counters show what was known at that point, not the final total. */
    score(upto) {
      const state = { rows: 0, passed: 0, failed: 0, unresolved: 0, attempts: 0, stage: "" };
      for (let i = 0; i < upto && i < this.events.length; i += 1) {
        const event = this.events[i];
        if (event.kind === "state") {
          if (event.label === "attempt") state.attempts += 1;
          if (event.meta && event.meta.rows) state.rows = event.meta.rows;
          if (event.meta && event.meta.stage) state.stage = event.meta.stage;
        } else if (event.kind === "verdict") {
          // Each pass re-reports its own checks, so the tally is taken from the
          // most recent verdict of each pass rather than summed across retries.
          const checks = (event.meta && event.meta.checks) || [];
          state.passed += checks.filter((c) => c.status === "PASS").length;
          state.failed += checks.filter((c) => c.status === "FAIL").length;
          state.unresolved += checks.filter((c) => c.status === "UNRESOLVED").length;
        }
      }
      return state;
    },

    toggleCode(index) {
      if (this.expanded.has(index)) this.expanded.delete(index);
      else this.expanded.add(index);
      const node = this.nodes.term.querySelector(`.ev[data-i="${index}"]`);
      if (!node) return;
      const wasSelected = node.getAttribute("aria-current") === "true";
      node.outerHTML = eventHTML(
        this.events[index], index, this.elapsedAt(index), this.expanded.has(index)
      );
      if (wasSelected) {
        const fresh = this.nodes.term.querySelector(`.ev[data-i="${index}"]`);
        if (fresh) fresh.setAttribute("aria-current", "true");
      }
    },

    select(index) {
      const previous = this.nodes.term.querySelector('.ev[aria-current="true"]');
      if (previous) previous.removeAttribute("aria-current");
      const node = this.nodes.term.querySelector(`.ev[data-i="${index}"]`);
      if (node) node.setAttribute("aria-current", "true");
      this.selected = index;
      this.paintExplain(this.events[index]);
      if (this.onSelect) this.onSelect(this.events[index], index);
    },

    /* --- painting ---------------------------------------------------------- */

    paintTransport() {
      const { play, scrub, readout, speeds } = this.nodes;
      play.textContent = this.playing ? "❚❚" : "▶";
      play.setAttribute("aria-label", this.playing ? "Pause" : "Play");
      scrub.value = String(this.cursor);
      readout.textContent =
        `${this.cursor} / ${this.events.length} events · ` +
        `${CM.util.seconds(this.elapsedAt(Math.max(0, this.cursor - 1)))} of ` +
        `${CM.util.seconds(this.elapsedAt(this.events.length - 1))}`;
      speeds.querySelectorAll("button").forEach((button) => {
        button.setAttribute("aria-pressed", String(Number(button.dataset.speed) === this.speed));
      });
    },

    /* The stage rail is derived from the state events played so far, so it can
       never claim a pass finished before the log says it did. */
    stages() {
      const order = [];
      const byId = {};
      const ensure = (id) => {
        if (!byId[id]) { byId[id] = { id, attempts: [], state: "seen" }; order.push(byId[id]); }
        return byId[id];
      };

      // The opening event names the passes, so a stage that has not started yet
      // is still on the rail — greyed, rather than appearing out of nowhere.
      const first = this.events[0];
      if (first && first.kind === "state" && first.meta && first.meta.passes) {
        String(first.meta.passes).split(",").map((s) => s.trim()).filter(Boolean).forEach(ensure);
      }

      for (let i = 0; i < this.cursor; i += 1) {
        const event = this.events[i];
        if (event.kind !== "state") continue;
        const meta = event.meta || {};
        const stage = meta.stage;
        if (!stage) continue;
        const entry = ensure(stage);
        if (event.label === "attempt") { entry.attempts.push("live"); entry.state = "current"; }
        else if (event.label === "accepted") {
          entry.attempts[entry.attempts.length - 1] = "ok";
          entry.state = "done";
        } else if (event.label === "rejected") {
          entry.attempts[entry.attempts.length - 1] = "bad";
          entry.state = "current";
        } else if (event.label === "exhausted") entry.state = "failed";
      }
      return order;
    },

    paintStages() {
      const stages = this.stages();
      const running = this.playing && this.cursor < this.events.length;
      const chips = stages.map((stage) => {
        const pips = stage.attempts.map((a) => `<i class="${a}"></i>`).join("");
        return `<span class="stage-chip ${stage.state}${
          stage.state === "current" && running ? " pulse" : ""}">${esc(stage.id)}` +
               `<span class="pips">${pips}</span></span>`;
      }).join('<span class="arrow">→</span>');

      // The counters tick up as the run establishes things. It is the only
      // motion on the page and it is all real: every number is read back out
      // of the events already played.
      const score = this.score(this.cursor);
      const counters = [
        ["rows", score.rows || "—"],
        ["passed", score.passed],
        ["failed", score.failed, score.failed ? "bad" : ""],
        ["attempts", score.attempts],
      ].map(([label, value, tone]) =>
        `<span class="count-cell ${tone || ""}"><b>${value}</b>${label}</span>`).join("");

      this.nodes.stagerail.innerHTML =
        (chips || '<span class="stage-chip">no passes recorded</span>') +
        `<span class="spacer"></span>` +
        `<span class="counters">${counters}</span>` +
        `<span class="replay-badge ${running ? "live" : ""}">` +
        `<span class="dot"></span>replay of a recorded run</span>`;
    },

    /* --- jumping in from the report ----------------------------------------- */

    /* The result and the log are the same run seen twice. Clicking a check in
       the report lands on the verdict that produced it, so "why does it say
       that" is one click rather than a search. */
    findCheck(name) {
      for (let i = this.events.length - 1; i >= 0; i -= 1) {
        const event = this.events[i];
        if (event.kind !== "verdict") continue;
        const checks = (event.meta && event.meta.checks) || [];
        if (checks.some((check) => check.name === name)) return i;
      }
      return -1;
    },

    findStage(stage) {
      return this.events.findIndex((event) =>
        event.kind === "state" && event.label === "attempt" &&
        event.meta && event.meta.stage === stage);
    },

    reveal(index) {
      if (index < 0) return false;
      this.pause();
      this.seek(Math.min(index + 1, this.events.length));
      this.select(index);
      const node = this.nodes.term.querySelector(`.ev[data-i="${index}"]`);
      if (node) {
        this.follow = false;
        this.nodes.follow.checked = false;
        node.scrollIntoView({ block: "center" });
      }
      return true;
    },

    paintExplain(event) {
      const panel = this.nodes.explain;
      if (!event) {
        panel.innerHTML =
          `<p class="hint">Every line in the log is clickable. Pick one and this panel says what ` +
          `that step was, why it matters, and shows the raw event exactly as it was recorded.</p>` +
          `<p class="hint">Nothing here is reconstructed — it is <code>trace.jsonl</code> from a ` +
          `real run against a real statement.</p>`;
        return;
      }

      const copy = CM.explain.forEvent(event);
      const fields = [];
      if (event.label) fields.push(["step", esc(event.label)]);
      if (event.detail) fields.push(["detail", esc(event.detail)]);
      if (event.status && event.kind !== "stdout") fields.push(["status", esc(event.status)]);
      Object.entries(event.meta || {}).forEach(([key, value]) => {
        if (key === "checks") return; // rendered below, not as a field
        fields.push([key, esc(typeof value === "object" ? JSON.stringify(value) : value)]);
      });

      const checks = (event.meta && event.meta.checks) || [];
      const checkList = checks.length
        ? `<dt>the checks that ran</dt><dd>${checks.map((check) => {
            const words = CM.explain.forCheck(check.name);
            return `<div style="margin:8px 0"><span class="chip ${
              check.status === "PASS" ? "match"
              : check.status === "FAIL" ? "bad"
              : check.status === "UNRESOLVED" ? "unresolved" : "cannot"
            }">${esc(check.status)}</span> <b>${esc(check.name)}</b><br>` +
            `<span style="color:var(--ink-soft)">${esc(check.detail || "")}</span>` +
            (words ? `<br><span style="color:var(--ink-faint)">${esc(words)}</span>` : "") +
            `</div>`;
          }).join("")}</dd>`
        : "";

      panel.innerHTML =
        `<div class="kicker">${esc(event.kind)}${event.label ? " · " + esc(event.label) : ""}</div>` +
        `<h3>${esc(copy.title)}</h3>` +
        `<p>${esc(copy.what)}</p>` +
        (copy.why ? `<p class="why">${esc(copy.why)}</p>` : "") +
        `<dl class="fields">${
          fields.map(([key, value]) => `<dt>${esc(key)}</dt><dd class="mono">${value}</dd>`).join("")
        }${checkList}</dl>` +
        `<details><summary>the event, as recorded</summary>` +
        `<pre>${esc(JSON.stringify(event, null, 2))}</pre></details>`;
      panel.scrollTop = 0;
    },
  };
})();
