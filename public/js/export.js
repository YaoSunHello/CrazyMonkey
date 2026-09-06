/* Taking the result away.
   ---------------------------------------------------------------------------
   A run whose output cannot leave the page is a demo. The whole claim of this
   pipeline is that somebody gets numbers they can check — so they need the rows
   in a spreadsheet, the envelope for whatever consumes it, and a plain note
   saying what the run could not settle.

   Everything here is built from the normalised shape `adapters.js` produces, so
   a replayed run and one started from this page export identically, and nothing
   needs a server round-trip.  */

(function () {
  "use strict";

  const CSV_COLUMNS = [
    ["row_id", (r) => r.id],
    ["account", (r, account) => account.account],
    ["date", (r) => r.date],
    ["currency", (r) => r.currency],
    ["amount", (r) => (r.amount === null ? "" : r.amount)],
    ["narrative", (r) => r.narrative],
    ["counterparty_raw", (r) => r.cpRaw],
    ["counterparty_match", (r) => (r.cp && r.cp.name) || ""],
    ["counterparty_status", (r) => (r.cp && r.cp.status) || ""],
    ["counterparty_why", (r) => (r.cp && r.cp.why) || ""],
    ["project_code_raw", (r) => r.pcRaw],
    ["project_code_match", (r) => (r.pc && r.pc.name) || ""],
    ["project_code_status", (r) => (r.pc && r.pc.status) || ""],
    ["classification", (r) => r.classification],
    ["ready_for_export", (r) => (r.ready ? "yes" : "no")],
    ["review_reason", (r) => r.reason || ""],
    ["page", (r) => (r.page === null || r.page === undefined ? "" : r.page)],
  ];

  /* A narrative is full of commas and the odd quote, and a CSV that splits one
     across three cells is worse than no CSV — the reviewer stops trusting the
     file rather than the row. So quote everything and double the quotes. */
  function cell(value) {
    const text = value === null || value === undefined ? "" : String(value);
    return `"${text.replace(/"/g, '""')}"`;
  }

  function toCsv(data) {
    const lines = [CSV_COLUMNS.map(([name]) => cell(name)).join(",")];
    data.accounts.forEach((account) => {
      account.rows.forEach((row) => {
        lines.push(CSV_COLUMNS.map(([, read]) => cell(read(row, account))).join(","));
      });
    });
    // A leading BOM, so Excel opens a UTF-8 file as UTF-8 rather than mangling
    // every accented company name in it.
    return "﻿" + lines.join("\r\n") + "\r\n";
  }

  /* The one a person actually reads before deciding whether to trust the run.
     Not a dump of everything — the counts, then the things that did not hold,
     then every row that needs somebody, each with the reason already recorded
     against it. */
  function toNotes(data, summary) {
    const out = [];
    const say = (line = "") => out.push(line);
    const rule = (title) => { say(); say(title); say("-".repeat(title.length)); };

    say(`CrazyMonkey — run notes`);
    say(`generated ${new Date().toISOString().replace("T", " ").slice(0, 19)}`);
    say();
    if (summary) {
      say(`run        ${summary.run_id || ""}`);
      say(`profile    ${summary.profile || data.profile || ""}`);
      say(`model      ${summary.model || ""}`);
      say(`attempts   ${summary.attempts || ""}`);
      say(`accepted   ${summary.accepted ? "yes" : "no"}`);
    } else {
      say(`profile    ${data.profile || ""}`);
      say(`batch      ${data.batch || ""}`);
    }
    say(`documents  ${data.accounts.length}`);

    const rows = data.accounts.reduce((n, a) => n + a.rows.length, 0);
    const review = [];
    data.accounts.forEach((account) => {
      account.rows.forEach((row) => {
        if (!row.ready) review.push({ account: account.account, row });
      });
    });

    rule("Counts");
    say(`rows                 ${rows}`);
    say(`ready to export      ${rows - review.length}`);
    say(`need a person        ${review.length}`);

    const byStatus = {};
    data.accounts.forEach((a) => a.rows.forEach((r) => {
      const key = (r.cp && r.cp.status) || "MISSING";
      byStatus[key] = (byStatus[key] || 0) + 1;
    }));
    Object.keys(byStatus).sort().forEach((key) => say(`  counterparty ${key.padEnd(14)} ${byStatus[key]}`));

    /* The checks that did not pass. A green board says nothing; these are the
       only lines in the file that can tell somebody the run is not safe. */
    const unhappy = [];
    data.accounts.forEach((account) => {
      (account.checks || []).forEach((check) => {
        if (check.status && check.status !== "PASS") {
          unhappy.push({ account: account.account, check });
        }
      });
    });

    rule(`Checks that did not pass (${unhappy.length})`);
    if (!unhappy.length) say("none — every check the profile asked for held.");
    unhappy.forEach(({ account, check }) => {
      say(`[${check.status}] ${account} · ${check.name}`);
      if (check.detail) say(`    ${check.detail}`);
      String(check.evidence || "").split("\n").filter(Boolean).slice(0, 6)
        .forEach((line) => say(`      ${line}`));
    });

    rule(`Rows needing a person (${review.length})`);
    if (!review.length) say("none.");
    review.forEach(({ account, row }) => {
      say(`${row.id} · ${account} · ${row.currency} ${row.amount === null ? "" : row.amount}`);
      say(`    reason      ${row.reason || "(none recorded)"}`);
      const explanation = row.raw && row.raw.review_explanation;
      if (explanation) say(`    explanation ${explanation}`);
      if (row.narrative) say(`    narrative   ${row.narrative.slice(0, 160)}`);
      if (row.cp && row.cp.status === "PROBABLE" && row.cp.name) {
        say(`    proposed    ${row.cp.name}${row.cp.confidence ? ` (${row.cp.confidence})` : ""}`);
        if (row.cp.why) say(`    because     ${row.cp.why}`);
      }
      say();
    });

    rule("How to read this");
    say("A row marked ready has a counterparty found verbatim in a reference list,");
    say("or no counterparty to find. A row needing a person has something that was");
    say("read from the document and could not be settled against the reference");
    say("data — the explanation says what was read and why it did not resolve.");
    say();
    say("Nothing here was guessed: a match is a value that exists in the list it");
    say("names, and a proposal carries its reasoning and a confidence below one.");

    return out.join("\r\n") + "\r\n";
  }

  function download(filename, text, type) {
    const blob = new Blob([text], { type: `${type};charset=utf-8` });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    // Revoked on the next tick: Firefox cancels an in-flight download if the
    // object URL disappears while it is still being read.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  CM.exporter = {
    /* Named for the run, so files from two runs never collide in Downloads. */
    stem(data, summary) {
      const id = (summary && summary.run_id) || data.batch || "crazymonkey";
      return String(id).replace(/[^A-Za-z0-9_.-]/g, "-");
    },

    csv(data, summary) {
      download(`${this.stem(data, summary)}-rows.csv`, toCsv(data), "text/csv");
    },

    json(data, summary) {
      const payload = data.envelope || data.raw || data;
      download(
        `${this.stem(data, summary)}.json`,
        JSON.stringify(payload, null, 2),
        "application/json",
      );
    },

    notes(data, summary) {
      download(`${this.stem(data, summary)}-notes.txt`, toNotes(data, summary), "text/plain");
    },

    /* The button row. Rendered wherever there is data — a replayed run and a
       fresh one both reach this with the same shape. */
    bar() {
      return `<div class="exports">
        <span class="exports-label">export</span>
        <button class="btn quiet" data-export="csv">CSV</button>
        <button class="btn quiet" data-export="json">JSON</button>
        <button class="btn quiet" data-export="notes">Notes (txt)</button>
      </div>`;
    },

    wire(root, data, summary) {
      root.querySelectorAll("[data-export]").forEach((button) => {
        button.onclick = () => {
          try {
            CM.exporter[button.dataset.export](data, summary);
          } catch (err) {
            button.textContent = "failed";
            console.error(err);
          }
        };
      });
    },
  };
})();
