/* The output, as it is meant to be handed over.
   ---------------------------------------------------------------------------
   Not a dump of the JSON. The product's claim is that the numbers foot, and a
   claim is worth nothing asserted — so the arithmetic is shown: balance, minus
   the amount, equals the next row's balance, four columns, no abbreviation. A
   reader who can see the subtraction does not have to trust anybody.

   The three check statuses stay three. A boolean would have to either block
   output that is legitimately complete, or launder a missing match into a
   confident answer, and 52 of the 100 rows in this dataset genuinely have no
   counterparty. UNRESOLVED is work to do, and it goes in a queue rather than
   an error list.  */

(function () {
  "use strict";

  const { esc, money, plain, words, number } = CM.util;
  const MARK = { PASS: "✓", FAIL: "✗", UNRESOLVED: "!", CANNOT_VERIFY: "–" };

  /* A match that cannot name the list it came from renders as an error, not as
     clean — but only where the envelope carried that detail at all. The flat
     profile projects a bare status string, and accusing it of losing something
     it never had would be the viewer lying about the backend. */
  function chip(resolution) {
    if (!resolution.status) return '<span class="chip bad">no status</span>';
    if (resolution.status === "MATCH") {
      if (resolution.detailed && !resolution.table && !resolution.name) {
        return '<span class="chip bad">match, unsourced</span>';
      }
      const label = resolution.name || "matched";
      return `<span class="chip match" title="${esc(resolution.table || "")}">${esc(label)}</span>`;
    }
    if (resolution.status === "UNRESOLVED") return '<span class="chip unresolved">unresolved</span>';
    if (resolution.status === "CANNOT_VERIFY") return '<span class="chip cannot">none named</span>';
    return `<span class="chip bad">${esc(resolution.status)}</span>`;
  }

  function tallyChecks(checks) {
    const tally = { PASS: 0, FAIL: 0, UNRESOLVED: 0, CANNOT_VERIFY: 0 };
    checks.forEach((check) => {
      tally[check.status] = (tally[check.status] || 0) + 1;
    });
    return tally;
  }

  /* --- the chain ----------------------------------------------------------- */

  function chainPanel(account) {
    if (!account.hasChain) {
      return panel("the chain", "", `<p class="empty">This envelope projects the amounts but not ` +
        `the running balance, so the subtraction cannot be shown here — open the run itself for ` +
        `that. The <b>balance_chain</b> check below is the arithmetic, and it ran on the full ` +
        `figures before anything was projected.</p>`);
    }

    const rows = account.rows;
    const currency = (rows[0] && rows[0].currency) || "";
    const closing = account.checks.find((c) => c.name === "closing_balance");
    let broken = 0;

    const body = rows.map((row, i) => {
      const next = rows[i + 1];
      if (!next) {
        return `<tr class="anchor"><td colspan="10">oldest row on this statement — the chain ` +
               `starts here</td></tr>`;
      }
      const expected = row.balance !== null && row.amount !== null ? row.balance - row.amount : null;
      const actual = next.balance;
      // Decimal money reconstructed as a float: compare at the penny, not at
      // machine epsilon, or every second link "breaks" for 1e-10.
      const holds = expected !== null && actual !== null && Math.abs(expected - actual) < 0.005;
      if (!holds) broken += 1;
      return `<tr class="${holds ? "holds" : "breaks"}" data-row="${i}">
        <td class="dim num">${i}</td>
        <td class="dim date">${esc(row.date)}</td>
        <td class="mono dim clip">${esc(row.reference || row.trnType)}</td>
        <td class="num">${plain(row.balance)}</td>
        <td class="op">−</td>
        <td class="num">${plain(row.amount)}</td>
        <td class="op">=</td>
        <td class="num">${expected === null ? "—" : plain(expected)}</td>
        <td class="num">${plain(actual)}</td>
        <td class="tick num">${holds ? "✓" : `off by ${plain(Math.abs((expected || 0) - (actual || 0)))}`}</td>
      </tr>`;
    }).join("");

    const anchor = closing
      ? `<tr class="anchor"><td colspan="10">closing balance — ${esc(closing.detail || "")}</td></tr>`
      : "";

    const note = broken
      ? `<span class="chip bad">${broken} link${broken === 1 ? "" : "s"} do not hold</span>`
      : `<span class="chip match">${rows.length - 1}/${rows.length - 1} links hold</span>`;

    return panel("the chain",
      note + trace("extract", "the extract pass"),
      `<table class="chain"><thead><tr>
         <th class="num">#</th><th>date</th><th>reference</th>
         <th class="num">balance</th><th></th><th class="num">amount</th><th></th>
         <th class="num">expected</th><th class="num">next row</th><th class="num"></th>
       </tr></thead><tbody>${anchor}${body}</tbody></table>`,
      true,
      `every row's balance, minus its amount, is the next row's · in ${esc(currency)}`);
  }

  /* --- transactions -------------------------------------------------------- */

  function rowsPanel(account, selected) {
    if (!account.rows.length) return panel("transactions", "", `<p class="empty">No rows.</p>`);
    const body = account.rows.map((row, i) => `
      <tr data-row="${i}" aria-selected="${selected === i}">
        <td class="dim num">${row.page === null ? "—" : "p" + row.page}</td>
        <td class="date">${esc(row.date)}</td>
        <td class="num">${money(row.amount, row.currency)}</td>
        <td class="clip dim" title="${esc(row.narrative)}">${esc(row.narrative)}</td>
        <td class="chipcell">${chip(row.cp)}</td>
        <td class="chipcell">${chip(row.pc)}</td>
        <td>${esc(row.classification) || "—"}</td>
        <td>${row.ready
          ? '<span class="chip match">ready</span>'
          : `<span class="chip unresolved" title="${esc(words(row.reason))}">needs a person</span>`}</td>
      </tr>`).join("");

    return panel(`${account.rows.length} transactions`,
      `<span class="note">click a row for its evidence</span>` + trace("resolve", "the resolve pass"),
      `<table class="rows"><thead><tr>
         <th>page</th><th>date</th><th class="num">amount</th><th>narrative, as the bank wrote it</th>
         <th>counterparty</th><th>project</th><th>class</th><th>export</th>
       </tr></thead><tbody>${body}</tbody></table>`, true);
  }

  /* --- journal entries ----------------------------------------------------- */

  function journalPanel(account) {
    const lines = account.journal || [];
    if (!lines.length) {
      return panel("journal entries", "", `<p class="empty">This run produced no journal lines. ` +
        `An empty table would read as “none were needed”, which is a different claim.</p>`);
    }

    // Group key falls back to the row: one profile stamps a batch id, the other
    // projects it empty, and a batch per row is the truth in that case.
    const groups = new Map();
    lines.forEach((line) => {
      const key = line.batch || line.row_id || "batch";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(line);
    });

    const currency = (account.rows[0] && account.rows[0].currency) || "";
    let unbalanced = 0;

    const body = [...groups.entries()].map(([key, group]) => {
      const debits = group.filter((l) => l.is_debit)
        .reduce((sum, l) => sum + (number(l.amount) || 0), 0);
      const credits = group.filter((l) => !l.is_debit)
        .reduce((sum, l) => sum + (number(l.amount) || 0), 0);
      const balanced = Math.abs(debits - credits) < 0.005;
      if (!balanced) unbalanced += 1;

      const head = `<tr class="batchrow"><td colspan="5">${esc(key)}
        <span class="${balanced ? "balanced" : "unbalanced"}">
          ${balanced ? `balances · ${plain(debits)} each side` : `does not balance · Dr ${plain(debits)} vs Cr ${plain(credits)}`}
        </span></td></tr>`;

      const rows = group.map((line) => `
        <tr>
          <td class="dim mono">${esc(line.row_id || "")}</td>
          <td>${esc(line.transaction_type || "—")}</td>
          <td class="side">${line.is_debit ? "Dr" : "Cr"}</td>
          <td class="num dr">${line.is_debit ? plain(line.amount) : ""}</td>
          <td class="num cr">${line.is_debit ? "" : plain(line.amount)}</td>
        </tr>`).join("");

      return head + rows;
    }).join("");

    const note = unbalanced
      ? `<span class="chip bad">${unbalanced} batch${unbalanced === 1 ? "" : "es"} do not balance</span>`
      : `<span class="chip match">${groups.size} batches, every one balances</span>`;

    return panel("journal entries", note + trace("journal", "the journal pass"),
      `<table class="journal"><thead><tr>
         <th>row</th><th>transaction type</th><th></th>
         <th class="num">debit</th><th class="num">credit</th>
       </tr></thead><tbody>${body}</tbody></table>`, true,
      `${lines.length} lines${currency ? ` · ${esc(currency)}` : ""}`);
  }

  /* --- checks -------------------------------------------------------------- */

  function checksPanel(account) {
    if (!account.checks.length) return panel("what the verifier said", "",
      `<p class="empty">No checks recorded.</p>`);

    const body = account.checks.map((check, i) => {
      const explanation = CM.explain.forCheck(check.name);
      const detail = check.evidence || explanation;
      return `<li class="st-${esc(check.status)}">
        <button class="line" data-check="${i}" aria-expanded="false">
          <span class="mark">${MARK[check.status] || "?"}</span>
          <span class="name">${esc(check.name)}</span>
          <span class="detail">${esc(check.detail || "")}</span>
          <span class="more">${detail ? "why" : ""}</span>
        </button>
        ${detail ? `<div class="evidence" hidden><pre>${
          esc(explanation)}${explanation && check.evidence ? "\n\n" : ""}${esc(check.evidence || "")
        }</pre><button class="btn quiet sm" data-trace-check="${esc(check.name)}"
          >show this in the log →</button></div>` : ""}
      </li>`;
    }).join("");

    const tally = tallyChecks(account.checks);
    const note =
      `<span class="chip match">${tally.PASS} pass</span> ` +
      (tally.FAIL ? `<span class="chip bad">${tally.FAIL} fail</span> ` : "") +
      (tally.UNRESOLVED ? `<span class="chip unresolved">${tally.UNRESOLVED} unresolved</span> ` : "") +
      (tally.CANNOT_VERIFY ? `<span class="chip cannot">${tally.CANNOT_VERIFY} cannot verify</span>` : "");

    return panel("what the verifier said", note, `<ul class="checks">${body}</ul>`, true);
  }

  /* --- review queue -------------------------------------------------------- */

  /* Ordered by exposure. A €15.7m suspense row and a €0.0000009 rounding gap are
     not equal work. Statement-level items carry no amount and go last rather
     than first — they were sorting above the biggest row on the statement,
     which is exactly the ordering this is meant to prevent. */
  function queuePanel(accounts) {
    const items = [];
    accounts.forEach((account) => {
      (account.queue || []).forEach((entry) => {
        const isCheck = entry.isCheck !== undefined ? entry.isCheck : !entry.row_id;
        items.push({
          account: account.account,
          reason: words(entry.reason),
          isCheck,
          amount: number(entry.amount),
          currency: entry.currency || "",
          text: isCheck
            ? `${entry.check || ""}${entry.detail ? ": " + entry.detail : ""}`
            : (entry.raw_narrative || entry.row_id || ""),
        });
      });
    });

    items.sort((a, b) =>
      (a.isCheck - b.isCheck) || (Math.abs(b.amount || 0) - Math.abs(a.amount || 0)));

    if (!items.length) {
      return panel("review queue", "", `<p class="empty">Nothing is waiting on a person.</p>`);
    }

    const body = items.map((item) => `
      <li>
        <span class="why ${item.isCheck ? "check" : "row"}">${esc(item.reason)}</span>
        <span class="amt">${item.amount === null ? "" : money(item.amount, item.currency)}</span>
        <span class="txt" title="${esc(item.text)}">${esc(item.account)} · ${esc(item.text)}</span>
      </li>`).join("");

    return panel(`review queue — ${items.length}, biggest first`, "",
      `<ol class="queue">${body}</ol>`, true);
  }

  /* --- evidence ------------------------------------------------------------ */

  function evidencePanel(account, selected) {
    if (selected === null || !account.rows[selected]) {
      return panel("evidence", "", `<p class="empty">Select a transaction. Every number on this ` +
        `page can name the page it was read from and the words it came from.</p>`);
    }
    const row = account.rows[selected];
    const file = account.source.filename || "";
    return panel("evidence", "", `<dl class="dl">
      <dt>row</dt><dd>${esc(row.id)} · ${row.ready
        ? '<span class="chip match">ready for export</span>'
        : `<span class="chip unresolved">${esc(words(row.reason))}</span>`}</dd>
      <dt>amount</dt><dd class="num">${money(row.amount, row.currency)} · ${esc(row.date)}</dd>
      ${row.balance !== null
        ? `<dt>balance after</dt><dd class="num">${plain(row.balance)}</dd>` : ""}
      <dt>read from</dt><dd>${esc(file)}${row.page !== null
        ? ` · page ${row.page}`
        : ' · <span class="chip bad">no page recorded</span>'}</dd>
      <dt>narrative, as the bank wrote it</dt>
      <dd><div class="quote">${esc(row.narrative)}</div></dd>
      ${row.reference ? `<dt>bank reference</dt><dd class="mono">${esc(row.reference)}${
        row.trnType ? " · " + esc(row.trnType) : ""}</dd>` : ""}
      ${row.cpRaw ? `<dt>counterparty pulled out of it</dt>
        <dd><div class="quote">${esc(row.cpRaw)}</div></dd>` : ""}
      <dt>counterparty</dt><dd>${chip(row.cp)}${row.cp.table
        ? ` <span style="color:var(--ink-faint)">from ${esc(row.cp.table)}</span>` : ""}
        ${row.cp.why ? `<div style="color:var(--ink-soft);margin-top:4px">${esc(row.cp.why)}</div>` : ""}</dd>
      <dt>project code</dt><dd>${chip(row.pc)}${row.pc.table
        ? ` <span style="color:var(--ink-faint)">from ${esc(row.pc.table)}</span>` : ""}
        ${row.pc.why ? `<div style="color:var(--ink-soft);margin-top:4px">${esc(row.pc.why)}</div>` : ""}</dd>
      <dt>classification</dt><dd>${esc(row.classification) || "—"}</dd>
      ${row.journalLines.length ? `<dt>journal lines</dt><dd>${row.journalLines.map((line) =>
        `${line.is_debit ? "Dr" : "Cr"} ${esc(line.transaction_type || "—")} ` +
        `<span class="num">${plain(line.amount)}</span>`).join("<br>")}</dd>` : ""}
    </dl>`);
  }

  /* --- assembly ------------------------------------------------------------ */

  function panel(title, note, body, tight, subnote) {
    return `<section class="panel">
      <header><h3>${title}</h3>${subnote ? `<span class="note">${subnote}</span>` : ""}
        <span class="spacer"></span><span class="note">${note}</span></header>
      <div class="body${tight ? " tight" : ""}">${body}</div>
    </section>`;
  }

  /* The result and the log are one run seen twice, so every panel can say
     "and here is where this came from". Rendered only when there is a trace to
     jump into — a dropped envelope has none, and a dead link is worse than no
     link at all. */
  function trace(stage, label) {
    if (!CM.output.hasTrace) return "";
    return ` <button class="btn quiet sm" data-trace-stage="${esc(stage)}">${
      esc(label)} in the log →</button>`;
  }

  CM.output = {
    /* `state` carries the selected account and row, and is mutated by the
       handlers wired at the end — the view is a pure function of it. */
    render(container, data, state) {
      const accounts = data.accounts;
      if (!accounts.length) {
        container.innerHTML = `<div class="pad"><p class="empty">Nothing to show.</p></div>`;
        return;
      }
      const account = accounts[Math.min(state.account, accounts.length - 1)];
      const allRows = accounts.flatMap((a) => a.rows);
      const ready = allRows.filter((r) => r.ready).length;
      const tally = tallyChecks(accounts.flatMap((a) => a.checks));

      // If this page's own gate disagrees with the backend's, say so rather
      // than rendering a number nobody can reconcile.
      const stated = accounts.reduce((sum, a) => sum + (a.statedClean ?? 0), 0);
      const known = accounts.every((a) => a.statedClean !== null);
      const mismatch = known && stated !== ready
        ? `<div class="notice bad">This page counts <b>${ready}</b> rows ready for export; the
           run's own envelope says <b>${stated}</b>. The viewer's rule has drifted from the
           backend's — trust the envelope, not this page.</div>`
        : "";

      /* A rejected run still has output on disk — the last thing the verifier
         refused. Showing it without saying so would present as a deliverable
         something the pipeline deliberately declined to emit, which is the one
         thing this product must never do. */
      const refused = state.rejected
        ? `<div class="notice warn"><b>This run was rejected, so none of this was emitted.</b>
           It is the last output the verifier refused${state.stage
             ? ` — the <b>${esc(state.stage)}</b> pass never satisfied its checks` : ""}. It is
           shown because reading what failed is the point of keeping it; it is not a deliverable.
           The failing checks are marked below.</div>`
        : "";

      const switcher = accounts.length > 1
        ? `<nav class="tabs" style="margin:-4px 0 16px">${accounts.map((a, i) =>
            `<button data-account="${i}" aria-selected="${a === account}">${esc(a.account)}
             <span class="count">${a.rows.length}</span></button>`).join("")}</nav>`
        : "";

      container.innerHTML = `<div class="pad">
        ${refused}
        ${mismatch}
        ${CM.exporter ? CM.exporter.bar() : ""}
        <div class="stats">
          <div class="stat"><span class="stat-value">${allRows.length}</span>
            <span class="stat-label">transactions</span></div>
          <div class="stat pass"><span class="stat-value">${ready}</span>
            <span class="stat-label">ready for export</span></div>
          <div class="stat unresolved"><span class="stat-value">${allRows.length - ready}</span>
            <span class="stat-label">need a person</span></div>
          <div class="stat ${tally.FAIL ? "fail" : "pass"}"><span class="stat-value">${tally.FAIL}</span>
            <span class="stat-label">failed checks</span></div>
          <div class="stat"><span class="stat-value">${accounts.flatMap((a) => a.checks).length}</span>
            <span class="stat-label">checks run</span></div>
        </div>
        <div class="split-bar">
          <i class="ok" style="width:${(ready / Math.max(allRows.length, 1)) * 100}%"></i>
          <i class="warn" style="width:${((allRows.length - ready) / Math.max(allRows.length, 1)) * 100}%"></i>
        </div>
        ${switcher}
        <div class="detail-grid">
          <div>
            ${chainPanel(account)}
            ${rowsPanel(account, state.row)}
            ${journalPanel(account)}
            ${checksPanel(account)}
          </div>
          <div class="sticky">
            ${evidencePanel(account, state.row)}
            ${queuePanel(accounts)}
          </div>
        </div>
      </div>`;

      if (CM.exporter) CM.exporter.wire(container, data, state.summary);

      container.querySelectorAll("[data-account]").forEach((button) => {
        button.onclick = () => {
          state.account = Number(button.dataset.account);
          state.row = null;
          CM.output.render(container, data, state);
        };
      });
      container.querySelectorAll("tbody tr[data-row]").forEach((tr) => {
        tr.onclick = () => {
          state.row = Number(tr.dataset.row);
          CM.output.render(container, data, state);
        };
      });
      container.querySelectorAll("[data-check]").forEach((button) => {
        button.onclick = () => {
          const body = button.nextElementSibling;
          if (!body) return;
          body.hidden = !body.hidden;
          button.setAttribute("aria-expanded", String(!body.hidden));
        };
      });
      container.querySelectorAll("[data-trace-check]").forEach((button) => {
        button.onclick = (event) => {
          event.stopPropagation();
          if (CM.output.onTrace) CM.output.onTrace({ check: button.dataset.traceCheck });
        };
      });
      container.querySelectorAll("[data-trace-stage]").forEach((button) => {
        button.onclick = (event) => {
          event.stopPropagation();
          if (CM.output.onTrace) CM.output.onTrace({ stage: button.dataset.traceStage });
        };
      });
    },
  };
})();
