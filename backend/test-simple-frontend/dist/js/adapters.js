/* Three input shapes, one internal shape.
   ---------------------------------------------------------------------------
   The console can be handed:

     1. a run's own rows.json          — richest: carries the running balance
                                          and the journal lines per row
     2. a `journal-entries` batch      — statement_rows / checks / journal_entries
     3. a `pipeline-validation` batch  — extracted_rows / verification_results,
                                          with resolution flattened to a status string

   They name the same things differently, so everything is normalised here and
   the rendering below sees one shape. A fourth profile would only need an entry
   adding to this file. That the same renderer draws all three is also a quiet
   check that they really are views of one run rather than three products.  */

(function () {
  "use strict";

  const { number } = CM.util;

  /* Mirrors the export gate in backend/app/emit.py. MATCH and CANNOT_VERIFY are
     settled — "the document named nobody" is a finding, not a gap. UNRESOLVED
     is not settled: somebody has to decide it. */
  const SETTLED = new Set(["MATCH", "CANNOT_VERIFY"]);

  function resolution(row, base) {
    const nested = row[base + "_match"];
    if (nested && typeof nested === "object") {
      return {
        status: nested.status || "",
        name: nested.matched_name || "",
        table: nested.table || "",
        confidence: nested.confidence,
        why: nested.why || "",
        // The envelope carried the detail, so a MATCH that names no source
        // list is a real defect rather than a limit of the format.
        detailed: true,
      };
    }
    const flat = row[base + "_status"];
    return {
      status: typeof flat === "string" ? flat : "",
      name: "", table: "", confidence: null, why: "",
      detailed: false,
    };
  }

  /* The gate, derived the same way the backend derives it — used only when the
     envelope has not already been through it. Order matters: a row with no
     citation is unusable whatever else resolved. */
  function gate(row, cp, pc, classification) {
    if (row.page === null || row.page === undefined) return "MISSING_SOURCE_CITATION";
    if (!SETTLED.has(cp.status)) return "COUNTERPARTY_UNRESOLVED";
    if (!SETTLED.has(pc.status)) return "PROJECT_CODE_UNRESOLVED";
    if (String(classification).toLowerCase() === "review") return "LOW_CLASSIFICATION_CONFIDENCE";
    return null;
  }

  function envelopeRow(row, index, account) {
    const cp = resolution(row, "counterparty");
    const pc = resolution(row, "project_code");
    const citation = row.source_citation || {};
    const classification = row.classification || "";
    const page = row.source_page !== undefined && row.source_page !== null
      ? row.source_page : (citation.page ?? null);

    let reason = row.review_reason;
    if (reason === undefined) reason = gate({ page }, cp, pc, classification);
    const ready = row.ready_for_export !== undefined
      ? !!row.ready_for_export
      : reason === null;

    return {
      index,
      id: row.row_id || `${account}-${String(index).padStart(3, "0")}`,
      page,
      date: row.transaction_date || row.value_date || "",
      amount: number(row.amount),
      // Envelopes do not project the running balance — the chain is a run-level
      // artefact. output.js says so rather than drawing an empty table.
      balance: null,
      currency: row.currency || "",
      narrative: row.raw_narrative || row.source_snippet || citation.snippet || "",
      snippet: citation.snippet || row.source_snippet || "",
      reference: "", trnType: "",
      cpRaw: row.counterparty_raw || "",
      pcRaw: row.project_code_raw || "",
      cp, pc, classification,
      journalLines: [],
      ready, reason,
      raw: row,
    };
  }

  function runRow(row, index, account) {
    const cp = resolution(row, "counterparty");
    const pc = resolution(row, "project_code");
    const classification = row.classification || "";
    const page = row.page ?? null;
    // A run's rows.json has not been through the gate — emit.py applies it on
    // the way out — so it is derived here with the same rule.
    const reason = gate({ page }, cp, pc, classification);

    return {
      index,
      id: `${account}-${String(index).padStart(3, "0")}`,
      page,
      date: row.value_date || row.post_date || "",
      // debit already carries its sign; credit and debit are never both set,
      // and one_amount_per_row is a check precisely because that must hold.
      amount: number(row.credit !== null && row.credit !== undefined ? row.credit : row.debit),
      balance: number(row.balance),
      currency: row.currency || "",
      narrative: row.narrative || "",
      snippet: row.narrative || "",
      reference: row.bank_reference || "",
      trnType: row.trn_type || "",
      cpRaw: row.counterparty_raw || "",
      pcRaw: row.project_code_raw || "",
      cp, pc, classification,
      journalLines: Array.isArray(row.journal_lines) ? row.journal_lines : [],
      ready: reason === null,
      reason,
      raw: row,
    };
  }

  /* Statement-level problems and row-level ones are different work, so the
     queue keeps them apart and output.js orders by exposure. */
  function deriveQueue(rows, checks) {
    const items = [];
    for (const check of checks) {
      if (check.status === "FAIL" || check.status === "UNRESOLVED") {
        items.push({
          reason: check.status,
          check: check.name,
          detail: check.detail || "",
          amount: null, currency: "",
          isCheck: true,
        });
      }
    }
    for (const row of rows) {
      if (!row.ready) {
        items.push({
          reason: row.reason || "NEEDS_REVIEW",
          row_id: row.id,
          raw_narrative: row.narrative,
          amount: row.amount,
          currency: row.currency,
          isCheck: false,
        });
      }
    }
    return items;
  }

  function journalFromRows(rows) {
    const lines = [];
    rows.forEach((row) => {
      row.journalLines.forEach((line) => lines.push({ ...line, row_id: row.id }));
    });
    return lines;
  }

  CM.adapters = {
    SETTLED,

    /* A batch envelope: either profile. */
    fromBatch(payload, label) {
      const accounts = (payload.accounts || []).map((entry) => {
        const envelope = entry.envelope || {};
        const account = entry.account || "";
        const raw = envelope.statement_rows || envelope.extracted_rows || [];
        const rows = raw.map((row, i) => envelopeRow(row, i, account));
        const checks = envelope.checks || envelope.verification_results || [];
        const summary = envelope.summary || {};
        const source = (envelope.source_files || envelope.input_documents || [])[0] || {};

        return {
          account,
          runId: entry.run_id || envelope.run_id || "",
          accepted: !!entry.accepted,
          attempts: entry.attempts,
          seconds: entry.seconds,
          model: entry.model || "",
          source,
          checks,
          rows,
          journal: envelope.journal_entries || [],
          queue: envelope.review_queue || deriveQueue(rows, checks),
          audit: envelope.audit_trail || null,
          hasChain: false,
          // The envelope's own count where it has one, so the page can say when
          // its derivation disagrees with the backend's rather than quietly
          // rendering a number nobody can reconcile.
          statedClean: envelope.export_candidates
            ? envelope.export_candidates.length
            : (summary.ready_for_export !== undefined ? summary.ready_for_export : null),
        };
      });

      return {
        kind: "batch",
        // Kept so an export hands back exactly what was loaded, unmodified.
        envelope: payload,
        label: label || payload.batch || "",
        batch: payload.batch || "",
        profile: payload.profile || "",
        accounts,
      };
    },

    /* One run, from its rows.json plus its summary.json. */
    fromRun(payload, summary) {
      const account = payload.account || (summary && summary.account) || "";
      const rows = (payload.rows || []).map((row, i) => runRow(row, i, account));
      const checks = payload.checks || [];

      return {
        kind: "run",
        envelope: payload,
        label: (summary && summary.run_id) || "",
        batch: (summary && summary.batch) || "",
        profile: payload.profile || (summary && summary.profile) || "",
        accounts: [{
          account,
          runId: (summary && summary.run_id) || "",
          accepted: !!payload.accepted,
          attempts: (summary && summary.attempts) || payload.attempt,
          seconds: summary && summary.seconds,
          model: (summary && summary.model) || "",
          source: { filename: payload.source_file || (summary && summary.source_file) || "" },
          checks,
          rows,
          journal: journalFromRows(rows),
          queue: deriveQueue(rows, checks),
          audit: null,
          // Only a run carries the running balance, so only a run can show the
          // subtraction. An envelope has to be taken on the balance_chain check.
          hasChain: rows.some((row) => row.balance !== null),
          statedClean: null,
          stage: payload.stage || "",
        }],
      };
    },
  };
})();
