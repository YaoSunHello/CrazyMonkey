# prompt

You are writing one Python file that will run once, in a sandbox, and produce a
single JSON result. A module `kit` is already available — import it, do not
rewrite it, and do not install anything.

Rules that hold for every task:

- Write the result exactly once, at the end, with the kit's write function.
- Never invent or adjust a value to make a check pass. A value you cannot read
  is a value you leave out, and the checks will say so plainly.
- **Print what you need to see.** Everything your script prints comes back to
  you if the attempt is rejected, so stdout is how you look at the data: the
  values that did not match, what the reference data holds near them, how many
  rows a pattern actually caught. A number you assumed is a number you will get
  wrong. Finish with a one-line summary, e.g. "parsed 16 rows".
- Reply with the complete contents of the file in a single ```python code block,
  and nothing else.

## What the checks are, and how much to trust each kind

You will be judged by checks, and knowing what they can and cannot see is part
of doing this well. They are not one thing.

**A check about a number or about existence is proof. Trust it completely.**
Does this balance chain close, does this batch net to zero, is this value
actually present in the list it claims, does this string really appear in the
document. There is no judgement in any of it. If one of these objects, it is
right and you are wrong — find the cause and fix it. Never argue with
arithmetic, and never adjust a figure to quiet it.

**A check that reports a count or a share is a measurement, not a verdict.**
How much *ought* to resolve is a fact about the document in front of you, and
the check cannot read it. One source is full of dealings with outside parties;
another is almost entirely internal movements naming nobody, and there a high
unresolved count is the correct answer rather than a failure. Read the number,
decide whether it is right *for this document*, and say why.

**You are the one who reads. Where no exact check contradicts you, your reading
stands.** A check works on shapes and strings; it cannot know what a name means
or which party a sentence is about. If something is obvious to you and nothing
exact says otherwise, go with it and record your reasoning.

**Never contort an answer to satisfy a rule you can see is crude.** If a check
would be quieter with a worse answer, give the better answer and explain the
disagreement in plain words. A reviewer can weigh that. What they cannot do is
recover the truth from an output bent to please a rule — and a wrong value that
passes silently is far more expensive than an honest one that gets discussed.

The point of all this is a result somebody can act on: correct where it can be
proved, judged where it must be, and clearly flagged where it is neither.

## How many tries you have

3 round(s) to look at the data first, then up to 6 attempts at the real file. Aim to be right in the first two or three: each attempt costs a full rewrite, and the later ones exist for problems you could not have foreseen, not for a plan you have not made yet.

If you reach the last attempt and something still will not come good, do not gamble on a rewrite. Submit what you have with that part honestly marked — unresolved, or proposed with your reasoning — because incomplete work that says where it is incomplete goes forward and gets reviewed, while a run that risks everything on one more try can end with nothing to show at all.

## The tools you have

Imported as `kit`. These signatures are read from the module itself, so
they are exactly right — do not guess at an argument, and do not rewrite
one of these by hand.

    kit.rows()
        The rows the extraction pass produced, verified before they got here.
    kit.tables()
    kit.table(name)
    kit.lookup(value, pools, markers = None, source = None)
        Find `value` in the first of `pools` that holds it. Exact only.
    kit.candidates(value, pools, limit = 5, source = None)
        Near misses worth a person's judgement, ranked by what they share.
    kit.narrative_span(narrative, name)
        The slice of `narrative` that `name` corresponds to, exactly as written.
    kit.variants(text, wrapper = ',')
        Every plausible reading of a value the source document line-wrapped.
    kit.trim_to(text, markers, keep = True)
        Cut a string at the first of `markers`, keeping the marker by default.
    kit.normalise(value)
        One string form for a cell, so lookups survive the source's whitespace.
    kit.fold(text)
        The form two strings are compared in. Case and accents removed.
    kit.compact(text)
        Folded, with every non-alphanumeric removed.
    kit.batches_balance(rows, field = 'journal_lines')
        Check your own double entry before you submit. Every batch nets to zero.
    kit.questions()
        The questions this run is asked, and what each one needs to be answered.
    kit.write_result(enriched)
    kit.write_assertions(claims)
        Record what you checked about your own output, and what you found.

The transaction rows have already been extracted and their arithmetic verified.
Your job is to resolve each row against the reference lists and classify it.

    t = kit.table(name)
      t.columns / t.contains(col, v) / t.find(col, v) / t.values(col)
**Do not hand-roll normalisation, comma-unwrapping or a variant ladder.**
`kit.lookup` already does all of it — accents, case, a wrap character in
either position, and a qualifier the list adds that the document omits.
Every previous run rewrote these by hand and roughly half got them subtly
wrong.

`kit.tables()` names what this run mounted, and `kit.table(name)` opens one.
Print a few values from the lists named above before you decide anything —
see how they spell a name, see which list a party is likely to be on.

Emit every input row, in the same order, with these keys added and every
original key kept unchanged:

    counterparty_raw     the party's name exactly as the narrative writes it,
                         or null if the narrative names none
    counterparty_match   {status, matched_name, table, confidence, why}
    project_code_raw     the project word exactly as written, or null
    project_code_match   {status, matched_name, table, confidence, why}
    classification       one of the labels listed below

`status` is one of:

    MATCH          `kit.lookup` found it. Copy `matched_name` and `table` from
                   what it returned — the list's spelling, not the document's.
    PROBABLE       lookup failed, but a candidate is obviously the same thing.
                   Give `matched_name` (from `t.candidates`, so it is a real
                   list entry), `table`, a `confidence` strictly between 0 and 1,
                   and a `why` saying what differed. See below.
    UNRESOLVED     a name was read out of the narrative and nothing plausible
                   was found. Keep `counterparty_raw`; `matched_name` is null.
    CANNOT_VERIFY  the narrative names nobody, so there was nothing to look up.
    FAIL           the row is malformed and you cannot proceed.

## Do not decide where the name ends. Let the lookup decide.

This is the single most important instruction here, and it reverses what
seems natural.

A bank narrative is unpunctuated, abbreviated and wrapped mid-word, so any
rule for where a party name starts and stops is a guess. Every guess tried
so far has failed the same way: it fires on some rows, silently misses on
others, and you cannot tell which from inside the code.

**So do not guess. Enumerate, and check.** Take the narrative, generate the
candidate substrings that could plausibly be a name, look each one up, and
keep the ones that are actually in a reference list. A span that resolves is
*verified by the reference data*; a span you reasoned your way to is not.
The kit already works this way for line-wraps — `kit.variants` returns the
readings and lets `kit.lookup` pick — and the same logic applies to spans.

Concretely: a contiguous run of words is a candidate. Try them. This is
cheap, and it is measurably better than being clever: on rows where careful
boundary logic found nothing, exactly one list name was present in the
narrative the whole time.

## Find the document's own convention before you work row by row

One system wrote every row of this statement, so whatever it does, it does
throughout. Work out what that is by testing, not by reading one narrative:
run your candidate rule over ALL the rows, count how many resolve, and keep
the rule that wins. Which part of the narrative carries the counterparty —
the leading field, a clause after a keyword, somewhere else — is usually
fixed for a document, and deciding it once from evidence beats guessing it
sixteen times. Print the counts; a rule that resolves three rows where
another resolves eleven is not a close call.

## The lists spell the same party more than one way

Master data holds a company under its full name in one place and a house
abbreviation in another, and a narrative may use either. The two share no
words, so no amount of string comparison connects them — but the
correspondence is sitting in the reference data itself, because both forms
are in there.

You can recover it: take the leading words of one entry, take their initials,
and look for entries that begin with exactly those letters. Build that map
once from the lists you are given, then use it when a narrative writes a
party one way and the list you need holds it the other. Everything you
resolve this way is still a real entry in a real list, so it is checkable —
and where the expansion is a judgement rather than a derivation, say so with
PROBABLE and a reason.

Then use judgement on what comes back:

- **exactly one name resolves** — that is the counterparty, unless it is this
  account's own party (see below), in which case keep looking
- **several resolve** — the narrative names more than one party. In order:
      1. drop this account's own party
      2. **drop any whose numbers, numerals or ordinals differ from the text you
         read.** Sibling entities differ by one numeral and nothing else, and
         that numeral is never noise — it is the whole difference between two
         companies. This is the single most common way the wrong party is
         chosen, because the siblings otherwise look identical
      3. of those left, prefer the one accounting for MORE of what the document
         actually wrote. A list may hold both a bare name and the same name with
         a qualifier; if the narrative carries something the qualifier explains,
         the qualified entry is the better answer, not the shorter one
      4. say in `why` how you chose
- **none resolve** — now the name may be present in a form no list holds
  exactly. That is what PROBABLE is for; see below

Emit `counterparty_raw` using `kit.narrative_span(narrative, matched_name)` so
it is the document's own characters. That is what the provenance check reads.
It is judged on being a plausible name, so keep it to the name: a span carrying
the purpose of the payment as well will be rejected, and so will one long enough
to be a clause rather than a party.

## Proposing, when it is obviously the same company

A name the document spells one way and a list spells another is still one
company, and throwing it away as UNRESOLVED leaves a person to work it out
from nothing. Offer it instead, with your reasoning attached:

    {"status": "PROBABLE", "matched_name": "<the list's own spelling>",
     "table": "<which list>", "confidence": 0.8,
     "why": "<the one-line reason these are the same party>"}

Differences small enough to propose: trailing punctuation, an abbreviated or
spelled-out legal form, a wrap character, case or accents, a qualifier the
list adds, an initialism the document expands or the list contracts. Judgement
is the point here — this is the part no string comparison settles, and it is
why a model rather than a script is doing the work. A proposal is never
applied; it routes to a person with the answer already filled in.

**Differences that are NOT small, and must stay UNRESOLVED:**

- a differing number, numeral or ordinal anywhere in the name — those
  distinguish sibling entities and are never noise
- a differing currency or jurisdiction where the rest also differs
- anything you cannot state a one-line reason for

Never propose from `t.candidates` without reading the candidate and satisfying
yourself. A wrong proposal costs a reviewer a click; a wrong MATCH goes into
the accounts.

## What is provable here, and what is yours to judge

The engine's rules above say how much to trust each kind of check. This is
what those kinds are for this task, so you know which ground you are on.

**Provable, and not open to argument.** A name you return must be in the list
you name it from. A span you report must appear in that row's own narrative. A
status must be one of the declared ones. If a check says otherwise it is right;
the value is wrong, not the check.

**Yours to judge, because reading is the whole of it.** Which party in a
narrative is the counterparty and which is the account itself. Whether a name
the document spells one way and a list spells another is one company or two.
What kind of movement a row records. No check decides these and none can — a
check compares strings, and none of these questions is about strings.

**Measurement, to be read and weighed.** How many rows named a party, how many
resolved, how often you fell back to the last-resort label. These are counted
and reported, not graded. Decide whether each is right for the document you
have read, and say so.

Hold your own work to the same split. When you check yourself, prove anything
numeric by computing it rather than asserting it, and where the question is a
reading, record the reading and your reason for it.

## The counterparty is the other party

A narrative often names both sides of a movement. The account these rows came
from belongs to one of them, and **that one is not the counterparty**. Take
the other. Each row carries its own `account_number`; work out whose account
is — the account-to-owner mapping named above tells you, and the statement's
own entity is also the name that recurs on nearly every row.

Read the owner's entry and understand it: it identifies an *account*, so it
carries things a company name never does — a branch, a currency, the account
number. Judge which part of it is the entity. Then judge whether a candidate
is that entity or merely a relative of it. Entities in one family share most
of their words and differ in one — a numeral, a legal form, a single word —
and that one difference is the whole difference between the account holder
and a genuine counterparty. Nothing checks this for you, because nothing can
read a name as well as you can; get it wrong and a real party is discarded or
the statement is booked against itself.

## Judge how well you did, for this document

There is no fixed share of rows that ought to resolve. One statement is full
of payments to outside parties; another is almost entirely internal movements
that name nobody but the account itself, and on that one a high unresolved
count is the correct answer rather than a failure. Only you can tell which
you are holding, because only you have read it.

So count your own work and say whether it is right **for this statement**:
how many rows named a party, how many of those resolved, how many you
proposed, how many name nobody at all. If the numbers look wrong to you, go
back to the rows behind them before you submit. If they look right, say why.
Record it with `kit.write_assertions` — a claim that does not hold fails the
attempt and tells you where to look, and a claim that holds cannot rescue a
failing one, so there is nothing to gain by overstating.

Anything you cannot settle, flag rather than force: a `PROBABLE` with your
reasoning, or `UNRESOLVED` saying what would settle it. A person reads those,
and a flagged row costs them one decision — a wrong one costs them the trust
in every other row you produced.

## Which list to prefer

The same party can appear on more than one list in different forms. Decide an
order and apply it consistently — look at what the lists actually contain and
at what the downstream journal needs, rather than trying them arbitrarily.
Say in `table` which list you took the name from.

A list entry may carry a qualifier the narrative never writes, such as a
currency or a jurisdiction appended after a dash. `kit.lookup` recognises the
name without it and returns the entry **as the list holds it**, qualifier
included. Keep what it returns; do not trim it back to what the narrative
said, because that qualifier is how later stages tell two sleeves of the same
company apart.

## The project code

The project word is in the narrative, usually straight after a keyword
announcing it. Take the single token after that keyword. Unlike a party name,
a project code has no spaces, so bound it at the first whitespace; that is why
this step has always resolved far better than the counterparty one, and it is
worth not breaking.

If the narrative names no project, that is CANNOT_VERIFY — many rows have none.
Resolve the word with `kit.lookup(word, [('project_codes', 'Project Code'),
('project_codes', 'New Project Code')])`, and pass no suffix markers: legal-form
tokens are for party names and would cut a project code in half.

Do not let a party name leak into the project lookup, or a project code into
the counterparty lookup. Blank out the counterparty span before searching for
the project word if that is easier.

## Classification

`classification` must be exactly one of these eight strings, copied verbatim.
Nothing else is accepted, and a label of your own invention fails the run:

    Investment            buying or selling a position, or funding one directly
    Investment Transfer   money moved between two of the platform's own entities
                          in order to fund or settle an investment, rather than
                          out to a third party
    Vendor                paying a supplier
    Related Party         a movement with a related party that is not funding
                          an investment — a fee, a rebate, a settling of
                          balances. Being on the related party list does not by
                          itself make a row this
    Investor              a capital call or distribution
    Internal              a transfer between the platform's own accounts
    Other                 bank charges, interest, and anything routine
    Review                none of the above

Whether an investment row is equity or a loan is carried by the narrative —
shares and equity on one side, loan principal and accrued interest on the
other — but that distinction belongs in the position, not in this label.

Two signals decide this and you have both: **which list the counterparty was
found on**, and **what the narrative says the movement was for**. A party
found on the vendor list being paid is a different label from the same party
funding a position, so neither signal decides alone.

**Classification comes from the evidence, not from whether a lookup
succeeded.** A row whose counterparty is UNRESOLVED is still classifiable: the
narrative says what kind of movement it is regardless of whether the name is on
a list. `Review` means you genuinely cannot place the row, and it should be
rare — reaching for it because the counterparty did not resolve is the mistake
to avoid; a made-up label is the other one.

## The reference data, and what each part is for

Anything else this run mounts is for context. Resolving against a table not
listed here fails, however real the value you find in it looks.

- **counterparty_match** may only resolve against, in an order you decide:
      legal_entities:Legal Entity
      related_parties:Related Party
      vendors:Vendor
      investors:Investor
      deals_positions:Deal Name
      deals_positions:Position
- **project_code_match** may only resolve against, in an order you decide:
      project_codes:Project Code
      project_codes:New Project Code

## What the verifier checks

- counterparty_raw_provenance         a counterparty you claim to have pulled out must appear in that row's narrative
- project_code_raw_provenance         so must a project word
- counterparty_match_membership       a MATCH must name a list and a value that is really in it
- project_code_match_membership       the same for project codes
- resolution_completeness             every row carries a status for both — an omitted resolution is unexamined, not unresolved
- classification_vocabulary           the classification must be one of the declared labels
- counterparty_match_proposals        a PROBABLE must carry a reason and a confidence between 0 and 1
- classification_review_rate          Review is the label of last resort; it should be rare
- counterparty_match_resolution_rate  of the names actually read out of the document, most should resolve
- counterparty_match_pairing          a status must agree with whether a value was actually read: nothing read means CANNOT_VERIFY, something read means it was looked up

## Notes for this run

- Caution belongs in the **matching**, not in the reading. Two different jobs:

  - `counterparty_raw` and `project_code_raw` are *transcription*. If the
    narrative names a party or a project, copy it out — always, whether or not
    any list contains it. Leaving it null claims the narrative named nobody,
    which is a different and usually wrong statement, and it robs the reviewer
    of the one thing they need to decide the row.
  - The `_match` status is *judgement*, and there you are strict. Forcing an
    unmatched name to the nearest list entry is the single worst thing you can
    do here: an UNRESOLVED row goes to a person, a wrong match goes into the
    accounts. Never use `candidates` to pick a match.

  So a narrative naming a party the narrative names that is in no list gives
  `counterparty_raw` set and status UNRESOLVED. Only a narrative that names no
  party at all — a bank charge, an interest posting — gives null and
  CANNOT_VERIFY.

There are 16 rows to resolve.

You do not have to write the final file yet. First, work on it.

Write a script that does part of the job and **checks itself out loud**. Run the
logic you are considering over the real data, count what it caught and what it
missed, print the cases it got wrong, and print enough of them to see the
pattern. Its stdout comes back to you, and then you can write another one.

This is a working loop, not a survey. Use it the way anyone writes code against
an unfamiliar document:

    try something on real rows  ->  print what it produced  ->  see where it is
    wrong  ->  change it  ->  try again

**Write your own checks and print their results.** You know what "right" looks
like for this task better than any fixed rule does — how many rows should have
found something, whether a value you extracted is really in the source, whether
two things that should agree do. Assert those, print the failures with the row
they came from, and keep going until your own checks stop finding problems.
Adapt the checks too: one that never fires is telling you nothing.

Do not reason about what the data probably looks like. Look at it. Every run
that wrote its parser blind made the same class of mistake — a pattern that
silently never fired, a span that swallowed a whole clause — and printing five
real values would have shown it immediately.

Reply with the script in a single ```python code block.

What you have seen so far:

--- you ran explore-1.py and it printed ---
=== TABLES ===
Table: account_map, columns: ['Account Number', 'Bank Account']
Table: deals_positions, columns: ['Deal Name', 'Position']
Table: investors, columns: ['Investor']
Table: legal_entities, columns: ['Legal Entity']
Table: project_codes, columns: ['Project Code', 'New Project Code']
Table: related_parties, columns: ['Related Party']
Table: vendors, columns: ['Vendor']

=== ROWS ===
Total rows: 16

--- Row 0 ---
  bank_reference: NONREF NONREF
  trn_type: 31 Mar
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 17:46
  narrative: CHARGES FOR 2, OUTWARD SEPA PAYMENT
  credit: None
  debit: -0.44
  balance: 13217773.59
  account_number: 240-524291-030
  currency: EUR
  page: 1

--- Row 1 ---
  bank_reference: 10716RS62GWQ CEPHALUS
  trn_type: 31 Mar
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 11:01
  narrative: NORDVIK I.A.B. FUND I, TFR+ PMT FRM NI ABF II SCSP TO NI ABF I, SCSP FOR PURCHASE 100PER OF ACC INT, IN CEPHALUS BIOGAS 001 LTD PREMIUM, ACCRUED INTEREST PROJECT CEPHALUS
  credit: 301908.70
  debit: None
  balance: 13217774.03
  account_number: 240-524291-030
  currency: EUR
  page: 1

--- Row 2 ---
  bank_reference: 85720JS23WNK CEPHALUS
  trn_type: 31 Mar
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 11:01
  narrative: NORDVIK I.A.B. FUND I, TFR+ PMT FRM NI ABF II SCSP TO NI ABF I, SCSP FOR ACQ 100PER OF SHARES IN, CEPHALUS BIOGAS 001 LTD REL TOTAL, PREMIUM (EQUITY) PROJECT CEPHALUS)
  credit: 2013809.89
  debit: None
  balance: 12915865.33
  account_number: 240-524291-030
  currency: EUR
  page: 1

--- Row 3 ---
  bank_reference: 24381JR11YY3 CEPHALUS
  trn_type: 31 Mar
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 11:01
  narrative: NORDVIK I.A.B. FUND I, TFR+ PMT FRM NI ABF II SCSP TO NI ABF I, SCSP FOR PURCHAS 100PER OF LOAN, PRINCIP IN CEPHALUS BIOGAS 001 LTD, TOTAL COST LOAN PROJECT CEPHALUS
  credit: 4232000.00
  debit: None
  balance: 10902055.44
  account_number: 240-524291-030
  currency: EUR
  page: 1

--- Row 4 ---
  bank_reference: ST65724109296034 52322485521381-4000
  trn_type: 31 Mar
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 10:08
  narrative: 52322485521381-7786132265, TRENTBECK AUDIT
  credit: None
  debit: -19931.11
  balance: 6670055.44
  account_number: 240-524291-030
  currency: EUR
  page: 1

--- Row 5 ---
  bank_reference: QN29131563952037 22254822
  trn_type: 31 Mar
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 10:08
  narrative: 22254822 92504555 46212525, NIP PLATFORM SOLUTIONS APS
  credit: None
  debit: -509.80
  balance: 6689986.55
  account_number: 240-524291-030
  currency: EUR
  page: 1

--- Row 6 ---
  bank_reference: QUR35762JQ16VCY5 NONREF
  trn_type: 31 Mar
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 05:12
  narrative: 1/NI ABF I DEVCO APS, TFR+ Loan dist. - NI ABF I DevCo ApS to, NI ABF II SCSp related to contri. 5, ,6+ 7 in + dist. 1 in NI ABF I DevCo ApS. Repay of loan principal. CHARGE WAIVED
  credit: 3597561.92
  debit: None
  balance: 6690496.35
  account_number: 240-524291-030
  currency: EUR
  page: 1

--- Row 7 ---
  bank_reference: 55051QC31ZHZ CEPHALUS
  trn_type: 31 Mar
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 23:04
  narrative: NORDVIK I.A.B. FUND I, TFR+ OBO PMT FRM NI ABF II SCSP ON, BEHALF OF NI ABF II CO-INVEST SCSP, TO NI ABF I SCSP FOR ACQ OF 1 SHARE, IN CEPHALUS BIOGAS 001 LTD (EQUITY
  credit: 1.62
  debit: None
  balance: 3092934.43
  account_number: 240-524291-030
  currency: EUR
  page: 2

--- Row 8 ---
  bank_reference: 85202DA174BN CEPHALUS
  trn_type: 31 Mar
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 23:04
  narrative: NORDVIK I.A.B. FUND I, TFR+ OBO PMT FRM NI ABF II SCSP ON, BEHALF OF NI ABF II QFPF BLOC. SCSP, TO NI ABF I SCSP FOR ACQ OF 1 SHARE, IN CEPHALUS BIOGAS 001 LTD (EQUITY
  credit: 1.62
  debit: None
  balance: 3092932.81
  account_number: 240-524291-030
  currency: EUR
  page: 2

--- Row 9 ---
  bank_reference: TT NQK807SFXYKMA INTERNAL
  trn_type: 31 Mar
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 23:04
  narrative: COMMISSION EUR 6,00, 47223IZ05W0Z
  credit: None
  debit: -6.00
  balance: 3092931.19
  account_number: 240-524291-030
  currency: EUR
  page: 2

--- Row 10 ---
  bank_reference: TT NQK807SFXYKMA INTERNAL
  trn_type: 31 Mar
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 23:04
  narrative: NI ABF I SCSP, 47223IZ05W0Z, /DK6757710886323208 INTERNAL TRANSFER
  credit: None
  debit: -180000.00
  balance: 3092937.19
  account_number: 240-524291-030
  currency: EUR
  page: 2

--- Row 11 ---
  bank_reference: 36128KB34UJM SHORTTERM
  trn_type: 31 Mar
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 23:04
  narrative: NI ABF I FEEDER SCSP, STL COVER INVOICES
  credit: None
  debit: -20000.00
  balance: 3272937.19
  account_number: 240-524291-030
  currency: EUR
  page: 2

--- Row 12 ---
  bank_reference: 26623WD49U68 CEPHALUS
  trn_type: 31 Mar
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 23:04
  narrative: NORDVIK I.A.B. FUND I, TFR+ PMT FRM NI ABF II SCSP TO NI ABF I, SCSP FOR ACQ 100PER OF SHARE IN, CEPHALUS BIOGAS 001 LTD REL COST (EQUITY) (PROJECT CEPHALUS)
  credit: 46272.93
  debit: None
  balance: 3292937.19
  account_number: 240-524291-030
  currency: EUR
  page: 2

--- Row 13 ---
  bank_reference: HVJ01535FI1XKDJS NONREF
  trn_type: 27 Mar
  value_date: 27 Mar 2026
  post_date: 27 Mar 2026
  time: 12:07
  narrative: 1/COVBURY ENERGI A/S FENNSTEAD 41, TFR+ SARDONYX CLOSING, FX GBP 556598,00 AT 1,0389605 681960417, CHARGE WAIVED
  credit: 632911.04
  debit: None
  balance: 3246664.26
  account_number: 240-524291-030
  currency: EUR
  page: 2

--- Row 14 ---
  bank_reference: NONREF NONREF
  trn_type: 24 Mar
  value_date: 24 Mar 2026
  post_date: 24 Mar 2026
  time: 07:05
  narrative: CREDIT INTEREST
  credit: 1423.44
  debit: None
  balance: 2613753.22
  account_number: 240-524291-030
  currency: EUR
  pa
--- you ran explore-2.py and it printed ---
=== ACCOUNT MAP ===
240-149813-030 -> {'Account Number': '240-149813-030', 'Bank Account': 'NI ABF II - Calder - EUR - 8102'}
240-149813-131 -> {'Account Number': '240-149813-131', 'Bank Account': 'NI ABF II - Calder - DKK - 4319'}
240-222731-030 -> {'Account Number': '240-222731-030', 'Bank Account': 'NIP V - Calder - EUR - 030041'}
240-222731-132 -> {'Account Number': '240-222731-132', 'Bank Account': 'NIP V - Calder - GBP - 3252'}
240-222731-135 -> {'Account Number': '240-222731-135', 'Bank Account': 'NIP V - Calder - DKK - 0541'}
240-524291-030 -> {'Account Number': '240-524291-030', 'Bank Account': 'Calder 0894 EUR'}
240-644826-130 -> {'Account Number': '240-644826-130', 'Bank Account': 'NI GMF II - Calder - USD - 4373'}

=== REFERENCE TABLES ===

--- legal_entities ---
  Legal Entity (97 items): ['AGP NI Co-Invest I SCSp', 'Alcor NI Co-Invest SCSp', 'Alnair NI Co-invest LP', 'Avior NI Co-Invest SCSp', 'DK NI Co-Invest K/S', 'DKP NI Co-Invest K/S', 'Delling NI Co-Invest SCSp', 'FS NI Co-Invest SCSp', 'Freyr NI Co-invest LP', 'IP NI Co-invest K/S']
    ... ['Kommanditselskabet af 20 juni 2023', 'Magni NI Co-Invest SCSp', 'NI GCF I Direct Lending Non-US SCSp', 'NI GCF I Direct Lending Non-US SCSp - Eliminations', 'NI GCF I Direct Lending US SCSp', 'NI GCF I Velaris SCSp', 'NI GCF II EUR HedgeCo SCSp', 'NI GCF II Non-US Aggregator SCSp', 'NI GCF II US Aggregator SCSp', 'NI GCF II US Aggregator SCSp - Elimination', 'NI GCF II USD HedgeCo SCSp', 'NI NKP Co-Invest I SCSp', 'NI Regulated Energy Grids SCA SICAV-RAIF – Compartment A', 'NI V Co-Invest Vehicle A SCSp', 'NI V GP I SCSp']

--- related_parties ---
  Related Party (296 items): ['ADVOKATFIRMAET LAURITZEN AS', 'AGP NI CO-Invest I SCSP', 'ANTARES Ottesen', 'ASHGROVE Qtd Holdco Pty Ltd.', 'Agatestone Grove 2 Holdco LLC', 'Agatestone Grove 2 LLC', 'Agatestone Grove DevCo LLC', 'Agatestone Grove II HoldCo LLC', 'Agatestone Grove Wind LLC', 'Alcor NI Co-Invest SCSp']
    ... ['Alnair NI Co-Invest SCSp', 'Ampelos HoldCo LLC', 'Anpartsselskabet af 20. Juni 2023', 'Austerwind Alpheratz S.r.l.', 'Avior NI Co-Invest SCSp', 'Avocet Offshore Windfarm Limited', 'Bexmoor Platform C.V.', 'CIV III 2017 K/S', 'California North Floating LLC', 'California Offshore Holding LLC', 'Castalia Platform CV', 'Cephalus Biogas 001 Limited', 'Diphda Solar DevCo II LLC', 'Director - Ida Palsgaard', 'Director - Rikke Fenger']

--- vendors ---
  Vendor (245 items): ['ACD', 'AL-Draywick & Associates - Non-LU', 'Admini. de l Enregistrement - LU', 'Administration des Contributions Directes - LU', 'Administration des contributions directes', 'Aldervale Aps - Non-LU', 'Alma J. Thulstrup (UK) Limited - Non-LU', 'Ashgarth Advisory Pty Ltd - Non-LU', 'Authorite des Marchers Financiers - Non - LU', 'Autorité des marchés financiers - Non LU']
    ... ['BAC A/S - Non-Lu', 'BLACKTHORN - VAT', 'BRACKEN Advisory', 'BRACKFORD LOSWOLD CJSC - Non-LU', 'BRACKMERE, REDDALE & CALDWICK S.E.N.C.R.L./S.R.L. - Non - LU', 'Boardwell - Non-LU', 'Bodil Norlund', 'Brackvale Group SA - LU', 'Bramworth', 'Bramworth & Caldmere SA', 'Bramworth & Caldmere SA - LU', 'Bregnholm', 'Brenneke, Hanne and Partner mbB - Non - LU', 'CE - Nordvik Economics - Non-LU', 'CECILIE TAZ - Non - LU']

--- investors ---
  Investor (277 items): ['Aeroven Wind Systems A/S', 'ApS Glanworth', 'ApS HET', 'ApS ZOF', 'Ashdale Linddale- hollmont Wrenshaw', 'Ashwold International S.A. acting on behalf of Ashwold Infrastruktur Tarnmere FCP-FIS - Teilfonds 1', 'BAQ Private Markets GmbH', 'BEV Private Capital Haslstead GmbH', 'Brackhurst Investment Pte. Ltd.', 'Bramstead Investment Pte. Ltd']
    ... ['Bramwick Climate Capital II, LLC', 'Brinberg LLC', 'Brinbury Lindford GmbH', 'Brinshaw. Haldcombe Harrdale Davhurst', 'Brinwick Pension Forsikringsaktieselskab', 'Bundespensionskasse BRACKEN - QOF 11', 'CER-Ardvik 95', 'CIS-Ardvik 63 Vermögensverwaltungsgesellschaft mbH', 'CIS-Ardvik 83', 'COMPTROLLER OF THE STATE OF CLANHOLM DEZ, AS TRUSTEE OF THE COMMON RETIREMENT FUND', 'Calder Investment Bank Holdings Limited', 'Cantbury Pension – pensionskassen for innstead', 'Carrbeck Invest ApS', 'Chalthorpe Wickley Larchdale', 'Clanwick Private Equity ApS']

--- deals_positions ---
  Deal Name (287 items): ['ADVOKATFIRMAET LAURITZEN AS - NOK', 'ADVOKATFIRMAET LAURITZEN AS - NOK (Do not use!!!)', 'Agatestone Chione I', 'Agatestone Grove 2 HoldCo LLC', 'Agatestone Grove DevCo LLC - USD', 'Agatestone Grove I - Nordvik Infrastructure V US C LP', 'Agatestone Grove I - Nordvik Infrastructure V US D LP', 'Agatestone Grove Wind LLC - EUR', 'Agatestone Grove Wind LLC - USD', 'Alfhild Green Limited']
    ... ['Ampelos HoldCo LLC', 'Amphion Energy OY', 'Bexmoor Platform C.V. - AUD', 'Bexmoor Platform C.V. - EUR', 'CE Green I Sarl', 'California Offshore Holding LLC', 'Castalia Energy Storage Pty Limited', 'Castalia Platform CV - AUD', 'Castalia Platform CV - EUR', 'Cephalus Biogas 001 Limited - EUR', 'Crédit Verrance CIB', 'DBC Invest A/S', 'Denholm Capital Partners LLC', 'Denholm Capital Partners LLC - EUR', 'Diphda Solar DevCo II LLC - USD']
  Position (1524 items): ['ADVOKATFIRMAET LAURITZEN AS - NOK (ADVOKATFIRMAET LAURITZEN AS (Snotra) (Equity))', 'ADVOKATFIRMAET LAURITZEN AS - NOK (Snotra (Equity))', 'Agatestone Chione I (Equity)', 'Agatestone Grove 2 HoldCo LLC (Agatestone Grove 2 LLC (Agatestone Grove II) (Equity))', 'Agatestone Grove 2 HoldCo LLC (Agatestone Grove 2 LLC (Agatestone Grove II) (Funding Loan))', 'Agatestone Grove DevCo LLC - USD (Agatestone Grove DevCo LLC (Agatestone Grove (Funding Loan)))', 'Agatestone Grove DevCo LLC - USD (Agatestone Grove DevCo LLC (Agatestone Grove II (Funding Loan)))', 'Agatestone Grove I - Nordvik Infrastructure V US C LP (Equity)', 'Agatestone Grove Wind LLC - EUR (Agatestone Grove Wind LLC (Agatestone Grove (Equity)))', 'Agatestone Grove Wind LLC - USD (Agatestone Grove Wind LLC (Agatestone Grove (Equity)))']
    ... ['Agatestone Grove Wind LLC - USD (Agatestone Grove Wind LLC (Agatestone Grove (Fund

# reply

```python
import kit

print("=== EXPLORATION 3 ===")

# Check questions
print("Questions:", kit.questions())

# Check all 16 rows
rows = kit.rows()
print(f"Total rows: {len(rows)}")

account_map = kit.table("account_map")
for r in account_map.values("Account Number"):
    print("Account map entry:", account_map.find("Account Number", r))

# Inspect legal entities, related parties matching "NI ABF" or "Nordvik"
for tbl_name, col_name in [
    ("legal_entities", "Legal Entity"),
    ("related_parties", "Related Party"),
    ("vendors", "Vendor"),
    ("investors", "Investor"),
    ("deals_positions", "Deal Name"),
    ("deals_positions", "Position"),
    ("project_codes", "Project Code"),
    ("project_codes", "New Project Code"),
]:
    t = kit.table(tbl_name)
    vals = t.values(col_name)
    abf = [v for v in vals if "ABF" in str(v) or "Cephalus" in str(v).capitalize() or "Trentbeck" in str(v).capitalize() or "NIP" in str(v) or "Covbury" in str(v).capitalize()]
    print(f"\n{tbl_name}:{col_name} matching ABF/Cephalus/Trentbeck/NIP/Covbury ({len(abf)}):")
    for v in abf[:20]:
        print("  ", v)

print("\n=== ALL ROWS DETAIL ===")
pools = [
    ("legal_entities", "Legal Entity"),
    ("related_parties", "Related Party"),
    ("vendors", "Vendor"),
    ("investors", "Investor"),
    ("deals_positions", "Deal Name"),
    ("deals_positions", "Position"),
]

proj_pools = [
    ("project_codes", "Project Code"),
    ("project_codes", "New Project Code"),
]

for i, row in enumerate(rows):
    print(f"\n--- Row {i} ---")
    print(f"  trn_type: {row.get('trn_type')}, val_date: {row.get('value_date')}")
    print(f"  amount: debit={row.get('debit')} credit={row.get('credit')}")
    print(f"  narrative: {repr(row.get('narrative'))}")
    print(f"  bank_ref: {repr(row.get('bank_reference'))}")

    # Let's test spans and lookups in the narrative
    # Try finding any substring of narrative in pools
    narr = row.get("narrative", "")
    words = narr.replace(",", " ").replace("/", " ").replace("-", " ").split()
    print("  Potential project codes:")
    for w in words:
        res = kit.lookup(w, proj_pools)
        if res:
            print(f"    found proj: {w} -> {res}")
    # Also check bank_reference for project codes
    b_words = (row.get("bank_reference") or "").replace(",", " ").split()
    for w in b_words:
        res = kit.lookup(w, proj_pools)
        if res:
            print(f"    found proj in bank_ref: {w} -> {res}")

    # Check candidates for counterparty
    print("  Candidates/lookups in narrative:")
    # generate sub-phrases of length 1 to 6
    tokens = narr.split()
    found_matches = []
    for l in range(len(tokens)):
        for r_len in range(1, 7):
            if l + r_len <= len(tokens):
                phrase = " ".join(tokens[l:l+r_len]).strip(",.- /")
                if len(phrase) >= 3:
                    m = kit.lookup(phrase, pools)
                    if m and m not in found_matches:
                        found_matches.append((phrase, m))
    for phrase, m in found_matches:
        print(f"    MATCH: phrase={repr(phrase)} -> {m}")
```
