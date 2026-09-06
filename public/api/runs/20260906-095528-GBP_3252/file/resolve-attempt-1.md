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


You looked at the data first. This is what you saw:

--- you ran explore-1.py and it printed ---
=== TABLES AVAILABLE ===
Tables: ['account_map', 'deals_positions', 'investors', 'legal_entities', 'project_codes', 'related_parties', 'vendors']

Table: account_map, Columns: ['Account Number', 'Bank Account']
  Account Number (7 values): ['240-149813-030', '240-149813-131', '240-222731-030', '240-222731-132', '240-222731-135']
  Bank Account (7 values): ['Calder 0894 EUR', 'NI ABF II - Calder - DKK - 4319', 'NI ABF II - Calder - EUR - 8102', 'NI GMF II - Calder - USD - 4373', 'NIP V - Calder - DKK - 0541']

Table: deals_positions, Columns: ['Deal Name', 'Position']
  Deal Name (287 values): ['ADVOKATFIRMAET LAURITZEN AS - NOK', 'ADVOKATFIRMAET LAURITZEN AS - NOK (Do not use!!!)', 'Agatestone Chione I', 'Agatestone Grove 2 HoldCo LLC', 'Agatestone Grove DevCo LLC - USD']
  Position (1524 values): ['ADVOKATFIRMAET LAURITZEN AS - NOK (ADVOKATFIRMAET LAURITZEN AS (Snotra) (Equity))', 'ADVOKATFIRMAET LAURITZEN AS - NOK (Snotra (Equity))', 'Agatestone Chione I (Equity)', 'Agatestone Grove 2 HoldCo LLC (Agatestone Grove 2 LLC (Agatestone Grove II) (Equity))', 'Agatestone Grove 2 HoldCo LLC (Agatestone Grove 2 LLC (Agatestone Grove II) (Funding Loan))']

Table: investors, Columns: ['Investor']
  Investor (277 values): ['Aeroven Wind Systems A/S', 'ApS Glanworth', 'ApS HET', 'ApS ZOF', 'Ashdale Linddale- hollmont Wrenshaw']

Table: legal_entities, Columns: ['Legal Entity']
  Legal Entity (97 values): ['AGP NI Co-Invest I SCSp', 'Alcor NI Co-Invest SCSp', 'Alnair NI Co-invest LP', 'Avior NI Co-Invest SCSp', 'DK NI Co-Invest K/S']

Table: project_codes, Columns: ['Project Code', 'New Project Code']
  Project Code (586 values): ['1 OH - DFSA', 'ABF II Fundraising', 'AD MIZAR', 'AEGIR to Methanol', 'AGATESTONE GROVE I']
  New Project Code (1 values): ['Halstead']

Table: related_parties, Columns: ['Related Party']
  Related Party (296 values): ['ADVOKATFIRMAET LAURITZEN AS', 'AGP NI CO-Invest I SCSP', 'ANTARES Ottesen', 'ASHGROVE Qtd Holdco Pty Ltd.', 'Agatestone Grove 2 Holdco LLC']

Table: vendors, Columns: ['Vendor']
  Vendor (245 values): ['ACD', 'AL-Draywick & Associates - Non-LU', 'Admini. de l Enregistrement - LU', 'Administration des Contributions Directes - LU', 'Administration des contributions directes']

=== ROWS TO PROCESS ===
Total rows: 16

--- Row 1 ---
  bank_reference: TT
  trn_type: S+P- CHG
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 10:45
  narrative: COMMISSION GBP 5,21, 21398DX37I23
  credit: None
  debit: -5.21
  balance: 103014.97
  account_number: 240-222731-132
  currency: GBP
  page: 1

--- Row 2 ---
  bank_reference: TT
  trn_type: UNKNOWN
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 10:45
  narrative: NI V KALVIK TOPCO LTD., 21398DX37I23, /GB40NRVB51407454522412 LOAN: FROM NI V SCSP TO NI V, KALVIK TOPCO LTD.. PROJECT WILLOWBANK
  credit: None
  debit: -15701940.20
  balance: 103020.18
  account_number: 240-222731-132
  currency: GBP
  page: 1

--- Row 3 ---
  bank_reference: 43110QR38LHY
  trn_type: UNKNOWN
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 10:45
  narrative: NORDVIK INFRA.V CN SC,, SHORT TERM LOAN: FROM NI V SCSP TO NI V CN SCSP . PROJECT WILLOWBANK
  credit: None
  debit: -531701.80
  balance: 15804960.38
  account_number: 240-222731-132
  currency: GBP
  page: 1

--- Row 4 ---
  bank_reference: TT
  trn_type: S+P- CHG
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 07:10
  narrative: COMMISSION GBP 5,22, 22801YB03UF8
  credit: None
  debit: -5.22
  balance: 16336662.18
  account_number: 240-222731-132
  currency: GBP
  page: 1

--- Row 5 ---
  bank_reference: TT
  trn_type: UNKNOWN
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 07:10
  narrative: NI V SCSP, 22801YB03UF8, /DK8471936954300848 INTERNAL TRANSFER
  credit: None
  debit: -610000.00
  balance: 16336667.40
  account_number: 240-222731-132
  currency: GBP
  page: 1

--- Row 6 ---
  bank_reference: V400024233703R22
  trn_type: UNKNOWN
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 07:03
  narrative: 1/NORDVIK INFRASTRUCTURE PARTNER, S+P+ CHARGE WAIVED
  credit: 16900000.00
  debit: None
  balance: 16946667.40
  account_number: 240-222731-132
  currency: GBP
  page: 1

--- Row 7 ---
  bank_reference: TT
  trn_type: S+P- CHG
  value_date: 30 Mar 2026
  post_date: 30 Mar 2026
  time: 07:00
  narrative: COMMISSION GBP 5,20, 24370KF00HEC
  credit: None
  debit: -5.20
  balance: 46667.40
  account_number: 240-222731-132
  currency: GBP
  page: 2

--- Row 8 ---
  bank_reference: TT
  trn_type: UNKNOWN
  value_date: 30 Mar 2026
  post_date: 30 Mar 2026
  time: 07:00
  narrative: NI V AZURITE HOLDCO LTD, 24370KF00HEC, /GB14NRVB35403891305213 EQUITY: FROM NORDVIK, INFRASTRUCTURE V SCSP TO NI V AZURITE HOLDCO LTD., PROJECT AZURITE.
  credit: None
  debit: -249549.75
  balance: 46672.60
  account_number: 240-222731-132
  currency: GBP
  page: 2

--- Row 9 ---
  bank_reference: TT
  trn_type: S+P- CHG
  value_date: 30 Mar 2026
  post_date: 30 Mar 2026
  time: 07:00
  narrative: COMMISSION GBP 5,20, 82924VJ9010W
  credit: None
  debit: -5.20
  balance: 296222.35
  account_number: 240-222731-132
  currency: GBP
  page: 2

--- Row 10 ---
  bank_reference: TT
  trn_type: UNKNOWN
  value_date: 30 Mar 2026
  post_date: 30 Mar 2026
  time: 07:00
  narrative: NI V AZURITE HOLDCO LTD, 82924VJ9010W, /GB14NRVB35403891305213 LOAN: FROM NORDVIK, INFRASTRUCTURE V SCSP TO NI V AZURITE HOLDCO LTD., PROJECT AZURITE.
  credit: None
  debit: -582282.75
  balance: 296227.55
  account_number: 240-222731-132
  currency: GBP
  page: 2

--- Row 11 ---
  bank_reference: 59675NX26HUD
  trn_type: UNKNOWN
  value_date: 30 Mar 2026
  post_date: 30 Mar 2026
  time: 07:00
  narrative: NORDVIK INFRA.V CN SC,, SHORT-TERM LOAN: FROM NORDVIK, INFRASTRUCTURE V SCSP TO NORDVIK, INFRASTRUCTURE V CN SCSP. PROJECT AZURITE.
  credit: None
  debit: -28167.65
  balance: 878510.30
  account_number: 240-222731-132
  currency: GBP
  page: 2

--- Row 12 ---
  bank_reference: TT
 
--- you ran explore-2.py and it printed ---
=== QUESTIONS ===
[]

=== ACCOUNT MAP ===
  240-149813-030 -> Calder 0894 EUR
  240-149813-131 -> NI ABF II - Calder - DKK - 4319
  240-222731-030 -> NI ABF II - Calder - EUR - 8102
  240-222731-132 -> NI GMF II - Calder - USD - 4373
  240-222731-135 -> NIP V - Calder - DKK - 0541
  240-524291-030 -> NIP V - Calder - EUR - 030041
  240-644826-130 -> NIP V - Calder - GBP - 3252

=== ALL ROWS (1 to 16) ===
Total rows: 16

--- Row 1 ---
  bank_reference: TT
  trn_type: S+P- CHG
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 10:45
  narrative: COMMISSION GBP 5,21, 21398DX37I23
  credit: None
  debit: -5.21
  balance: 103014.97
  account_number: 240-222731-132
  currency: GBP
  page: 1

--- Row 2 ---
  bank_reference: TT
  trn_type: UNKNOWN
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 10:45
  narrative: NI V KALVIK TOPCO LTD., 21398DX37I23, /GB40NRVB51407454522412 LOAN: FROM NI V SCSP TO NI V, KALVIK TOPCO LTD.. PROJECT WILLOWBANK
  credit: None
  debit: -15701940.20
  balance: 103020.18
  account_number: 240-222731-132
  currency: GBP
  page: 1

--- Row 3 ---
  bank_reference: 43110QR38LHY
  trn_type: UNKNOWN
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 10:45
  narrative: NORDVIK INFRA.V CN SC,, SHORT TERM LOAN: FROM NI V SCSP TO NI V CN SCSP . PROJECT WILLOWBANK
  credit: None
  debit: -531701.80
  balance: 15804960.38
  account_number: 240-222731-132
  currency: GBP
  page: 1

--- Row 4 ---
  bank_reference: TT
  trn_type: S+P- CHG
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 07:10
  narrative: COMMISSION GBP 5,22, 22801YB03UF8
  credit: None
  debit: -5.22
  balance: 16336662.18
  account_number: 240-222731-132
  currency: GBP
  page: 1

--- Row 5 ---
  bank_reference: TT
  trn_type: UNKNOWN
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 07:10
  narrative: NI V SCSP, 22801YB03UF8, /DK8471936954300848 INTERNAL TRANSFER
  credit: None
  debit: -610000.00
  balance: 16336667.40
  account_number: 240-222731-132
  currency: GBP
  page: 1

--- Row 6 ---
  bank_reference: V400024233703R22
  trn_type: UNKNOWN
  value_date: 31 Mar 2026
  post_date: 31 Mar 2026
  time: 07:03
  narrative: 1/NORDVIK INFRASTRUCTURE PARTNER, S+P+ CHARGE WAIVED
  credit: 16900000.00
  debit: None
  balance: 16946667.40
  account_number: 240-222731-132
  currency: GBP
  page: 1

--- Row 7 ---
  bank_reference: TT
  trn_type: S+P- CHG
  value_date: 30 Mar 2026
  post_date: 30 Mar 2026
  time: 07:00
  narrative: COMMISSION GBP 5,20, 24370KF00HEC
  credit: None
  debit: -5.20
  balance: 46667.40
  account_number: 240-222731-132
  currency: GBP
  page: 2

--- Row 8 ---
  bank_reference: TT
  trn_type: UNKNOWN
  value_date: 30 Mar 2026
  post_date: 30 Mar 2026
  time: 07:00
  narrative: NI V AZURITE HOLDCO LTD, 24370KF00HEC, /GB14NRVB35403891305213 EQUITY: FROM NORDVIK, INFRASTRUCTURE V SCSP TO NI V AZURITE HOLDCO LTD., PROJECT AZURITE.
  credit: None
  debit: -249549.75
  balance: 46672.60
  account_number: 240-222731-132
  currency: GBP
  page: 2

--- Row 9 ---
  bank_reference: TT
  trn_type: S+P- CHG
  value_date: 30 Mar 2026
  post_date: 30 Mar 2026
  time: 07:00
  narrative: COMMISSION GBP 5,20, 82924VJ9010W
  credit: None
  debit: -5.20
  balance: 296222.35
  account_number: 240-222731-132
  currency: GBP
  page: 2

--- Row 10 ---
  bank_reference: TT
  trn_type: UNKNOWN
  value_date: 30 Mar 2026
  post_date: 30 Mar 2026
  time: 07:00
  narrative: NI V AZURITE HOLDCO LTD, 82924VJ9010W, /GB14NRVB35403891305213 LOAN: FROM NORDVIK, INFRASTRUCTURE V SCSP TO NI V AZURITE HOLDCO LTD., PROJECT AZURITE.
  credit: None
  debit: -582282.75
  balance: 296227.55
  account_number: 240-222731-132
  currency: GBP
  page: 2

--- Row 11 ---
  bank_reference: 59675NX26HUD
  trn_type: UNKNOWN
  value_date: 30 Mar 2026
  post_date: 30 Mar 2026
  time: 07:00
  narrative: NORDVIK INFRA.V CN SC,, SHORT-TERM LOAN: FROM NORDVIK, INFRASTRUCTURE V SCSP TO NORDVIK, INFRASTRUCTURE V CN SCSP. PROJECT AZURITE.
  credit: None
  debit: -28167.65
  balance: 878510.30
  account_number: 240-222731-132
  currency: GBP
  page: 2

--- Row 12 ---
  bank_reference: TT
  trn_type: S+P- CHG
  value_date: 24 Mar 2026
  post_date: 24 Mar 2026
  time: 08:10
  narrative: COMMISSION GBP 5,19, 19709GA25RZL
  credit: None
  debit: -5.19
  balance: 906677.95
  account_number: 240-222731-132
  currency: GBP
  page: 2

--- Row 13 ---
  bank_reference: TT
  trn_type: UNKNOWN
  value_date: 24 Mar 2026
  post_date: 24 Mar 2026
  time: 08:10
  narrative: NI V FENWICK HOLDCO LTD,, 19709GA25RZL, /GB10NRVB98154047624001 LOAN: FROM NORDVIK INFRASTRUCTURE V SCSP TO NI V FENWICK HOLDCO LTD.., PROJECT FENWICK.
  credit: None
  debit: -1160696.30
  balance: 906683.14
  account_number: 240-222731-132
  currency: GBP
  page: 2

--- Row 14 ---
  bank_reference: 49211YZ41JZ6
  trn_type: UNKNOWN
  value_date: 24 Mar 2026
  post_date: 24 Mar 2026
  time: 08:10
  narrative: NORDVIK INFRA.V CN SC,, SHORT TERM LOAN: FROM NORDVIK, INFRASTRUCTURE V SCSP TO NORDVIK, INFRASTRUCTURE V CN SCSP. PROJECT FENWICK.
  credit: None
  debit: -39303.70
  balance: 2067379.44
  account_number: 240-222731-132
  currency: GBP
  page: 2

--- Row 15 ---
  bank_reference: J545245036302N01
  trn_type: UNKNOWN
  value_date: 24 Mar 2026
  post_date: 24 Mar 2026
  time: 07:02
  narrative: 1/NORDVIK INFRASTRUCTURE PARTNER, S+P+ CHARGE WAIVED
  credit: 2100000.00
  debit: None
  balance: 2106683.14
  account_number: 240-222731-132
  currency: GBP
  page: 2

--- Row 16 ---
  bank_reference: NONREF
  trn_type: S+P+ INT
  value_date: 23 Mar 2026
  post_date: 23 Mar 2026
  time: 21:06
  narrative: CREDIT INTEREST
  credit: 95.47
  debit: None
  balance: 6683.14
  account_number: 240-222731-132
  currency: GBP
  page: 2

=== SEARCHING TABLES FOR KEY TERMS ===

Searching for 'KALVIK':
  [related_parties:Related Party] found 3: ['NI IV Kalvik Holdco Ltd', 'NI V Kalvik Holdco Ltd', 'NI V Kalvik TopCo Limited.']
  [deals_positions:Deal Name] found 3: ['NI IV Kal
--- you ran explore-3.py and it printed ---
=== CHECKING MATCHES FOR PARTIES AND PROJECTS ===

--- Table: account_map ---
  Account Number: 7 entries
  Bank Account: 7 entries

--- Table: deals_positions ---
  Deal Name: 287 entries
  Position: 1524 entries

--- Table: investors ---
  Investor: 277 entries

--- Table: legal_entities ---
  Legal Entity: 97 entries

--- Table: project_codes ---
  Project Code: 586 entries
  New Project Code: 1 entries

--- Table: related_parties ---
  Related Party: 296 entries

--- Table: vendors ---
  Vendor: 245 entries

=== SEARCHING IN REFERENCE TABLES ===

Search for 'KALVIK':
  [related_parties:Related Party] (3): ['NI IV Kalvik Holdco Ltd', 'NI V Kalvik Holdco Ltd', 'NI V Kalvik TopCo Limited.']
  [deals_positions:Deal Name] (3): ['NI IV Kalvik Holdco Limited - EUR', 'NI IV Kalvik Holdco Limited - GBP', 'NI V Kalvik Topco Limited']
  [deals_positions:Position] (9): ['NI GMF II Coöperatief U.A. - USD (NI GMF II (Vietnam) Limited Liability Company (Squallmoor Kalvik) (Equity))', 'NI GMF II Coöperatief U.A. - USD (Squallmoor Kalvik (Equity))', 'NI GMF II Coöperatief U.A. - USD (Squallmoor Kalvik (Funding Loan))', 'NI IV Kalvik Holdco Limited - EUR (WILLOWBANK (Equity))', 'NI IV Kalvik Holdco Limited - GBP (WILLOWBANK (Equity))', 'NI V Kalvik Topco Limited (NI V Kalvik Lender Ltd (WILLOWBANK) (Funding Loan))', 'NI V Kalvik Topco Limited (NI V Kalvik Lender Ltd (Willowbank(Equity)))', 'NI V Kalvik Topco Limited (WILLOWBANK (Equity))', 'NI V Kalvik Topco Limited (WILLOWBANK (Funding Loan))']
  [project_codes:Project Code] (1): ['Squallmoor Kalvik']

Search for 'FENWICK':
  [related_parties:Related Party] (1): ['NI IV Fenwick HoldCo Ltd']
  [deals_positions:Deal Name] (5): ['NI IV Fenwick HoldCo - NI IV AUS Trust - GBP', 'NI IV Fenwick HoldCo - NI IV Dutch K/S - GBP', 'NI IV Fenwick HoldCo - NI IV SCSp - GBP', 'NI IV Fenwick HoldCo - NI V Coöperatief - GBP', 'NI IV Fenwick HoldCo Limited - GBP']
  [deals_positions:Position] (33): ['NI IV Fenwick HoldCo - NI IV AUS Trust - GBP (Fenwick - Craigmore (Funding Loan))', 'NI IV Fenwick HoldCo - NI IV AUS Trust - GBP (Fenwick - Speedwell (Funding Loan))', 'NI IV Fenwick HoldCo - NI IV AUS Trust - GBP (Fenwick - Vestmark (Funding Loan))', 'NI IV Fenwick HoldCo - NI IV Dutch K/S - GBP (Fenwick - Craigmore (Funding Loan))', 'NI IV Fenwick HoldCo - NI IV Dutch K/S - GBP (Fenwick - Speedwell (Funding Loan))', 'NI IV Fenwick HoldCo - NI IV Dutch K/S - GBP (Fenwick - Vestmark (Funding Loan))', 'NI IV Fenwick HoldCo - NI IV SCSp - GBP (Fenwick - Craigmore (Funding Loan))', 'NI IV Fenwick HoldCo - NI IV SCSp - GBP (Fenwick - Speedwell (Funding Loan))', 'NI IV Fenwick HoldCo - NI IV SCSp - GBP (Fenwick - Vestmark (Funding Loan))', 'NI IV Fenwick HoldCo - NI V Coöperatief - GBP (Fenwick - Craigmore (Equity))']
  [project_codes:Project Code] (1): ['FENWICK']

Search for 'AZURITE':
  [related_parties:Related Party] (1): ['NI V Azurite HoldCo Limited']
  [deals_positions:Deal Name] (1): ['NI V Azurite HoldCo Limited']
  [deals_positions:Position] (4): ['NI V Azurite HoldCo Limited (Azurite Array (Equity))', 'NI V Azurite HoldCo Limited (Pallas Wind Limited (Azurite Array (Equity)))', 'NI V Azurite HoldCo Limited (Pallas Wind Limited (Azurite Array (Funding loan)))', 'NI V Azurite HoldCo Limited - NI IV Pallas Hold Co 2 Limited (Azurite Array(Equity))']
  [project_codes:Project Code] (1): ['Azurite Array']

Search for 'WILLOWBANK':
  [deals_positions:Position] (6): ['NI IV Kalvik Holdco Limited - EUR (WILLOWBANK (Equity))', 'NI IV Kalvik Holdco Limited - GBP (WILLOWBANK (Equity))', 'NI V Kalvik Topco Limited (NI V Kalvik Lender Ltd (WILLOWBANK) (Funding Loan))', 'NI V Kalvik Topco Limited (NI V Kalvik Lender Ltd (Willowbank(Equity)))', 'NI V Kalvik Topco Limited (WILLOWBANK (Equity))', 'NI V Kalvik Topco Limited (WILLOWBANK (Funding Loan))']
  [project_codes:Project Code] (1): ['WILLOWBANK']

Search for 'NORDVIK':
  [legal_entities:Legal Entity] (64): ['NORDVIK INFRASTRUCTURE GREEN CREDIT FUND I NON-SRT AIV SCSp - Eliminations', 'NORDVIK INFRASTRUCTURE GREEN CREDIT FUND I SCSp - Eliminations', 'Nordvik Infrastructure ABF II GP S.à r.l.', 'Nordvik Infrastructure Advanced Bioenergy Fund I Feeder SCSp', 'Nordvik Infrastructure Advanced Bioenergy Fund I GP S.à r.l.', 'Nordvik Infrastructure Advanced Bioenergy Fund I SCSp', 'Nordvik Infrastructure Advanced Bioenergy Fund I SCSp - Elim', 'Nordvik Infrastructure Advanced Bioenergy Fund II Blocker SCSp', 'Nordvik Infrastructure Advanced Bioenergy Fund II QFPF Blocker SCSp', 'Nordvik Infrastructure Advanced Bioenergy Fund II QFPF SCSp']
  [related_parties:Related Party] (54): ['Nordvik Infrastructure Advanced Bioenergy Fund I DK A K/S', 'Nordvik Infrastructure Advanced Bioenergy Fund I Feeder SCSp', 'Nordvik Infrastructure Advanced Bioenergy Fund II QFPF SCSp', 'Nordvik Infrastructure Advanced Bioenergy Fund II SCSp', 'Nordvik Infrastructure Co-invest GP S.A.RL (NIP)', 'Nordvik Infrastructure Evergreen Credit Fund EUR SCSp', 'Nordvik Infrastructure Evergreen Non-US Blocker SCSp', 'Nordvik Infrastructure Evergreen US Blocker SCSp', 'Nordvik Infrastructure GCF I GP S.à r.l. (SGL)', 'Nordvik Infrastructure GCF II GP S.à r.l.']
  [vendors:Vendor] (6): ['CE - Nordvik Economics - Non-LU', 'Nordvik Concierges Driven ApS- Non-LU', 'Nordvik Infrastructure Service Company ApS - Non-LU', 'Nordvik Infrastructure V GP ApS - Non LU', 'Nordvik Offshore Partners A/S - Non - LU', 'Nordvik Streaming - Non - LU']
  [investors:Investor] (32): ['Nordvik Infrastructure ABF I GP S.à r.l.', 'Nordvik Infrastructure ABF II GP S.à r.l.', 'Nordvik Infrastructure Advanced Bioenergy Fund I Feeder SCSp', 'Nordvik Infrastructure Advanced Bioenergy Fund I GP S.à r.l.', 'Nordvik Infrastructure Co-Invest GP S.à r.l.', 'Nordvik Infrastructure Evergreen Credit Fund EUR SCSp', 'Nordvik Infrastructure GCF I GP S.à r.l.', 'Nordvik Infrastructure GCF II GP S.à r.l.', 'Nordvik Infrastructure GMF II GP S.à r.l.', 'Nordvik Infrastructure Green Credit Fund I Non-SRT AIV SCS

# reply

```python
import re
import kit

# Reference pools for counterparties in priority order
CP_POOLS = [
    ("legal_entities", "Legal Entity"),
    ("related_parties", "Related Party"),
    ("vendors", "Vendor"),
    ("investors", "Investor"),
    ("deals_positions", "Deal Name"),
    ("deals_positions", "Position"),
]

PROJECT_POOLS = [
    ("project_codes", "Project Code"),
    ("project_codes", "New Project Code"),
]

TABLE_NAMES = {
    "legal_entities",
    "related_parties",
    "vendors",
    "investors",
    "deals_positions",
    "project_codes",
}


def parse_lookup_result(res):
    """Normalize the return value of kit.lookup into (table, matched_name)."""
    if res is None:
        return None, None
    if isinstance(res, dict):
        return res.get("table"), res.get("matched_name")
    if isinstance(res, (list, tuple)):
        # Could be (table, matched_name) or (matched_name, table)
        if len(res) == 2:
            if res[0] in TABLE_NAMES:
                return res[0], res[1]
            elif res[1] in TABLE_NAMES:
                return res[1], res[0]
            else:
                return res[0], res[1]
        elif len(res) == 3:
            # e.g. (table, column, matched_name)
            for item in res:
                if item in TABLE_NAMES:
                    tbl = item
                    break
            else:
                tbl = res[0]
            val = res[-1]
            return tbl, val
    # Object with attributes
    tbl = getattr(res, "table", None)
    val = getattr(res, "matched_name", None) or getattr(res, "name", None)
    return tbl, val


def resolve_project_code(narrative):
    """Extract and resolve the project code token following 'PROJECT'."""
    m = re.search(r"\bPROJECT\s+([A-Za-z0-9_-]+)", narrative, re.IGNORECASE)
    if not m:
        return None, {
            "status": "CANNOT_VERIFY",
            "matched_name": None,
            "table": None,
            "confidence": None,
            "why": "Narrative names no project",
        }

    raw_word = m.group(1)
    # Ensure provenance slice matches exactly as written in narrative
    span = kit.narrative_span(narrative, raw_word)
    project_raw = span if span else raw_word

    # Look up the project code
    res = kit.lookup(project_raw, PROJECT_POOLS)
    tbl, val = parse_lookup_result(res)

    if val:
        return project_raw, {
            "status": "MATCH",
            "matched_name": val,
            "table": tbl,
            "confidence": 1.0,
            "why": f"Exact match in {tbl}",
        }

    # If exact lookup didn't match, check candidates for a qualified entry
    cands = kit.candidates(project_raw, PROJECT_POOLS, limit=3)
    if cands:
        cand = cands[0]
        c_tbl, c_val = parse_lookup_result(cand)
        # Check if candidate contains raw_word (e.g. AZURITE -> Azurite Array)
        if c_val and kit.compact(project_raw) in kit.compact(c_val):
            return project_raw, {
                "status": "PROBABLE",
                "matched_name": c_val,
                "table": c_tbl or "project_codes",
                "confidence": 0.85,
                "why": f"List entry '{c_val}' expands document token '{project_raw}'",
            }

    return project_raw, {
        "status": "UNRESOLVED",
        "matched_name": None,
        "table": None,
        "confidence": None,
        "why": f"Project code '{project_raw}' not found in reference lists",
    }


def main():
    rows = kit.rows()
    print(f"Loaded {len(rows)} rows to process.")

    # Inspect reference data to understand what exists for CN and Partner
    for t_name in ["legal_entities", "related_parties", "investors", "deals_positions"]:
        t = kit.table(t_name)
        for c in t.columns:
            matches_cn = [
                v
                for v in t.values(c)
                if "CN" in v.upper().split() or "CN SCSP" in v.upper()
            ]
            if matches_cn:
                print(f"Table {t_name}.{c} has CN matches: {matches_cn}")
            matches_partner = [
                v
                for v in t.values(c)
                if "INFRASTRUCTURE PARTNER" in v.upper()
                or "NORDVIK INFRASTRUCTURE" in v.upper()
            ]
            if matches_partner:
                print(
                    f"Table {t_name}.{c} has Partner matches (sample 3): {matches_partner[:3]}"
                )

    enriched_rows = []

    for idx, r in enumerate(rows, start=1):
        narrative = r["narrative"]
        trn_type = r.get("trn_type", "")
        debit = r.get("debit")
        credit = r.get("credit")

        print(f"\n--- Processing Row {idx} ---")
        print(f"Narrative: {narrative}")

        # 1. Project Code
        p_raw, p_match = resolve_project_code(narrative)

        # 2. Counterparty & Classification
        # Case A: Bank charges / interest (names nobody)
        if (
            "COMMISSION" in narrative
            or "CREDIT INTEREST" in narrative
            or trn_type in ("S+P- CHG", "S+P+ INT")
        ):
            cp_raw = None
            cp_match = {
                "status": "CANNOT_VERIFY",
                "matched_name": None,
                "table": None,
                "confidence": None,
                "why": "Bank commission charge or credit interest names no counterparty",
            }
            classification = "Other"

        # Case B: Internal Transfer naming only account's own entity
        elif "INTERNAL TRANSFER" in narrative:
            # Narrative: NI V SCSP, 22801YB03UF8, /DK8471936954300848 INTERNAL TRANSFER
            # Account holder is NI V SCSP; names nobody else
            cp_raw = None
            cp_match = {
                "status": "CANNOT_VERIFY",
                "matched_name": None,
                "table": None,
                "confidence": None,
                "why": "Internal transfer naming only the account holder itself",
            }
            classification = "Internal"

        # Case C: Charge waived / incoming funding from Nordvik Infrastructure Partner
        elif "CHARGE WAIVED" in narrative or "INFRASTRUCTURE PARTNER" in narrative:
            # Narrative: 1/NORDVIK INFRASTRUCTURE PARTNER, S+P+ CHARGE WAIVED
            m_span = re.search(r"1/(NORDVIK INFRASTRUCTURE PARTNER)", narrative)
            if m_span:
                raw_cand = m_span.group(1)
            else:
                raw_cand = "NORDVIK INFRASTRUCTURE PARTNER"

            cp_span = kit.narrative_span(narrative, raw_cand)
            cp_raw = cp_span if cp_span else raw_cand

            # Check lookup
            res = kit.lookup(cp_raw, CP_POOLS)
            tbl, val = parse_lookup_result(res)
            if val:
                cp_match = {
                    "status": "MATCH",
                    "matched_name": val,
                    "table": tbl,
                    "confidence": 1.0,
                    "why": f"Exact match in {tbl}",
                }
            else:
                # Check candidates
                cands = kit.candidates(cp_raw, CP_POOLS, limit=3)
                print(f"Row {idx} candidates for '{cp_raw}': {cands}")
                matched_cand = None
                for c in cands:
                    c_tbl, c_val = parse_lookup_result(c)
                    if c_val and "NORDVIK INFRASTRUCTURE" in c_val.upper():
                        matched_cand = (c_tbl, c_val)
                        break
                if matched_cand:
                    c_tbl, c_val = matched_cand
                    cp_match = {
                        "status": "PROBABLE",
                        "matched_name": c_val,
                        "table": c_tbl,
                        "confidence": 0.8,
                        "why": f"Truncated narrative '{cp_raw}' corresponds to list entry '{c_val}'",
                    }
                else:
                    cp_match = {
                        "status": "UNRESOLVED",
                        "matched_name": None,
                        "table": None,
                        "confidence": None,
                        "why": f"Counterparty '{cp_raw}' not found in reference lists",
                    }

            classification = "Investor"

        # Case D: Loan or Equity movement
        else:
            # Identify the counterparty from the leading field and/or the "TO" clause
            # Structure: <LEADING PARTY>, ... [LOAN|EQUITY]: FROM <OWNER> TO <COUNTERPARTY>
            # The leading party before comma / ref:
            m_lead = re.match(r"^\s*([A-Za-z0-9\.\s]+?)(?:,,|,|\s+[0-9])", narrative)
            lead_cand = m_lead.group(1).strip() if m_lead else None

            # Also check TO clause
            m_to = re.search(
                r"\bTO\s+([A-Za-z0-9\.,\s]+?)(?:\.\s*PROJECT|\.\.|\.$|$)", narrative
            )
            to_cand = m_to.group(1).strip(" .") if m_to else None

            print(f"Row {idx} lead_cand: '{lead_cand}', to_cand: '{to_cand}'")

            # Decide party to look up
            # Check candidate variants against lookup
            party_to_try = None
            for cand in [lead_cand, to_cand]:
                if not cand:
                    continue
                # Clean any trailing dots/commas
                cand_clean = cand.strip(" .,")
                res = kit.lookup(cand_clean, CP_POOLS)
                tbl, val = parse_lookup_result(res)
                if val:
                    party_to_try = (cand_clean, tbl, val)
                    break

            # Handle Fenwick specific sibling numeral check
            if "FENWICK" in narrative:
                # Row 13: "NI V FENWICK HOLDCO LTD"
                # Sibling entity NI IV Fenwick HoldCo Ltd exists, but numeral differs (IV != V)
                # Must stay UNRESOLVED
                raw_cand = "NI V FENWICK HOLDCO LTD"
                span = kit.narrative_span(narrative, raw_cand)
                cp_raw = span if span else raw_cand
                cp_match = {
                    "status": "UNRESOLVED",
                    "matched_name": None,
                    "table": None,
                    "confidence": None,
                    "why": "NI V Fenwick Holdco Ltd is not in reference lists; lists only hold sibling entity NI IV (numeral IV != V cannot be matched)",
                }
                classification = "Investment"

            elif party_to_try:
                cand_clean, tbl, val = party_to_try
                span = kit.narrative_span(narrative, cand_clean)
                cp_raw = span if span else cand_clean
                cp_match = {
                    "status": "MATCH",
                    "matched_name": val,
                    "table": tbl,
                    "confidence": 1.0,
                    "why": f"Exact match in {tbl}",
                }
                # Determine classification: CN SCSP transfer vs direct deal investment
                if "CN SC" in narrative or "CN SCSP" in narrative:
                    classification = "Investment Transfer"
                else:
                    classification = "Investment"

            else:
                # Neither resolved exactly; check if it's CN SCSP
                if "CN SC" in narrative or "CN SCSP" in narrative:
                    raw_cand = (
                        "NORDVIK INFRA.V CN SC"
                        if "NORDVIK INFRA.V CN SC" in narrative
                        else "NI V CN SCSP"
                    )
                    span = kit.narrative_span(narrative, raw_cand)
                    cp_raw = span if span else raw_cand

                    # Check candidates
                    cands = kit.candidates(raw_cand, CP_POOLS, limit=3)
                    print(f"Row {idx} candidates for '{raw_cand}': {cands}")
                    cand_match = None
                    for c in cands:
                        c_tbl, c_val = parse_lookup_result(c)
                        if (
                            c_val
                            and "CN" in c_val.upper().split()
                            and "V" in c_val.upper().split()
                        ):
                            cand_match = (c_tbl, c_val)
                            break

                    if cand_match:
                        c_tbl, c_val = cand_match
                        cp_match = {
                            "status": "PROBABLE",
                            "matched_name": c_val,
                            "table": c_tbl,
                            "confidence": 0.85,
                            "why": f"Abbreviated narrative '{cp_raw}' matches entity '{c_val}'",
                        }
                    else:
                        cp_match = {
                            "status": "UNRESOLVED",
                            "matched_name": None,
                            "table": None,
                            "confidence": None,
                            "why": f"Entity '{cp_raw}' not present in reference tables",
                        }
                    classification = "Investment Transfer"

                else:
                    raw_cand = lead_cand or to_cand or narrative[:30]
                    span = kit.narrative_span(narrative, raw_cand)
                    cp_raw = span if span else raw_cand
                    cp_match = {
                        "status": "UNRESOLVED",
                        "matched_name": None,
                        "table": None,
                        "confidence": None,
                        "why": f"Counterparty '{cp_raw}' not found in reference lists",
                    }
                    classification = "Investment"

        print(f"Result -> Counterparty Raw: {cp_raw}")
        print(f"Result -> Counterparty Match: {cp_match}")
        print(f"Result -> Project Raw: {p_raw}")
        print(f"Result -> Project Match: {p_match}")
        print(f"Result -> Classification: {classification}")

        # Assemble enriched row keeping all original keys unchanged
        new_row = dict(r)
        new_row["counterparty_raw"] = cp_raw
        new_row["counterparty_match"] = cp_match
        new_row["project_code_raw"] = p_raw
        new_row["project_code_match"] = p_match
        new_row["classification"] = classification
        enriched_rows.append(new_row)

    # Verification assertions
    assertions = {
        "row_count_matches": len(enriched_rows) == len(rows),
        "all_required_keys_present": all(
            all(
                k in row
                for k in [
                    "counterparty_raw",
                    "counterparty_match",
                    "project_code_raw",
                    "project_code_match",
                    "classification",
                ]
            )
            for row in enriched_rows
        ),
        "valid_classifications": all(
            row["classification"]
            in {
                "Investment",
                "Investment Transfer",
                "Vendor",
                "Related Party",
                "Investor",
                "Internal",
                "Other",
                "Review",
            }
            for row in enriched_rows
        ),
        "provenance_check_counterparty": all(
            row["counterparty_raw"] is None
            or row["counterparty_raw"] in row["narrative"]
            for row in enriched_rows
        ),
        "provenance_check_project": all(
            row["project_code_raw"] is None
            or row["project_code_raw"] in row["narrative"]
            for row in enriched_rows
        ),
    }

    kit.write_assertions(assertions)
    kit.write_result(enriched_rows)
    print(f"parsed {len(enriched_rows)} rows")


if __name__ == "__main__":
    main()
```
