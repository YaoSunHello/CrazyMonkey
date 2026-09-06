/* State, routing, and the wiring between the three views.
   ---------------------------------------------------------------------------
   Small on purpose. Everything interesting is in harness.js (the replay) and
   output.js (the deliverable); this file decides what is on screen and hands
   them their data.  */

(function () {
  "use strict";

  const { esc, seconds } = CM.util;
  const $ = (id) => document.getElementById(id);

  const STATE = {
    runs: [],
    latest: "",
    runId: null,
    summary: null,
    data: null,          // normalised, from adapters.js
    view: "replay",
    out: { account: 0, row: null },
    label: "",
    launch: null,
    launchSeen: 0,
    launchTimer: null,
  };

  /* --- the left rail: batches, then the documents inside them --------------- */

  function paintRail() {
    const rail = $("runlist");
    if (!CM.api.served) {
      rail.innerHTML = `<p class="empty" style="color:#93A984">This page was opened straight off
        the filesystem, so it cannot read <code>outputs/runs/</code> — a <code>file://</code> page
        may not fetch its own siblings. Drop an envelope from <code>examples/</code> below, or
        start the console with <code>python serve.py</code> to replay real runs.</p>`;
      return;
    }
    if (!STATE.runs.length) {
      rail.innerHTML = `<p class="empty" style="color:#93A984">No runs recorded yet.</p>`;
      return;
    }

    // Runs that were part of one `agent --all` share a timestamp, and that is
    // the unit people think in — "the batch where four were rejected".
    const batches = new Map();
    STATE.runs.forEach((run) => {
      if (!batches.has(run.batch)) batches.set(run.batch, []);
      batches.get(run.batch).push(run);
    });

    let index = 0;
    rail.innerHTML = [...batches.entries()].map(([batch, runs]) => {
      const accepted = runs.filter((r) => r.accepted).length;
      const rejected = runs.filter((r) => r.finished && !r.accepted).length;
      const open = index++ === 0 || runs.some((r) => r.run_id === STATE.runId);
      return `<details class="batch" ${open ? "open" : ""}>
        <summary>
          <span class="caret">▶</span>
          <span class="when">${esc(runs[0].when ? runs[0].when.slice(5, 16) : batch)}</span>
          <span class="tally"><b>${accepted}</b>${rejected ? ` · <i>${rejected}</i>` : ""}
            / ${runs.length}</span>
        </summary>
        ${runs.map((run) => `
          <button class="run" data-run="${esc(run.run_id)}"
                  aria-current="${run.run_id === STATE.runId}">
            <span class="pip ${run.finished ? (run.accepted ? "ok" : "bad") : ""}"></span>
            <span class="run-name">${esc(run.account)}</span>
            <span class="run-meta">${run.rows || 0}r · ${run.attempts || 0}t ·
              ${esc(seconds(run.seconds))}</span>
          </button>`).join("")}
      </details>`;
    }).join("");

    rail.querySelectorAll("[data-run]").forEach((button) => {
      button.onclick = () => openRun(button.dataset.run);
    });
  }

  /* --- top bar -------------------------------------------------------------- */

  function paintTop() {
    const summary = STATE.summary;
    const account = STATE.data && STATE.data.accounts[0];

    if (!STATE.data && !summary) {
      $("topline").innerHTML = `<div><h2>CrazyMonkey</h2>
        <div class="sub">Pick a run on the left, or drop a batch envelope.</div></div>`;
      $("tabs").innerHTML = "";
      return;
    }

    const title = summary
      ? `${esc(summary.account)} — ${esc(summary.source_file || "")}`
      : esc(STATE.label);
    const bits = summary
      ? [
          `<code>${esc(summary.run_id)}</code>`,
          summary.profile ? esc(summary.profile) : "",
          summary.model ? esc(summary.model) : "",
          summary.attempts ? `${summary.attempts} attempt${summary.attempts === 1 ? "" : "s"}` : "",
          summary.seconds ? esc(seconds(summary.seconds)) : "",
        ]
      : [
          STATE.data.profile ? `profile <b>${esc(STATE.data.profile)}</b>` : "",
          STATE.data.batch ? `batch <code>${esc(STATE.data.batch)}</code>` : "",
          `${STATE.data.accounts.length} statement${STATE.data.accounts.length === 1 ? "" : "s"}`,
        ];

    const pill = summary
      ? (!summary.finished
          ? `<span class="verdict-pill none">did not finish</span>`
          : summary.accepted
            ? `<span class="verdict-pill ok">accepted by the verifier</span>`
            : `<span class="verdict-pill bad">rejected — nothing emitted</span>`)
      : "";

    $("topline").innerHTML = `
      <div style="min-width:0">
        <h2>${title}</h2>
        <div class="sub">${bits.filter(Boolean).join(" · ")}</div>
        ${summary && summary.note
          ? `<div class="sub" style="margin-top:3px">${esc(summary.note)}</div>` : ""}
      </div>
      <span class="spacer"></span>
      ${STATE.data && CM.exporter ? CM.exporter.bar() : ""}
      ${pill}`;

    /* Downloads belong wherever a run is open, not behind a tab. Any recorded
       run that has rows can be taken away — that is the difference between a
       console you look at and a result you can act on. */
    if (STATE.data && CM.exporter) CM.exporter.wire($("topline"), STATE.data, STATE.summary);

    const rows = account ? account.rows.length : 0;
    const checks = account ? account.checks.length : 0;
    const files = (summary && summary.files ? summary.files : []).filter((n) => n.endsWith(".py"));
    const traceCount = STATE.trace ? STATE.trace.length : 0;

    $("tabs").innerHTML = [
      ["replay", "Replay", traceCount ? `${traceCount}` : ""],
      ["output", "Output", rows ? `${rows}` : ""],
      ["checks", "Checks", checks ? `${checks}` : ""],
      ["code", "Code", files.length ? `${files.length}` : ""],
      ["new", "New run", ""],
    ].map(([id, label, count]) =>
      `<button data-view="${id}" aria-selected="${STATE.view === id}">${label}${
        count ? `<span class="count">${count}</span>` : ""}</button>`).join("");

    $("tabs").querySelectorAll("[data-view]").forEach((button) => {
      button.onclick = () => show(button.dataset.view);
    });
  }

  /* --- views ---------------------------------------------------------------- */

  function show(view) {
    STATE.view = view;
    ["replay", "output", "checks", "code", "new"].forEach((id) => {
      $(`view-${id}`).hidden = id !== view;
    });
    // Only the harness owns its own scrolling; the rest is one long page.
    $("view-replay").classList.toggle("no-scroll", true);
    paintTop();

    if (view === "output") paintOutput();
    if (view === "checks") paintChecks();
    if (view === "code") paintCode();
    if (view === "new") paintLauncher();
  }

  function paintOutput() {
    const target = $("view-output");
    if (!STATE.data) {
      target.innerHTML = `<div class="pad"><div class="notice warn">This run has no rows on disk.
        A run that never satisfied the verifier emits nothing — which is the intended behaviour,
        not a missing file. The <b>Replay</b> tab shows what happened.</div></div>`;
      return;
    }
    CM.output.hasTrace = !!(STATE.trace && STATE.trace.length);
    STATE.out.rejected = !!(STATE.summary && STATE.summary.finished && !STATE.summary.accepted);
    STATE.out.stage = failedStage();
    STATE.out.summary = STATE.summary;
    CM.output.render(target, STATE.data, STATE.out);
  }

  /* Which pass ran out of attempts, from the log rather than from the summary
     string — the summary is prose and the events are the record. */
  function failedStage() {
    const last = (STATE.trace || []).filter((event) =>
      event.kind === "state" && event.label === "exhausted").pop();
    return last && last.meta ? last.meta.stage || "" : "";
  }

  /* Checks get their own tab as well as a panel, because on a rejected run it
     is the first thing anybody opens. */
  function paintChecks() {
    const target = $("view-checks");
    if (!STATE.data) {
      target.innerHTML = `<div class="pad"><p class="empty">No checks on disk for this run.</p></div>`;
      return;
    }
    const account = STATE.data.accounts[Math.min(STATE.out.account, STATE.data.accounts.length - 1)];
    const rows = account.checks.map((check) => `
      <section class="panel">
        <header>
          <h3 class="st-${esc(check.status)}" style="text-transform:none;letter-spacing:0;
              font-family:var(--mono);font-size:12px">${esc(check.name)}</h3>
          <span class="spacer"></span>
          <span class="chip ${
            check.status === "PASS" ? "match"
            : check.status === "FAIL" ? "bad"
            : check.status === "UNRESOLVED" ? "unresolved" : "cannot"
          }">${esc(check.status)}</span>
        </header>
        <div class="body">
          <p style="margin:0 0 8px"><b>${esc(check.detail || "")}</b></p>
          ${CM.explain.forCheck(check.name)
            ? `<p style="margin:0 0 8px;color:var(--ink-soft)">${esc(CM.explain.forCheck(check.name))}</p>`
            : ""}
          ${check.evidence ? `<div class="quote">${esc(check.evidence)}</div>` : ""}
          <p style="margin:10px 0 0;color:var(--ink-faint);font-size:var(--t-sm)">
            ${esc(CM.explain.forStatus(check.status))}</p>
        </div>
      </section>`).join("");

    target.innerHTML = `<div class="pad">
      <div class="notice plain">Three outcomes, not two. <b>PASS</b> holds. <b>FAIL</b> blocks the
        output and the pass is retried. <b>UNRESOLVED</b> means the parse was fine but a value has
        no match in the reference data, and a person decides it — 52 of the 100 rows in this
        dataset genuinely have no counterparty, which is the difficulty of the exercise rather
        than a defect. <b>CANNOT_VERIFY</b> means the document named nothing to check.</div>
      ${rows}</div>`;
  }

  async function paintCode() {
    const target = $("view-code");
    const files = ((STATE.summary && STATE.summary.files) || []).filter((n) => n.endsWith(".py"));
    if (!files.length) {
      target.innerHTML = `<div class="pad"><p class="empty">No attempt sources on disk for this
        run.</p></div>`;
      return;
    }
    target.innerHTML = `<div class="pad"><p class="empty">Loading ${files.length} files…</p></div>`;
    const sources = await Promise.all(files.map((name) =>
      CM.api.file(STATE.runId, name).catch((error) => `# could not read: ${error.message}`)));

    target.innerHTML = `<div class="pad">
      <div class="notice plain">Every attempt's source is kept beside the run. When a run fails the
        first useful thing is the code that failed, so it is a file rather than a field inside a
        log line.</div>
      ${files.map((name, i) => `
        <section class="panel">
          <header><h3 style="font-family:var(--mono);text-transform:none;letter-spacing:0">
            ${esc(name)}</h3><span class="spacer"></span>
            <span class="note">${sources[i].split("\n").length} lines</span></header>
          <div class="body tight"><pre style="margin:0;padding:14px 16px;overflow:auto;
            font-family:var(--mono);font-size:11.5px;line-height:1.6;max-height:460px">${
            esc(sources[i])}</pre></div>
        </section>`).join("")}</div>`;
  }

  /* --- starting a new run ---------------------------------------------------- */

  async function paintLauncher() {
    const target = $("view-new");
    if (!CM.api.served) {
      target.innerHTML = `<div class="pad"><div class="notice warn">Starting a run needs the
        console to be served. Run <code>python backend/test-simple-frontend/serve.py</code> and
        open the URL it prints.</div></div>`;
      return;
    }

    const [health, statements, profiles] = await Promise.all([
      CM.api.health().catch(() => ({})),
      CM.api.statements().catch(() => []),
      CM.api.profiles().catch(() => []),
    ]);

    if (!health.new_runs_allowed) {
      target.innerHTML = `<div class="pad"><div class="notice warn">This console was started with
        <code>--no-new-runs</code>, so it will refuse to start one. Restart
        <code>serve.py</code> without that flag to enable it.</div></div>`;
      return;
    }

    target.innerHTML = `<div class="pad" style="max-width:760px">
      <div class="notice plain">A run takes roughly seven minutes, spends model calls, and creates
        a disposable sandbox per document. Nothing is started until the command below is confirmed.</div>
      <section class="panel">
        <header><h3>Start a run</h3></header>
        <div class="body">
          <div class="launcher">
            <div class="field"><label for="folder">choose a folder of statements</label>
              <input type="file" id="folder" webkitdirectory directory multiple>
              <span class="note" id="foldernote">every PDF inside is uploaded and processed</span></div>
            <div class="field"><label for="pdf">or add one file</label>
              <input type="file" id="pdf" accept="application/pdf,.pdf" multiple>
              <span class="note" id="pdfnote"></span></div>
            <div class="field"><label for="acct">statement</label>
              <select id="acct"><option value="__all__">— all ${statements.length} statements, one batch —</option>${statements.map((s) =>
                `<option value="${esc(s.account)}">${esc(s.account)} — ${esc(s.filename)}</option>`
              ).join("")}</select></div>
            <div class="field"><label for="prof">profile</label>
              <select id="prof">${profiles.map((p) =>
                `<option value="${esc(p.id)}">${esc(p.id)} — ${esc(p.label)}</option>`
              ).join("")}</select></div>
            <div id="cmdbox"></div>
            <div class="confirm-row">
              <button class="btn" id="review">Review the command</button>
              <span class="note" style="color:var(--ink-faint);font-size:var(--t-sm)">
                two steps on purpose</span>
            </div>
          </div>
        </div>
      </section>
      <section class="panel" id="launchlog" hidden>
        <header><h3>live output</h3><span class="spacer"></span>
          <span class="note" id="launchmeta"></span></header>
        <div class="body tight"><pre id="launchlines" style="margin:0;padding:14px 16px;
          max-height:420px;overflow:auto;background:var(--forest-deep);color:var(--term-ink);
          font-family:var(--mono);font-size:11.5px;line-height:1.6"></pre></div>
      </section>`;

    /* Take a folder, keep the PDFs, ignore the rest. A real folder has a
       .DS_Store and a spreadsheet in it, and refusing the whole thing over
       those would be the console being pedantic about somebody else's disk. */
    async function absorb(files, note) {
      const pdfs = [...files].filter((f) => /\.pdf$/i.test(f.name));
      const skipped = files.length - pdfs.length;
      if (!pdfs.length) {
        note.textContent = `no PDFs there${skipped ? ` (${skipped} other file${skipped === 1 ? "" : "s"})` : ""}`;
        return;
      }

      let added = 0;
      const failed = [];
      for (const file of pdfs) {
        note.textContent = `uploading ${added + 1} of ${pdfs.length} — ${file.name}`;
        try {
          await CM.api.upload(file);
          added += 1;
        } catch (err) {
          failed.push(`${file.name}: ${err.message || err}`);
        }
      }

      await paintLauncher();
      const after = $(note.id);
      if (!after) return;
      after.textContent = [
        `${added} statement${added === 1 ? "" : "s"} ready`,
        skipped ? `${skipped} non-PDF ignored` : "",
        failed.length ? `${failed.length} failed` : "",
      ].filter(Boolean).join(" · ");
      if (failed.length) after.title = failed.join(" | ");
    }

    const folder = $("folder");
    if (folder) folder.onchange = () => {
      if (folder.files && folder.files.length) absorb(folder.files, $("foldernote"));
    };

    const picker = $("pdf");
    if (picker) picker.onchange = () => {
      if (picker.files && picker.files.length) absorb(picker.files, $("pdfnote"));
    };

    $("review").onclick = () => {
      const account = $("acct").value;
      const profile = $("prof").value;
      /* Show the command that will actually run. One statement takes minutes;
         the whole batch takes closer to half an hour, and saying so before the
         confirm is the difference between a decision and a surprise. */
      const every = account === "__all__";
      const target = every
        ? `<span class="flag">--all</span> <span class="flag">--parallel</span> 4`
        : `<span class="flag">--account</span> ${esc(account)}`;
      $("cmdbox").innerHTML = `<div class="cmd">cd backend &amp;&amp; python -m app.cli agent ` +
        `${target} <span class="flag">--profile</span> ${esc(profile)}</div>` +
        `<div class="note" style="margin-top:6px">${every
          ? "Every statement, four at a time — roughly half an hour, and a sandbox per document."
          : "One statement — a few minutes."}</div>`;
      $("review").outerHTML = `<button class="btn danger" id="confirm">Confirm and start</button>
        <button class="btn quiet" id="cancel">Cancel</button>`;
      $("cancel").onclick = () => paintLauncher();
      $("confirm").onclick = () => startRun(account, profile);
    };
  }

  async function startRun(account, profile) {
    $("confirm").disabled = true;
    $("confirm").textContent = "Starting…";
    try {
      STATE.launch = await CM.api.launch(account, profile);
      STATE.launchSeen = 0;
      $("launchlog").hidden = false;
      pollLaunch();
    } catch (error) {
      $("cmdbox").innerHTML += `<div class="notice bad" style="margin-top:10px">Could not start:
        ${esc(error.message)}</div>`;
      $("confirm").disabled = false;
      $("confirm").textContent = "Confirm and start";
    }
  }

  /* The agent writes trace.jsonl in one go when it finishes, so there is no
     structured stream to tail while it works — what there is, is the terminal
     renderer on stderr. Show that, and the moment the run directory lands,
     offer the real replay. */
  async function pollLaunch() {
    clearTimeout(STATE.launchTimer);
    if (!STATE.launch) return;
    let state;
    try {
      state = await CM.api.launchState(STATE.launch.id, STATE.launchSeen);
    } catch (error) {
      $("launchmeta").textContent = `lost contact: ${error.message}`;
      return;
    }
    STATE.launchSeen = state.total_lines;

    const pre = $("launchlines");
    if (pre && state.lines.length) {
      pre.textContent += state.lines.join("\n") + "\n";
      pre.scrollTop = pre.scrollHeight;
    }
    $("launchmeta").textContent =
      `${state.running ? "running" : `finished (exit ${state.returncode})`} · ` +
      `${seconds(state.seconds)}${state.run_id ? ` · ${state.run_id}` : ""}`;

    if (state.running) {
      STATE.launchTimer = setTimeout(pollLaunch, 1500);
      return;
    }
    await refreshRuns();
    if (state.run_id) {
      $("launchmeta").innerHTML +=
        ` · <a href="#" id="openfresh">replay it</a>`;
      $("openfresh").onclick = (e) => { e.preventDefault(); openRun(state.run_id); };
    }
  }

  /* --- loading -------------------------------------------------------------- */

  async function refreshRuns() {
    if (!CM.api.served) return;
    const payload = await CM.api.runs().catch(() => ({ runs: [], latest: "" }));
    STATE.runs = payload.runs || [];
    STATE.latest = payload.latest || "";
    paintRail();
  }

  async function openRun(runId) {
    STATE.runId = runId;
    STATE.out = { account: 0, row: null };
    STATE.data = null;
    STATE.trace = [];

    const summary = STATE.runs.find((r) => r.run_id === runId) || { run_id: runId };
    STATE.summary = summary;
    STATE.label = runId;
    paintRail();
    paintTop();

    const [traceText, rows] = await Promise.all([
      summary.has_trace ? CM.api.trace(runId).catch(() => "") : Promise.resolve(""),
      loadRows(runId, summary),
    ]);

    STATE.trace = traceText
      .split("\n")
      .filter(Boolean)
      .map((line) => { try { return JSON.parse(line); } catch (_) { return null; } })
      .filter(Boolean);

    if (rows) STATE.data = CM.adapters.fromRun(rows, summary);

    CM.harness.load(STATE.trace, summary);
    show("replay");
    if (STATE.trace.length) CM.harness.play();
  }

  /* A run that was rejected on the resolve pass still has its extract output on
     disk. Falling back through the stages means a failed run is still readable
     rather than an empty screen. */
  async function loadRows(runId, summary) {
    const files = summary.files || [];
    const order = [
      ["", "rows.json"],
      ["resolve", "rows-resolve.json"],
      ["extract", "rows-extract.json"],
    ].filter(([, name]) => !files.length || files.includes(name));

    for (const [stage] of order) {
      try {
        return await CM.api.rows(runId, stage);
      } catch (_) { /* try the next stage */ }
    }
    return null;
  }

  function loadFile(text, label) {
    let payload;
    try {
      payload = JSON.parse(text);
    } catch (error) {
      $("view-output").innerHTML =
        `<div class="pad"><div class="notice bad">Could not read ${esc(label)}: ${
          esc(error.message)}</div></div>`;
      show("output");
      return;
    }

    STATE.summary = null;
    STATE.runId = null;
    STATE.trace = [];
    STATE.out = { account: 0, row: null };
    STATE.label = label;
    STATE.data = payload.accounts
      ? CM.adapters.fromBatch(payload, label)
      : CM.adapters.fromRun(payload, null);
    CM.harness.load([], {});
    show("output");
    paintRail();
  }

  /* --- boot ------------------------------------------------------------------ */

  function wireDropZone() {
    const zone = $("drop");
    const read = (file) => {
      const reader = new FileReader();
      reader.onload = () => loadFile(reader.result, file.name);
      reader.readAsText(file);
    };
    $("file").onchange = (e) => e.target.files[0] && read(e.target.files[0]);
    ["dragenter", "dragover"].forEach((kind) =>
      zone.addEventListener(kind, (e) => { e.preventDefault(); zone.classList.add("over"); }));
    ["dragleave", "drop"].forEach((kind) =>
      zone.addEventListener(kind, () => zone.classList.remove("over")));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      if (e.dataTransfer.files[0]) read(e.dataTransfer.files[0]);
    });
    document.addEventListener("dragover", (e) => e.preventDefault());
    document.addEventListener("drop", (e) => e.preventDefault());
  }

  async function boot() {
    CM.harness.mount({
      term: $("term"),
      explain: $("explain"),
      stagerail: $("stagerail"),
      play: $("play"),
      scrub: $("scrub"),
      readout: $("readout"),
      speeds: $("speeds"),
      follow: $("follow"),
    });

    // The two views are one run seen twice, so each can send you to the other.
    CM.harness.onGoto = (view) => show(view);
    CM.output.onTrace = (wanted) => {
      const index = wanted.check
        ? CM.harness.findCheck(wanted.check)
        : CM.harness.findStage(wanted.stage);
      if (index < 0) return;
      show("replay");
      CM.harness.reveal(index);
    };

    wireDropZone();
    $("newrun").onclick = () => show("new");
    $("refresh").onclick = () => refreshRuns();
    show("replay");

    if (!CM.api.served) {
      paintRail();
      paintTop();
      return;
    }

    await refreshRuns();

    const wanted = new URLSearchParams(location.search);
    const src = wanted.get("src");
    if (src) {
      fetch(src).then((r) => r.text()).then((t) => loadFile(t, src)).catch(() => {});
      return;
    }

    const asked = wanted.get("run");
    const pick = STATE.runs.find((r) => r.run_id === asked)
      || STATE.runs.find((r) => r.run_id === STATE.latest && r.has_trace)
      || STATE.runs.find((r) => r.has_trace);
    if (pick) openRun(pick.run_id);
    else paintTop();
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
