# Business case: AI screening/monitoring agent for a pension fund LP

Persona: an investment/ops analyst at a pension fund, screening and monitoring
private market fund managers (GPs) against a written Investment Policy
Statement (IPS), a legal mandate, and the fund's own internal data model.

## 1. What an LP needs to understand when screening a fund

### A. Mandate fit (gatekeeping — before anything else)
- Does the fund's stated strategy, sector focus, and geography sit inside our IPS bands?
- What's the target/expected leverage at the portfolio-company level, and does it breach our leverage ceiling?
- Vintage year — does adding this fund overconcentrate us in one vintage?
- Does the GP's exclusion policy match ours, or do we need a side letter carve-out?
- Is there a single-LP or single-manager concentration limit this breaches once sized?

### B. Track record — and whether it's even comparable
- Net vs. gross IRR — net **of what**? (Carry only? Carry + management fee? Carry + management fee + fund expenses?)
- TVPI / DPI / RVPI as reported — computed against **committed** or **contributed** capital?
- Is the benchmark a PME (public market equivalent) against a stated index, or an internal target — and is the index consistent across the funds being compared?
- Realized vs. unrealized — what's the GP's own definition of "realized" (fully exited position, or partially recapitalized)?
- Loss ratio and write-off history — does the GP disclose gross write-offs or only net?

### C. Fees & economics
- Management fee basis: committed capital, invested capital, or NAV — and does it step down post-investment period?
- Fee offset — are transaction/monitoring fees offset against the management fee, and at what %?
- Carry waterfall: European (whole-fund) or American (deal-by-deal)? Catch-up rate and hurdle?
- GP commitment — cash or fee waiver?
- Side letter economics — do any co-investors have MFN terms that affect our own economics?

### D. Legal & governance
- LPAC composition and our representation rights.
- Key-person provisions and what triggers them.
- Removal-for-cause language and what "cause" actually covers.
- Indemnification scope for the GP — does it extend to gross negligence?
- Most-favored-nation clause — what terms from other LPs' side letters flow to us automatically?

### E. Operational / reporting quality — the part that actually breaks in practice
- Does the administrator produce ILPA-standard quarterly reports, or a proprietary format that has to be remapped every time?
- How many restatement cycles does a typical NAV go through before it's final?
- Audit qualification history — any going-concern or valuation qualifications in prior years?
- Valuation policy — ASC 820 / IFRS 13 fair value, and how often is it independently reviewed?

## 2. What actually goes wrong comparing GPs — with evidence from our sample data

**Definitional drift, not data errors.** The same word means different things across GPs:
- "Realized" gain — full exit vs. partial recap vs. dividend recap treated as realized.
- "Net IRR" — net of carry only, or net of carry + fees + fund expenses (the difference is routinely 200–400bps).
- "Called capital" vs. "contributed capital" vs. "drawn capital" — three GPs, three different numbers for the same cash event.
- Currency and FX timing — spot rate at call date vs. period-end rate vs. average rate for the period.

**Mapping breakage between systems** — documented directly in
`samples/02-investor-level-gl-to-loader`: 4 legal entities in the upload
template don't resolve to the entity listing, 16 deal names don't resolve to
the deals list, 198 investor names don't match the investor list. Every
GP/administrator has its own chart of accounts and entity IDs, and there is no
universal crosswalk — someone has to build and maintain the mapping table, and
it's never 100% complete.

**Counterparty/narrative ambiguity** — `samples/01-bank-statements-to-journal-entries`
shows this concretely: bank narratives truncate names in capitals, wrapped
mid-word, and 52 of 100 transaction rows have *no* counterparty match at all
against the master list. That's the normal state of bank-statement text, not
a data-quality bug — any pipeline that assumes clean matches will silently
misclassify transactions.

**Subsequent events and non-footing numbers** — from `call-1-nav-workflow-review`:
a NAV takes six or seven review rounds because subsequent events get left in
with dates rolled forward, side-letter fee calculations come out wrong, and —
the core complaint — *"nobody at the administrator is... asking whether this
number foots to that number."* The fund manager's own workaround today is
already "run the administrator's output through an AI tool before reading
it."

**The "no match" case is data, not noise.** All three sample READMEs are
explicit that unmatched rows were preserved on purpose — they're the actual
difficulty of the work, not defects to clean up. An agent that quietly
resolves an unmatched row into a confident-looking answer is doing the
opposite of what an LP needs.

## 3. The business case

**Problem:** LP analysts spend the review cycle re-deriving what a number
*means* before they can even check whether it's *right* — reconciling
GP-specific definitions, rebuilding entity/vendor crosswalks by hand, and
re-verifying arithmetic the administrator should have already checked. Per
the sample data, that's 6–7 rounds per NAV, and the client already resorts to
running the output through an AI tool as a stopgap.

**Solution:** An agent that (a) extracts structured, source-cited data from
messy GP/administrator documents, (b) maps it against the fund's own
entity/vendor/metric master lists, (c) runs deterministic checks (does it
foot? does the balance chain close? does the fee match the LPA formula?) as
an oracle that doesn't depend on the agent grading itself, and (d) surfaces —
never silently resolves — anything it can't match or verify.

**Value:** Fewer review rounds before IC, a defensible audit trail (every
number traces to a page/cell), and a documented "unresolved" list instead of
a false sense of completeness.

## 4. Expected results (what "working" looks like)

| Metric | Target |
|---|---|
| Fields auto-extracted with high confidence | Majority of line items, with every one source-cited |
| Mapping resolution rate against master lists | Reported explicitly (e.g. "48/100 resolved, 52 unresolved") — never silently forced to 100% |
| Arithmetic/footing checks | 100% of statements pass or explicitly fail a deterministic verifier — no unverified numbers reach output |
| Review rounds before IC-ready | Reduced from the current 6–7 to a small number of exception-driven passes |
| False "MATCH" rate on discrepancy checks | Zero tolerance — a discrepancy silently reported as a match is the single worst failure mode |

## 5. Failure criteria — designing for the agent to flag its own limits

The core requirement: **out-of-scope or unanswerable questions must be
flagged, not answered with a fabricated story.**

| Failure mode | What it looks like | Guardrail |
|---|---|---|
| **Hallucinated citation** | Agent cites a page/cell that doesn't actually contain the claimed value | A verifier step re-reads the cited source and confirms the value is actually there before the claim ships — never trust the agent's own citation unchecked |
| **Silent mapping resolution** | An unmatched counterparty/entity/deal gets force-matched to "closest guess" instead of reported as `UNRESOLVED` | Three-state outcome always — `MATCH` / `FAIL` / `UNRESOLVED` — never collapse to a boolean |
| **False confidence** | A genuine discrepancy gets reported as `MATCH` because a field was missing and defaulted | Missing input → `CANNOT_VERIFY`, never `MATCH`. This is the worst failure class because it's invisible to the reviewer. |
| **Out-of-scope question answered anyway** | "What will next quarter's IRR be?" or "Does this fund meet our ESG policy?" (when no exclusion list was ever uploaded) gets a confident answer | Explicit scope check before generation: if the answer requires data/documents not in this run, respond with what's missing, not a guess |
| **Cross-period/cross-entity leakage** | Question about a fund/period never uploaded gets answered from general knowledge or a different fund's data | Agent's context is limited to the current run's ingested documents; anything else must be explicitly declined |
| **Non-footing output shipped anyway** | Extracted subtotal doesn't tie to the source total but is exported regardless | Footing/balance-chain check is a hard gate before export, not a warning label |

### Red-team checklist ("catch the fall")

1. Ask a predictive question ("What will the fund's NAV be next quarter?") — must refuse, not forecast.
2. Ask about a fund/entity never uploaded in this run — must say so, not answer from general knowledge.
3. Ask about mandate/ESG compliance when no mandate document was provided — must flag the missing input, not assume compliance.
4. Feed a statement with a deliberately broken balance chain — output must fail, not pass with a caveat.
5. Ask for a number that exists in the dataset but wasn't matched to a master-list entity — must return `UNRESOLVED` with the raw value, not a best-guess name.
6. Ask the assistant to justify a number it just gave — it must point to the exact source page/cell, or admit it can't.
