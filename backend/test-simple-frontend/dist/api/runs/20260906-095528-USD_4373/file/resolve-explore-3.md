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

There are 19 rows to resolve.

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
Available tables: ['account_map', 'deals_positions', 'investors', 'legal_entities', 'project_codes', 'related_parties', 'vendors']

Table 'account_map': columns = ['Account Number', 'Bank Account']
  Col 'Account Number' (7 entries): sample -> ['240-149813-030', '240-149813-131', '240-222731-030', '240-222731-132', '240-222731-135']
  Col 'Bank Account' (7 entries): sample -> ['Calder 0894 EUR', 'NI ABF II - Calder - DKK - 4319', 'NI ABF II - Calder - EUR - 8102', 'NI GMF II - Calder - USD - 4373', 'NIP V - Calder - DKK - 0541']

Table 'deals_positions': columns = ['Deal Name', 'Position']
  Col 'Deal Name' (287 entries): sample -> ['ADVOKATFIRMAET LAURITZEN AS - NOK', 'ADVOKATFIRMAET LAURITZEN AS - NOK (Do not use!!!)', 'Agatestone Chione I', 'Agatestone Grove 2 HoldCo LLC', 'Agatestone Grove DevCo LLC - USD']
  Col 'Position' (1524 entries): sample -> ['ADVOKATFIRMAET LAURITZEN AS - NOK (ADVOKATFIRMAET LAURITZEN AS (Snotra) (Equity))', 'ADVOKATFIRMAET LAURITZEN AS - NOK (Snotra (Equity))', 'Agatestone Chione I (Equity)', 'Agatestone Grove 2 HoldCo LLC (Agatestone Grove 2 LLC (Agatestone Grove II) (Equity))', 'Agatestone Grove 2 HoldCo LLC (Agatestone Grove 2 LLC (Agatestone Grove II) (Funding Loan))']

Table 'investors': columns = ['Investor']
  Col 'Investor' (277 entries): sample -> ['Aeroven Wind Systems A/S', 'ApS Glanworth', 'ApS HET', 'ApS ZOF', 'Ashdale Linddale- hollmont Wrenshaw']

Table 'legal_entities': columns = ['Legal Entity']
  Col 'Legal Entity' (97 entries): sample -> ['AGP NI Co-Invest I SCSp', 'Alcor NI Co-Invest SCSp', 'Alnair NI Co-invest LP', 'Avior NI Co-Invest SCSp', 'DK NI Co-Invest K/S']

Table 'project_codes': columns = ['Project Code', 'New Project Code']
  Col 'Project Code' (586 entries): sample -> ['1 OH - DFSA', 'ABF II Fundraising', 'AD MIZAR', 'AEGIR to Methanol', 'AGATESTONE GROVE I']
  Col 'New Project Code' (1 entries): sample -> ['Halstead']

Table 'related_parties': columns = ['Related Party']
  Col 'Related Party' (296 entries): sample -> ['ADVOKATFIRMAET LAURITZEN AS', 'AGP NI CO-Invest I SCSP', 'ANTARES Ottesen', 'ASHGROVE Qtd Holdco Pty Ltd.', 'Agatestone Grove 2 Holdco LLC']

Table 'vendors': columns = ['Vendor']
  Col 'Vendor' (245 entries): sample -> ['ACD', 'AL-Draywick & Associates - Non-LU', 'Admini. de l Enregistrement - LU', 'Administration des Contributions Directes - LU', 'Administration des contributions directes']

=== QUESTIONS ===
[]

=== ROWS ===
Total rows: 19

--- Row 0 ---
  bank_reference: 'TT UCL163D8BANG'
  trn_type: 'S+P-'
  value_date: '31 Mar 2026'
  post_date: '31 Mar 2026'
  time: '07:01'
  narrative: 'BQVRFRPP, /448323310 CHARGE WAIVED'
  credit: None
  debit: '-184939.74'
  balance: '943598.38'
  account_number: '240-644826-130'
  currency: 'USD'
  page: 1

--- Row 1 ---
  bank_reference: 'TT YCB037B7GBGIU'
  trn_type: 'S+P- CHG'
  value_date: '31 Mar 2026'
  post_date: '31 Mar 2026'
  time: '07:00'
  narrative: 'COMMISSION USD 6,87, 16138PF705L0'
  credit: None
  debit: '-6.87'
  balance: '1128538.12'
  account_number: '240-644826-130'
  currency: 'USD'
  page: 1

--- Row 2 ---
  bank_reference: 'TT YCB037B7GBGIU'
  trn_type: 'S+P-'
  value_date: '31 Mar 2026'
  post_date: '31 Mar 2026'
  time: '07:00'
  narrative: 'NI GMF II COOPERATIEF U.A, 16138PF705L0, /DK8510041070352358 EQUITY: FROM NORDVIK, INFRASTRUCTURE GROWTH MARKET FUND II SCSP TO NI GMF II, COOPERATIEF U.A. PROJECT ATRIA'
  credit: None
  debit: '-40000.00'
  balance: '1128544.99'
  account_number: '240-644826-130'
  currency: 'USD'
  page: 1

--- Row 3 ---
  bank_reference: 'TT TJK451YCABAJG'
  trn_type: 'S+P- CHG'
  value_date: '31 Mar 2026'
  post_date: '31 Mar 2026'
  time: '07:00'
  narrative: 'COMMISSION USD 6,87, 01104ZP014LE'
  credit: None
  debit: '-6.87'
  balance: '1168544.99'
  account_number: '240-644826-130'
  currency: 'USD'
  page: 1

--- Row 4 ---
  bank_reference: 'TT TJK451YCABAJG'
  trn_type: 'S+P-'
  value_date: '31 Mar 2026'
  post_date: '31 Mar 2026'
  time: '07:00'
  narrative: 'NI GMF II SCSP, 01104ZP014LE, /DK0996402923176963 INTERNAL TRANSFER'
  credit: None
  debit: '-85000.00'
  balance: '1168551.86'
  account_number: '240-644826-130'
  currency: 'USD'
  page: 1

--- Row 5 ---
  bank_reference: 'TT TID363HB4NMXE'
  trn_type: 'S+P- CHG'
  value_date: '31 Mar 2026'
  post_date: '31 Mar 2026'
  time: '07:00'
  narrative: 'COMMISSION USD 6,87, 94453FH69CVT'
  credit: None
  debit: '-6.87'
  balance: '1253551.86'
  account_number: '240-644826-130'
  currency: 'USD'
  page: 1

--- Row 6 ---
  bank_reference: 'TT TID363HB4NMXE'
  trn_type: 'S+P-'
  value_date: '31 Mar 2026'
  post_date: '31 Mar 2026'
  time: '07:00'
  narrative: 'NI GMF II COOPERATIEF U.A., 94453FH69CVT, /DK8510041070352358 EQUITY: FROM NORDVIK INFRASTRUCTURE GROWTH MARKETS FUND II SCSP TO NI GMF II COOPERATIEF U.A. PROJECT TANSYMOOR.'
  credit: None
  debit: '-750000.00'
  balance: '1253558.73'
  account_number: '240-644826-130'
  currency: 'USD'
  page: 1

--- Row 7 ---
  bank_reference: 'TT XTT580QZUKJDU'
  trn_type: 'S+P- CHG'
  value_date: '31 Mar 2026'
  post_date: '31 Mar 2026'
  time: '07:00'
  narrative: 'COMMISSION USD 6,87, 93301QH142TF'
  credit: None
  debit: '-6.87'
  balance: '2003558.73'
  account_number: '240-644826-130'
  currency: 'USD'
  page: 2

--- Row 8 ---
  bank_reference: 'TT XTT580QZUKJDU'
  trn_type: 'S+P-'
  value_date: '31 Mar 2026'
  post_date: '31 Mar 2026'
  time: '07:00'
  narrative: 'NI GMF II COOPERATIEF U.A, 93301QH142TF, /DK8510041070352358 EQUITY: FROM NI GMF II SCSP TO, NI GMF II COOPERATIEF U.A. PROJECT IAPETUS.'
  credit: None
  debit: '-667723.00'
  balance: '2003565.60'
  account_number: '240-644826-130'
  currency: 'USD'
  page: 2

--- Row 9 ---
  bank_reference: 'TT LKS976XV0DUWR'
  trn_type: 'S+P- CHG'
  value_date: '31 Mar 2026'
  post_date: '31 Mar 2026'
  time: '07:00'
  narrative: 'COMMISSION USD 6,87, 43433NJ28TB0'
  credit: None
  debit: '-6.87'
  balance: '2671288.60'
  account_number: '240-64482
--- you ran explore-2.py and it printed ---
account_map accounts: ['240-149813-030', '240-149813-131', '240-222731-030', '240-222731-132', '240-222731-135', '240-524291-030', '240-644826-130']
account_map bank accounts: ['Calder 0894 EUR', 'NI ABF II - Calder - DKK - 4319', 'NI ABF II - Calder - EUR - 8102', 'NI GMF II - Calder - USD - 4373', 'NIP V - Calder - DKK - 0541', 'NIP V - Calder - EUR - 030041', 'NIP V - Calder - GBP - 3252']
Found account in account_map: Account Number
Found account in account_map: Bank Account
Total rows: 19
--- Row 0 ---
  trn_type: S+P-
  narrative: BQVRFRPP, /448323310 CHARGE WAIVED
  debit: -184939.74 | credit: None
  account: 240-644826-130
--- Row 1 ---
  trn_type: S+P- CHG
  narrative: COMMISSION USD 6,87, 16138PF705L0
  debit: -6.87 | credit: None
  account: 240-644826-130
--- Row 2 ---
  trn_type: S+P-
  narrative: NI GMF II COOPERATIEF U.A, 16138PF705L0, /DK8510041070352358 EQUITY: FROM NORDVIK, INFRASTRUCTURE GROWTH MARKET FUND II SCSP TO NI GMF II, COOPERATIEF U.A. PROJECT ATRIA
  debit: -40000.00 | credit: None
  account: 240-644826-130
--- Row 3 ---
  trn_type: S+P- CHG
  narrative: COMMISSION USD 6,87, 01104ZP014LE
  debit: -6.87 | credit: None
  account: 240-644826-130
--- Row 4 ---
  trn_type: S+P-
  narrative: NI GMF II SCSP, 01104ZP014LE, /DK0996402923176963 INTERNAL TRANSFER
  debit: -85000.00 | credit: None
  account: 240-644826-130
--- Row 5 ---
  trn_type: S+P- CHG
  narrative: COMMISSION USD 6,87, 94453FH69CVT
  debit: -6.87 | credit: None
  account: 240-644826-130
--- Row 6 ---
  trn_type: S+P-
  narrative: NI GMF II COOPERATIEF U.A., 94453FH69CVT, /DK8510041070352358 EQUITY: FROM NORDVIK INFRASTRUCTURE GROWTH MARKETS FUND II SCSP TO NI GMF II COOPERATIEF U.A. PROJECT TANSYMOOR.
  debit: -750000.00 | credit: None
  account: 240-644826-130
--- Row 7 ---
  trn_type: S+P- CHG
  narrative: COMMISSION USD 6,87, 93301QH142TF
  debit: -6.87 | credit: None
  account: 240-644826-130
--- Row 8 ---
  trn_type: S+P-
  narrative: NI GMF II COOPERATIEF U.A, 93301QH142TF, /DK8510041070352358 EQUITY: FROM NI GMF II SCSP TO, NI GMF II COOPERATIEF U.A. PROJECT IAPETUS.
  debit: -667723.00 | credit: None
  account: 240-644826-130
--- Row 9 ---
  trn_type: S+P- CHG
  narrative: COMMISSION USD 6,87, 43433NJ28TB0
  debit: -6.87 | credit: None
  account: 240-644826-130
--- Row 10 ---
  trn_type: S+P-
  narrative: NI GMF II COOPERATIEF U.A, 43433NJ28TB0, /DK8510041070352358 EQUITY: FROM NORDVIK, INFRASTRUCTURE GROWTH MARKETS FUND II SCSP TO NI GMF II, COOPERATIEF U.A. PROJECT BRAGI.
  debit: -736000.00 | credit: None
  account: 240-644826-130
--- Row 11 ---
  trn_type: S+P-
  narrative: BQVRFRPP, /448323310 CHARGE WAIVED
  debit: -10000000.00 | credit: None
  account: 240-644826-130
--- Row 12 ---
  trn_type: S+P+
  narrative: 1/NORDVIK INFRASTRUCTURE PARTNER, S+P+ CHARGE WAIVED
  debit: None | credit: 13007460.48
  account: 240-644826-130
--- Row 13 ---
  trn_type: S+P- CHG
  narrative: COMMISSION USD 6,97, 40123ZC60S9V
  debit: -6.97 | credit: None
  account: 240-644826-130
--- Row 14 ---
  trn_type: S+P-
  narrative: NI GMF II COOPERATIEF U.A, 40123ZC60S9V, /DK8510041070352358 EQUITY: FROM NORDVIK, INFRASTRUCTURE GROWTH MARKET FUND, II SCSP TO NI GMF II COOPERATIEF, U.A. PROJECT OFW-XX-1
  debit: -20000.00 | credit: None
  account: 240-644826-130
--- Row 15 ---
  trn_type: S+P- CHG
  narrative: COMMISSION USD 6,97, 20235GB45D5M
  debit: -6.97 | credit: None
  account: 240-644826-130
--- Row 16 ---
  trn_type: S+P-
  narrative: NI GMF II COOPERATIEF U.A, 20235GB45D5M, /DK8510041070352358 EQUITY: FROM NORDVIK, INFRASTRUCTURE GROWTH MARKETS FUND, II SCSP TO NI GMF II COOPERATIEF, U.A. PROJECT ELMWOOD.
  debit: -260000.00 | credit: None
  account: 240-644826-130
--- Row 17 ---
  trn_type: S+P-
  narrative: BQVRFRPP, /448323310 CHARGE WAIVED
  debit: -38739.87 | credit: None
  account: 240-644826-130
--- Row 18 ---
  trn_type: S+P+ INT
  narrative: CREDIT INTEREST
  debit: None | credit: 3260.28
  account: 240-644826-130

Sample legal entities with GMF or Nordvik:
  LE: AGP NI Co-Invest I SCSp
  LE: Alcor NI Co-Invest SCSp
  LE: Avior NI Co-Invest SCSp
  LE: Delling NI Co-Invest SCSp
  LE: FS NI Co-Invest SCSp
  LE: Magni NI Co-Invest SCSp
  LE: NI GCF I Direct Lending Non-US SCSp
  LE: NI GCF I Direct Lending Non-US SCSp - Eliminations
  LE: NI GCF I Direct Lending US SCSp
  LE: NI GCF I Velaris SCSp
  LE: NI GCF II EUR HedgeCo SCSp
  LE: NI GCF II Non-US Aggregator SCSp
  LE: NI GCF II US Aggregator SCSp
  LE: NI GCF II US Aggregator SCSp - Elimination
  LE: NI GCF II USD HedgeCo SCSp
  LE: NI NKP Co-Invest I SCSp
  LE: NI V Co-Invest Vehicle A SCSp
  LE: NI V GP I SCSp
  LE: NORDVIK INFRASTRUCTURE GREEN CREDIT FUND I NON-SRT AIV SCSp - Eliminations
  LE: NORDVIK INFRASTRUCTURE GREEN CREDIT FUND I SCSp - Eliminations
  LE: Nordvik Infrastructure ABF II GP S.à r.l.
  LE: Nordvik Infrastructure Advanced Bioenergy Fund I Feeder SCSp
  LE: Nordvik Infrastructure Advanced Bioenergy Fund I GP S.à r.l.
  LE: Nordvik Infrastructure Advanced Bioenergy Fund I SCSp
  LE: Nordvik Infrastructure Advanced Bioenergy Fund I SCSp - Elim
  LE: Nordvik Infrastructure Advanced Bioenergy Fund II Blocker SCSp
  LE: Nordvik Infrastructure Advanced Bioenergy Fund II QFPF Blocker SCSp
  LE: Nordvik Infrastructure Advanced Bioenergy Fund II QFPF SCSp
  LE: Nordvik Infrastructure Advanced Bioenergy Fund II SCSp
  LE: Nordvik Infrastructure Co-Invest GP S.à r.l.
  LE: Nordvik Infrastructure Evergreen Credit Fund EUR SCSp
  LE: Nordvik Infrastructure Evergreen Credit Fund EUR SCSp - Elimination
  LE: Nordvik Infrastructure Evergreen Non-US Blocker SCSp
  LE: Nordvik Infrastructure Evergreen US Blocker SCSp
  LE: Nordvik Infrastructure GCF I GP S.à r.l.
  LE: Nordvik Infrastructure GCF II GP S.à r.l.
  LE: Nordvik Infrastructure GMF II GP S.à r.l.
  LE: Nordvik Infrastructure Green Credit Fund I Non-SRT AIV SCSp
  LE: Nordvik Infrastructure Green Credit Fund I SCSp
  LE: Nordvik Infrastructure Green Credit Fund II EUR Non-US Block

# reply

```python
import kit

print("=== ACCOUNT OWNER ===")
am = kit.table('account_map')
print("Account map cols:", am.columns)
for a, b in zip(am.values('Account Number'), am.values('Bank Account')):
    print(f"  {a} -> {b}")

print("\n=== RELATED PARTIES SAMPLE ===")
rp = kit.table('related_parties')
print(f"Total RP: {len(rp.values('Related Party'))}")
for r in rp.values('Related Party'):
    if 'gmf' in r.lower() or 'nordvik' in r.lower() or 'cooperatief' in r.lower():
        print(f"  RP: {r}")

print("\n=== LEGAL ENTITIES SAMPLE ===")
le = kit.table('legal_entities')
print(f"Total LE: {len(le.values('Legal Entity'))}")
for l in le.values('Legal Entity'):
    if 'gmf' in l.lower() or 'growth' in l.lower() or 'cooperatief' in l.lower():
        print(f"  LE: {l}")

print("\n=== PROJECT CODES SAMPLE ===")
pc = kit.table('project_codes')
for c in pc.columns:
    vals = pc.values(c)
    print(f"Project codes col {c}: {len(vals)} items")
    for v in vals:
        if any(w in str(v).lower() for w in ['atria', 'tansymoor', 'iapetus', 'bragi', 'ofw', 'elmwood']):
            print(f"  PC in {c}: {v}")

print("\n=== INVESTORS SAMPLE ===")
inv = kit.table('investors')
print(f"Total Investors: {len(inv.values('Investor'))}")
for i in inv.values('Investor'):
    if 'nordvik' in i.lower() or 'partner' in i.lower():
        print(f"  Inv: {i}")

print("\n=== VENDORS SAMPLE ===")
ven = kit.table('vendors')
print(f"Total Vendors: {len(ven.values('Vendor'))}")
for v in ven.values('Vendor'):
    if 'nordvik' in v.lower() or 'partner' in v.lower() or 'bqvr' in v.lower():
        print(f"  Ven: {v}")

print("\n=== DEALS POSITIONS SAMPLE ===")
dp = kit.table('deals_positions')
for c in dp.columns:
    vals = dp.values(c)
    print(f"Deals/positions {c}: {len(vals)}")
    for v in vals:
        if any(w in str(v).lower() for w in ['atria', 'tansymoor', 'iapetus', 'bragi', 'ofw', 'elmwood']):
            print(f"  DP in {c}: {v}")

print("exploration complete")
```
