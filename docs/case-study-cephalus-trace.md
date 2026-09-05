# Case study: the Cephalus trace

One payment of **€301,908.70**, followed from the bank's PDF to the two journal
lines it becomes — through every stage of the four-agent flow, with the checks
that catch it when a stage gets it wrong.

Source material is the anonymised Ylookup hackathon dataset. All entities,
counterparties and identifiers are replacements; amounts, dates and balances are
untouched and still tie.

---

## The input

Statement `20260331_NI_A_B__FUND_II_CALDER_EUR_8102.pdf` — account `NI ABF II SCSP`,
Calder Luxembourg, EUR, `240-149813-030`.

```
10716RS62GWQ  CEPHALUS TRF  TFR-  31 Mar 2026   -301,908.70   20,088.76  11:01
Narrative  NI ABF I SCSP, PMT FRM NI ABF II SCSP TO NI ABF I, SCSP FOR
           PURCHASE 100PER OF ACC INT, IN CEPHALUS BIOGAS 001 LTD PREMIUM,
           ACCRUED INTEREST PROJECT CEPHALUS
```

That is the entire input. Everything the system produces has to come out of those
four lines plus the reference data, and every value has to stay traceable back to
them.

### Why this row

Three payments settled the same day, on the same account, to the same
counterparty, under the same customer reference `CEPHALUS TRF`:

| Reference | Narrative verb | Amount (EUR) | Correct position |
|---|---|---:|---|
| `10716RS62GWQ` | `PURCHASE 100PER OF ACC INT` | 301,908.70 | Funding Loan |
| `85720JS23WNK` | `ACQ 100PER OF SHARES … (EQUITY)` | 2,013,809.89 | Equity |
| `24381JR11YY3` | `PURCHAS 100PER OF LOAN PRINCIP` | 4,232,000.00 | Funding Loan |

Every field a naive extractor keys on is identical across all three. The only
thing separating equity from loan is the verb phrase — and note `PURCHAS`, cut
mid-word, because the bank wraps narrative text at a fixed width without regard
for word boundaries.

**This is not an extraction problem. It is a classification problem under a
rulebook**, which is why it currently costs a person their week.

---

## Stage 1 — Resolver

*Turn the bank's shorthand into canonical identifiers.*

The bank writes names truncated, in capitals, and wrapped mid-word. The master
lists hold the clean full name. Bridging those two is the bulk of the work, and
nothing downstream can start until it is done — which is why the original
"Storage Keeper" framing understated this stage. It is not storage, it is
resolution.

| In — as written | Out — resolved | Via |
|---|---|---|
| `240-149813-030` | `NI ABF II - Calder - EUR - 8102` | Account Map |
| `NI ABF I SCSP` | `NI ABF I SCSp` | Related Party Master |
| `CEPHALUS` | `Cephalus` | Project Code Report |
| — | `Nordvik Infrastructure Advanced Bioenergy Fund II SCSp` | Legal Entity Master |

Look at the counterparty match: `NI ABF I SCSP` against `NI ABF I SCSp`. A single
character of case decides whether the row books to a named related party or falls
into suspense. Nine reference lists sit behind this stage; the largest is 6,637
rows of deals and positions.

> **Where it fails.** 52 of the 100 rows in this week have no counterparty match
> at all. That is not a defect in the data — it was preserved deliberately from
> the original. It is the honest hit rate of the hardest step, and the reason the
> next stage must be able to proceed without it.

---

## Stage 2 — Classifier

*Apply the rulebook: what kind of movement is this?*

Six outcomes are available — Investment, Investment Transfer, Vendor, Related
Party, Investor, Internal — plus `Review` when the row resolves to none of them.
On top of that sits the equity-or-loan call, and that is where the judgement
lives.

| Field | Value |
|---|---|
| Discriminator | `… OF ACC INT … ACCRUED INTEREST` |
| Reading | accrued interest → **Loan** |
| Sign on the statement | debit — money leaving |
| Classification | `Investment Transfer` |
| Cash leg transtype | `Cash - Disbursed - EUR` |
| Counterparty transtype | `Payable - Third Party` |

The whole classification turns on reading `ACC INT` as accrued interest rather
than an account number, and knowing that accrued interest attaches to a loan
rather than equity. Its sibling row, `ACQ 100PER OF SHARES`, takes the other
branch on the same logic.

Get this backwards and every field after it is wrong *while looking perfectly
well-formed*: the amount still ties, the counterparty still matches, the batch
still balances. It just posts against the wrong position.

> **Why the check goes here, not at the end.** The working file's own `Process`
> sheet opens with the line *"each value is only as good as the stage before
> it."* A misclassification is invisible in the finished journal. It is only
> catchable here, against the narrative it came from.

---

## Stage 3 — Builder

*Resolve the position and write the double entry.*

With the classification settled, the position under the deal follows, and the two
journal lines are mechanical. One statement row becomes exactly two lines sharing
a batch: the cash side and the counterparty side, equal and opposite.

Resolved deal: `Cephalus Biogas 001 Limited - EUR`
Resolved position: `Cephalus Biogas 001 Limited - EUR (Funding Loan)`

| Batch · Trans | Transaction type | Account | Dr/Cr | Amount (EUR) | Allocation |
|---|---|---|---|---:|---|
| 2 · 1 | `Payable - Third Party` | `20500.5` | Debit | 301,908.70 | No Allocation |
| 2 · 2 | `Cash - Disbursed - EUR` | `10000.1` | Credit | 301,908.70 | Non Dominant |

Both accounts are live entries in the chart of accounts — `10000.1` is Cash – EUR
under Assets, `20500.5` is Payable – Third Party under Liabilities. The debit line
also carries `NI ABF I SCSp` in its Related Party field, which is the value
Stage 1 fought for.

---

## Stage 4 — Reconciler

*Prove it foots before a human ever looks.*

This is the agent the original flow did not have, and the one the client interview
asks for by name. It runs three checks, none of which need judgement — only
arithmetic that nobody is currently doing.

- **Double entry.** Every batch nets to zero. Across this week: 100 batches, 200
  journal lines, **100 of 100 balanced to the cent** — including batch 2 above.
- **Movements reconciliation.** Debits less credits, per entity per account,
  before anything is uploaded. On the migration tranche that is 690 rows whose
  grand total lands at **−0.0000001** — floating-point zero.
- **Mapping gaps, ranked by exposure.** Two gaps in the tranche, and they are not
  equal: one covers 11 rows worth **€4,867.16** and already carries a proposed
  target account awaiting approval; the other covers 8 rows worth
  **€0.0000000000009**. Same status, opposite urgency.

> There is a quality control gap where nobody reads it and asks whether this
> number foots to that number. How does my balance sheet have nothing in common
> with my equity balance?
>
> — fund manager, call 1 (anonymised transcript)

He goes on to say he no longer reads what his administrator sends — he runs it
through an AI tool first, which returns a forty-point memo of what is wrong. He
has already built this agent, by hand, because nobody supplied it.

---

## The suspense lane

A pipeline that halts on every unmatched row processes nothing. The working
file's answer — and ours — is a designed third outcome: book the row to a
suspense account, carry it forward with its batch, and flag it. Parked, not
blocked, and the batch still balances.

In this week's hundred rows that means:

- 52 with no counterparty match
- 30 project codes that do not resolve to the project code report
- 4 positions absent from the deal and position master
- 3 rows flagged `Review` outright

Six rows end up booked to `Suspense (debit)` or `Suspense (credit)`. One of them:

| Field | Value |
|---|---|
| Narrative | `NI V FENWICK HOLDCO LTD … LOAN: FROM NORDVIK INFRASTRUCTURE V SCSP TO …` |
| Counterparty pulled | `NI V Fenwick Holdco Ltd.` |
| Counterparty matched | *no match* |
| Booked to | `Suspense (debit)` |
| Amount | 1,160,696.30 |

The narrative names a real entity, but with a trailing full stop the master list
does not carry. The amount is material, so it ranks high in the review queue —
and the batch still balances, because suspense absorbs the counterparty leg.

---

## Two loops, and only one of them is expensive

Everything above exists to protect the last step.

The **reconciler's loop is cheap**: it runs against the builder's output as many
times as it needs to, costs nothing but compute, and stops when the arithmetic
comes back clean.

The **fund manager's loop is the opposite** — each pass costs a day or two of
somebody's attention, and the last NAV took six of them.

So the review queue does not hand over a list of problems. It hands over
**proposed fixes, ranked by exposure**: the €1.16m suspense row above the €4,867
mapping gap above the row worth nine ten-thousandths of a cent. The unit of work
is a decision, not an investigation.

> I am not sensitive to whether a turn took an hour or forty-eight hours. What I
> care about is the count of turns.
>
> — fund manager, call 1 (anonymised transcript)

That sentence is the specification. It is why latency is not the metric and turn
count is.

---

## What this is worth

| | |
|---|---|
| Turns on the last NAV | **6** — each a day or two of the fund manager's time |
| Target | **1** — everything machine-checkable resolved before the first hand-off |
| Rows with a known answer | **100** — the workbook ships the verified journal, so a run can be scored rather than admired |

---

## Where the numbers come from

- Statement `20260331_NI_A_B__FUND_II_CALDER_EUR_8102.pdf` and the working file's
  `Staging Sheet`, `DIU` and `Process` sheets — dataset 01.
- Movements reconciliation and mapping gaps from *Tranche 1 — reference and
  verified loader v4c* — dataset 02.
- Quotations from the anonymised transcript of call 1, the NAV workflow review.

The balance and reconciliation figures were recomputed from the workbooks rather
than read off a summary sheet. The unmatched counts are the ones the dataset
README states were preserved from the original on purpose — they are the
difficulty of the exercise, not defects to clean up.

**The target of one turn is our stated goal, not something the data measures.**

---

*Companion to the Agent flow v2 diagram. See also [`business-case.md`](business-case.md)
for the LP-side screening case and [`FRONTEND.md`](FRONTEND.md) for the integration guide.*
