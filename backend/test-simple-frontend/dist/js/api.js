/* Talking to serve.py, and the small helpers everything else shares.
   ---------------------------------------------------------------------------
   Two ways in. Served by serve.py, the console can list the runs on disk and
   read any of their artefacts. Opened straight off the filesystem it cannot —
   a file:// page may not fetch a sibling — so it falls back to a dropped file
   and says so rather than showing an empty list and letting you wonder.

   Classic script, no modules: `<script type="module">` is blocked on file://
   too, and losing the offline path to save one line of boilerplate is a bad
   trade for a viewer whose whole job is being easy to open.  */

window.CM = window.CM || {};

(function () {
  "use strict";

  const SERVED = location.protocol === "http:" || location.protocol === "https:";

  async function get(path, asText) {
    const response = await fetch(path, { headers: { Accept: "application/json" } });
    if (!response.ok) {
      let message = response.statusText;
      try { message = (await response.json()).error || message; } catch (_) { /* not JSON */ }
      throw new Error(`${path} — ${message}`);
    }
    return asText ? response.text() : response.json();
  }

  CM.api = {
    served: SERVED,

    health:     ()          => get("/api/health"),
    runs:       ()          => get("/api/runs"),
    run:        (id)        => get(`/api/runs/${id}`),
    trace:      (id)        => get(`/api/runs/${id}/trace`, true),
    /* A static deployment has no query strings — every stage would come back as
       the same file — so there the stage is a path segment the build wrote. */
    rows(id, stage) {
      if (!stage) return get(`/api/runs/${id}/rows`);
      return get(`/api/runs/${id}/rows${window.CM_STATIC ? `-${stage}` : `?stage=${stage}`}`);
    },
    file:       (id, name)  => get(`/api/runs/${id}/file/${encodeURIComponent(name)}`, true),
    examples:   ()          => get("/api/examples"),
    example:    (name)      => get(`/api/examples/${encodeURIComponent(name)}`),
    profiles:   ()          => get("/api/profiles"),
    statements: ()          => get("/api/statements"),

    /* Put a statement PDF where a run can find it. The console could otherwise
       only offer whatever documents happened to be in the repository, which
       makes it a demo of one dataset rather than a way to process a document. */
    upload(file) {
      return fetch(`/api/upload?name=${encodeURIComponent(file.name)}`, {
        method: "POST",
        headers: { "Content-Type": "application/pdf" },
        body: file,
      }).then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || response.statusText);
        return payload;
      });
    },

    launch(account, profile) {
      return fetch("/api/launch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account, profile }),
      }).then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || response.statusText);
        return payload;
      });
    },

    launchState: (id, since) => get(`/api/launch/${id}?since=${since || 0}`),
  };

  /* --- formatting --------------------------------------------------------- */

  const CURRENCY_KNOWN = /^[A-Z]{3}$/;

  CM.util = {
    /* Everything user-supplied goes through here on its way into innerHTML.
       The rows come out of a bank statement and the checks out of a model, so
       nothing rendered below is trusted markup. */
    esc(value) {
      return String(value === null || value === undefined ? "" : value)
        .replace(/[&<>"']/g, (c) => (
          { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
        ));
    },

    /* Amounts arrive as numbers from an envelope and as decimal strings from a
       run's rows.json — the backend keeps Decimal precision on the way out, so
       "-44.83" is normal and must not be treated as a parse failure. */
    number(value) {
      if (value === null || value === undefined || value === "") return null;
      const parsed = typeof value === "number" ? value : Number(String(value).replace(/,/g, ""));
      return Number.isFinite(parsed) ? parsed : null;
    },

    money(value, currency) {
      const parsed = CM.util.number(value);
      if (parsed === null) return "—";
      if (currency && CURRENCY_KNOWN.test(currency)) {
        return new Intl.NumberFormat("en-GB", {
          style: "currency", currency, currencyDisplay: "code",
        }).format(parsed);
      }
      return new Intl.NumberFormat("en-GB", {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
      }).format(parsed);
    },

    /* No currency prefix — for the chain, where five money columns sit side by
       side and repeating "DKK" five times per row destroys the alignment that
       is the entire point of the table. */
    plain(value) {
      const parsed = CM.util.number(value);
      return parsed === null ? "—" : new Intl.NumberFormat("en-GB", {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
      }).format(parsed);
    },

    seconds(value) {
      const parsed = CM.util.number(value);
      if (parsed === null) return "";
      if (parsed < 60) return `${parsed.toFixed(0)}s`;
      const minutes = Math.floor(parsed / 60);
      return `${minutes}m ${String(Math.round(parsed % 60)).padStart(2, "0")}s`;
    },

    words(value) {
      return String(value || "").replace(/_/g, " ").toLowerCase();
    },

    el(html) {
      const holder = document.createElement("div");
      holder.innerHTML = html.trim();
      return holder.firstElementChild;
    },
  };
})();
