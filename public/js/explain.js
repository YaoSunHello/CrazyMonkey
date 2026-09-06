/* What each line of the log actually means.
   ---------------------------------------------------------------------------
   The person this product is for is a fund manager, not an engineer. They can
   read `● sandbox  ready · 2 data files` and learn nothing from it. Clicking it
   should answer two questions: what just happened, and why should I care.

   Everything here is copy, keyed by the event's kind and label. Nothing in this
   file computes anything, so adding a step to the backend is one entry here and
   nothing else. An unrecognised step still renders — with its raw fields — so a
   new event kind degrades to "we do not have words for this yet" rather than to
   a blank panel.  */

(function () {
  "use strict";

  /* Keyed "<kind>" or "<kind>:<label>". `what` is what happened; `why` is the
     sentence that makes it matter. */
  const EVENTS = {
    "state:starting": {
      title: "The run begins",
      what: "One bank statement PDF is picked up, and the reference lists it will be " +
            "matched against are loaded. The passes listed here run in order, and each " +
            "one has to satisfy the verifier before the next one starts.",
      why: "Nothing is emitted until the arithmetic holds. That rule is set here, before " +
           "the model has been asked for anything.",
    },
    "state:attempt": {
      title: "A fresh attempt",
      what: "The model is asked to write the code for this pass. If an earlier attempt was " +
            "rejected, the exact failures — row number, expected, actual, delta — went into " +
            "this prompt.",
      why: "It is retrying against ground truth, not against a hunch. That is what the " +
           "self-checking statement makes possible.",
    },
    "state:accepted": {
      title: "The pass was accepted",
      what: "Every check on this pass came back PASS or CANNOT_VERIFY. The output is written " +
            "to disk and the next pass starts from it.",
      why: "Accepted means a deterministic checker agreed, not that the model was confident.",
    },
    "state:rejected": {
      title: "The verifier rejected this attempt",
      what: "At least one check came back FAIL. The output is thrown away and the failures are " +
            "handed back to the model verbatim.",
      why: "This is the product working, not the product failing. A wrong number caught here " +
           "is a wrong number that never reached a journal entry.",
    },
    "state:exhausted": {
      title: "Out of attempts",
      what: "The pass never satisfied the verifier within its attempt budget, so the run stops " +
            "here and emits nothing for it.",
      why: "Refusing to answer is the correct outcome. The alternative is a confident number " +
           "nobody checked.",
    },

    "tool:reference": {
      title: "Reference lists loaded",
      what: "The counterparty, project-code, chart-of-accounts and legal-entity lists are read " +
            "in, with their row counts. The model may only match against these.",
      why: "A name that is not on one of these lists cannot be matched to. That is the " +
           "mechanism that stops a plausible-looking counterparty being invented.",
    },
    "tool:sandbox": {
      title: "A disposable container",
      what: "A throwaway Linux container is created, the statement and the toolkit are uploaded, " +
            "and the model's code runs in there. It is destroyed when the run ends.",
      why: "Code written by a model runs somewhere it can do no harm, and never on the machine " +
           "holding the statements.",
    },
    "tool:model": {
      title: "The model writes the code",
      what: "The model is given the statement text and a small toolkit and asked to write a " +
            "program. It does not get the answers, and it cannot reach the verifier.",
      why: "The model is a candidate generator. Whether its work is any good is decided by " +
           "something it cannot influence.",
    },
    "tool:run_python": {
      title: "The code runs",
      what: "The program the model just wrote is executed in the container. Its output and any " +
            "traceback come back as the lines below.",
      why: "A program that will not run is caught here, before anything it produced is looked at.",
    },
    "tool:explore": {
      title: "A look at the data first",
      what: "Before writing the resolver, the model gets a fixed number of read-only rounds to " +
            "inspect the reference lists and its own extracted rows.",
      why: "Bounded on purpose. It can look at what it is matching against, but it cannot " +
           "wander, and the rounds are recorded here.",
    },
    "tool:assertions": {
      title: "The code's own claims, re-checked",
      what: "The model's program reported checks it believed it had passed. Those claims are " +
            "re-run here against the real output.",
      why: "A self-reported pass is a claim. It is worth something only once somebody else " +
           "has run it.",
    },
    "tool:output": {
      title: "Written to disk",
      what: "The accepted rows for this pass are saved into the run directory.",
      why: "Every run is kept and can be replayed later without the model. This screen is that " +
           "replay.",
    },
    "tool:run_checks": {
      title: "The verifier is invoked",
      what: "The deterministic checks are run over whatever the pass produced.",
      why: "Same code the command line runs. There is no second implementation that could drift.",
    },

    code: {
      title: "The code the model wrote",
      what: "This is the actual program, in full — not a summary of it. Every attempt's source " +
            "is kept beside the run, so a failure can be read rather than guessed at.",
      why: "When a run goes wrong the first useful thing is the code that went wrong. It is not " +
           "buried inside a log.",
    },
    stdout: {
      title: "Output from the agent's code",
      what: "A line the model's own program printed while running in the container.",
      why: "Kept because it is the only view into what the code thought it was doing.",
    },
    stderr: {
      title: "Error output",
      what: "A line the model's program wrote to the error stream — a warning, or a traceback.",
      why: "Not necessarily a failure: pip warnings land here too. The verdict below decides.",
    },
    think: {
      title: "The model reasoning",
      what: "The model's private working, streamed as it arrives. It is not the answer — the code " +
            "it produces comes separately.",
      why: "Shown because the wait is otherwise unexplained. One measured run produced 120,000 " +
           "characters of this and no code at all, which is why it is now switched off by default.",
    },
    verdict: {
      title: "The verifier ran",
      what: "Plain Python — no model, no network, no sandbox — reads the output and decides. It is " +
            "the same code the command line runs, and the agent has no way to reach it.",
      why: "Three outcomes, not two. PASS holds, FAIL blocks the output, and UNRESOLVED means the " +
           "parse was fine but a value has no match and a person has to decide.",
    },
  };

  const FALLBACK = {
    title: "A step in the run",
    what: "This step has no explanation written for it yet. Its raw fields are below, exactly as " +
          "they were recorded.",
    why: "",
  };

  /* One line per check, in the reader's language rather than the function's. */
  const CHECKS = {
    balance_chain:
      "Each row's balance minus its amount must equal the next row's balance. If the parse is " +
      "right the chain closes; if a number was misread it does not. This is the oracle the " +
      "whole pipeline retries against.",
    closing_balance:
      "The newest row's balance must equal the closing balance printed on the statement.",
    printed_openings:
      "Where the statement prints a 'balance brought forward' marker, the chain must start there.",
    row_count:
      "The number of rows parsed must equal the number of transaction lines in the raw page text.",
    one_amount_per_row:
      "Every row carries exactly one amount — a debit or a credit, never both and never neither.",
    reference_provenance:
      "Every bank reference must appear literally in the PDF text. A reference that was tidied " +
      "up is a reference that was invented.",
    counterparty_raw_provenance:
      "Every counterparty string read out of a narrative must be a literal substring of that " +
      "same narrative.",
    project_code_raw_provenance:
      "Every project code read out of a narrative must be a literal substring of that narrative.",
    counterparty_match_membership:
      "Every counterparty match must name a row that exists in a named reference list.",
    project_code_match_membership:
      "Every project-code match must name a row that exists in a named reference list.",
    resolution_completeness:
      "Every resolution carries one of the three statuses. Silence is not an allowed answer.",
    classification_vocabulary:
      "Every classification is one of the declared labels — not a phrase the model made up.",
    counterparty_raw_span:
      "What was read out as a counterparty has to look like a party name, not a fragment of a " +
      "reference number.",
    counterparty_match_pairing:
      "A row's match must correspond to the string that row actually read out of its narrative.",
    counterparty_match_not_self:
      "The counterparty cannot be this account's own party. A statement line has two sides, and " +
      "naming your own side as the counterparty is a misread, not a match.",
    counterparty_match_proposals:
      "Where a near miss is offered instead of a match, it must be offered as a proposal for a " +
      "person to accept — never silently promoted to a match.",
    counterparty_match_proposal_distance:
      "A proposed near miss has to be near. A proposal too far from what the document says is " +
      "a guess wearing a suggestion's clothes.",
    counterparty_match_resolution_rate:
      "Of the counterparties actually read out of the document, a reasonable share should resolve. " +
      "Far too few means the matcher gave up; far too many means it forced matches.",
    classification_review_rate:
      "'Review' is a legitimate answer, but a fallback label absorbing most of the statement is a " +
      "decision not made rather than a decision to defer.",
    project_code_raw_span:
      "What was read out as a project code has to look like one.",
    double_entry:
      "Every journal batch must balance: debits equal credits, to the penny.",
    posting:
      "Every journal line must post to an account that exists in the chart of accounts.",
  };

  const STATUSES = {
    PASS: "The check holds. Nobody has to do anything.",
    FAIL: "The arithmetic or the structure is wrong. Output is blocked and the pass is retried.",
    UNRESOLVED: "It parsed correctly, but a value has no match in the reference data. A person " +
                "decides this one, with a citation to work from.",
    CANNOT_VERIFY: "There was nothing to check — the document named nobody. That is a finding, " +
                   "not a gap.",
  };

  CM.explain = {
    /* Labels carry a detail suffix in practice ("sandbox" with detail
       "creating · python:3.11-bookworm"), so the label alone is the key. */
    forEvent(event) {
      if (!event) return FALLBACK;
      return EVENTS[`${event.kind}:${event.label}`] || EVENTS[event.kind] || FALLBACK;
    },

    forCheck(name) {
      if (!name) return "";
      // `self:batches_balance` — a claim the model's own code made, re-run by
      // the verifier. The prefix is the whole point, so it is spelled out.
      if (name.startsWith("self:")) {
        return "A check the model's own program claimed to have passed, re-run here against the " +
               "real output. " + (CHECKS[name.slice(5)] || "");
      }
      return CHECKS[name] || "";
    },

    forStatus(status) {
      return STATUSES[status] || "";
    },
  };
})();
