"""Schema, reason-code taxonomy, and validation rules for the Article
Eligibility Manual Review stage (E4, E5's L/N-relevance test, E6, E8 -
see news_protocol/article_eligibility_rules.md and the companion
codebook news_protocol/eligibility_manual_review_codebook.md).

Why this exists as a separate module from assess_eligibility.py
-----------------------------------------------------------------
assess_eligibility.py deliberately stops at what a script can decide
honestly (dates, windows, the two relevance-flag audits, language,
retrievability). It explicitly refuses to guess at result leakage
(E4), the L/N relevance test, Reform UK disambiguation (E6), or
genuine-editorial-content (E8) - the rules document requires a human
to read the article for those. This module defines the STRUCTURE that
human judgement is recorded into, so every reviewer (now or in a
future session) fills in the same fields the same way, and a script
can check the result is internally consistent - it never makes the
judgement calls itself.

Design principles carried over from the rest of this pipeline
-----------------------------------------------------------------
  * Never overwrite: original_manual_decision is written once and never
    changed; a later adjudication writes final_reviewed_decision plus a
    correction_reason instead (same "preserve, don't resolve in place"
    discipline as raw_news_schema.json's date_evidence[]).
  * Explicit over guessed: DECISIONS is a closed set including
    "insufficient_evidence" - a reviewer with too little text to judge
    records that honestly, rather than picking include/exclude anyway.
  * Auditable: every reason code maps to exactly one rule (E4/E5/E6/E8)
    and one decision polarity, checked by REASON_CODES below - a typo
    or an invented code fails validation instead of silently passing.
"""

from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Closed vocabularies. Every value a review row can take is listed here
# explicitly - an unrecognised value is a validation error, not a
# silent pass-through, so a typo in a spreadsheet cannot corrupt the
# record silently.
# ---------------------------------------------------------------------------

RULES = ("E4", "E5", "E6", "E8")

# Per-rule decision for one article. "not_applicable" exists only for
# E6 (a record that never matched a Reform-related query has nothing
# to disambiguate) - it is a real, permitted state, not a null.
DECISIONS = ("include", "exclude", "needs_second_review",
            "insufficient_evidence", "not_applicable")

CONFIDENCE_LEVELS = ("high", "medium", "low")

# Overall, whole-article decision, derived from the four per-rule
# decisions by derive_overall_decision() - never set directly by a
# reviewer, so it can never drift out of sync with the per-rule fields
# it is computed from.
OVERALL_DECISIONS = ("include", "exclude", "needs_second_review",
                    "insufficient_evidence")

REVIEW_ROUNDS = ("initial", "second_review", "kappa_blind_recheck")

# Reason codes, grouped by rule. Every code's meaning is spelled out in
# eligibility_manual_review_codebook.md; this dict exists so a script
# can check "is this code even a real one, and does it belong to the
# rule it was recorded against" - it is the single source of truth for
# both the codebook and the validator, so the two cannot drift apart.
REASON_CODES = {
    "E4": {
        # decision: exclude - the rules document's own examples (E4:
        # "reports, previews citing results, or reacts to the
        # election's outcome, exit information, or count")
        "E4-LEAK-RESULT": "exclude",
        "E4-LEAK-COUNT": "exclude",
        "E4-LEAK-EXIT-POLL": "exclude",
        "E4-LEAK-PREVIEW-CITING-RESULT": "exclude",
        # decision: include
        "E4-CLEAR": "include",
        # decision: needs_second_review
        "E4-AMBIGUOUS-TENSE": "needs_second_review",
        "E4-POSSIBLE-POST-PUBLICATION-EDIT": "needs_second_review",
        # decision: insufficient_evidence
        "E4-NO-FULL-TEXT": "insufficient_evidence",
    },
    "E5": {
        # decision: include - one code per L/N-rule in
        # article_eligibility_rules.md section 1, so the specific
        # qualifying rule is always on record, not just "relevant"
        "E5-L1-PLACE": "include",
        "E5-L2-CANDIDATE": "include",
        "E5-L3-COUNCIL-ISSUE": "include",
        "E5-L4-COUNTY-WIDE": "include",
        "E5-N1-PARTY-POLITICS": "include",
        "E5-N2-POLICY-ISSUE": "include",
        "E5-N3-REFORM-GROWTH": "include",
        # decision: exclude
        "E5-NO-L-OR-N-RULE-MET": "exclude",
        # decision: needs_second_review
        "E5-BORDERLINE-PLACE-MENTION": "needs_second_review",
        "E5-BORDERLINE-POLICY-RELEVANCE": "needs_second_review",
        # decision: insufficient_evidence
        "E5-NO-FULL-TEXT": "insufficient_evidence",
    },
    "E6": {
        # decision: include (genuine Reform UK reference)
        "E6-PARTY-CONFIRMED": "include",
        # decision: exclude (false positive)
        "E6-GENERIC-WORD-USE": "exclude",
        # decision: needs_second_review
        "E6-AMBIGUOUS-USAGE": "needs_second_review",
        # decision: insufficient_evidence
        "E6-NO-FULL-TEXT": "insufficient_evidence",
        # decision: not_applicable (record was never Reform-flagged)
        "E6-NOT-REFORM-FLAGGED": "not_applicable",
    },
    "E8": {
        # decision: include - matches I4's list (news report, analysis,
        # opinion, editorial, letter, interview, profile, press release)
        "E8-EDITORIAL-CONFIRMED": "include",
        # decision: exclude
        "E8-LISTING-OR-INDEX-PAGE": "exclude",
        "E8-ADVERT-OR-COMMERCIAL": "exclude",
        "E8-NOTICE-ONLY": "exclude",
        # decision: needs_second_review
        "E8-UNCLEAR-FORMAT": "needs_second_review",
        # decision: insufficient_evidence
        "E8-NO-FULL-TEXT": "insufficient_evidence",
    },
}

# Precedence for deriving the overall decision from the four per-rule
# decisions, mirroring assess_eligibility.py's "first rule failed wins"
# logic and article_eligibility_rules.md's stated check order
# (E4 leakage, then E5 relevance, then E6, then E8/editorial type).
_PRECEDENCE = ("exclude", "needs_second_review", "insufficient_evidence",
              "include")

# The full set of fields one review row carries. Defined once here so
# build_manual_review_sample.py (which creates rows) and
# validate_manual_review.py (which checks them) can never disagree
# about what a row looks like.
REVIEW_FIELDS = [
    "article_id", "election_id", "source_id", "arm",
    "sample_stratum", "review_round",
    # deterministic assessment, carried over verbatim from
    # assess_eligibility.py - never edited by a reviewer
    "deterministic_status", "deterministic_note",
    "needs_reform_disambiguation",
    # per-rule reviewer judgement (E4, E5, E6, E8), each with its own
    # decision / reason code / quoted evidence / confidence
    *(f"{rule.lower()}_decision" for rule in RULES),
    *(f"{rule.lower()}_reason_code" for rule in RULES),
    *(f"{rule.lower()}_supporting_text" for rule in RULES),
    *(f"{rule.lower()}_confidence" for rule in RULES),
    # overall decision bookkeeping - see module docstring on why
    # original and final are kept as two separate, never-overwritten fields
    "reviewer_id",
    "original_manual_decision", "original_review_timestamp",
    "second_review_required",
    "final_reviewed_decision", "correction_reason", "final_review_timestamp",
    "reviewer_note",
]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def needs_second_review_flag(e4, e5, e6, e8):
    """Whether ANY applicable rule is still an open needs_second_review
    question - kept as its own preserved field (requirement: a
    dedicated second-review-requirement field) rather than inferred
    only implicitly from the overall decision, so a record that has
    since been through a second review and resolved to exclude/include
    still shows on its face that it WAS flagged, not just what it
    ended up as."""
    return "needs_second_review" in (e4, e5, e6, e8)


def derive_overall_decision(e4, e5, e6, e8):
    """Pure function: the four per-rule decisions in, one overall
    decision out. E6's "not_applicable" is excluded from the vote
    (a record that was never Reform-flagged cannot fail a
    disambiguation test it was never subject to); every other rule
    must contribute a real decision.

    Precedence matches article_eligibility_rules.md's own check order:
    any exclude wins outright (the article is out), otherwise any
    still-open question (needs_second_review or insufficient_evidence)
    blocks a final "include" - the article can only be included once
    every applicable rule has been resolved to include.
    """
    votes = [d for d in (e4, e5, e6, e8) if d != "not_applicable"]
    for outcome in _PRECEDENCE:
        if outcome in votes:
            return outcome
    # every vote was "not_applicable" - cannot happen for E4/E5/E8
    # (those are never not_applicable), defensive only
    return "insufficient_evidence"


class ValidationError(Exception):
    pass


def validate_row(row, *, context=""):
    """Check ONE review row against every rule in requirement 6 of the
    manual-review protocol. Raises ValidationError with every problem
    found (not just the first), so a reviewer sees the whole picture
    in one pass rather than fixing issues one at a time.
    """
    problems = []
    prefix = f"{context}: " if context else ""

    # --- per-rule internal consistency -----------------------------------
    for rule in RULES:
        decision = row.get(f"{rule.lower()}_decision")
        code = row.get(f"{rule.lower()}_reason_code")
        text = row.get(f"{rule.lower()}_supporting_text")
        confidence = row.get(f"{rule.lower()}_confidence")

        if decision not in DECISIONS:
            problems.append(f"{rule}: decision {decision!r} is not one "
                            f"of {DECISIONS}")
            continue

        if decision == "not_applicable":
            if rule != "E6":
                problems.append(f"{rule}: not_applicable is only a "
                                "valid decision for E6")
            continue

        # every resolved rule must cite a reason code that is a real,
        # registered code AND belongs to this rule AND matches the
        # decision polarity that code is registered under
        if not code:
            problems.append(f"{rule}: decision {decision!r} recorded "
                            "with no reason_code (requirement: every "
                            "exclusion/decision needs an explicit code)")
        elif code not in REASON_CODES[rule]:
            problems.append(f"{rule}: reason_code {code!r} is not a "
                            f"registered {rule} code")
        elif REASON_CODES[rule][code] != decision:
            problems.append(f"{rule}: reason_code {code!r} is "
                            f"registered for decision "
                            f"{REASON_CODES[rule][code]!r}, not "
                            f"{decision!r} - code/decision mismatch")

        # every judgement-based decision needs either quoted evidence,
        # or an explicit, on-record reason evidence isn't available
        # (insufficient_evidence IS that explicit reason - it must not
        # also be required to cite text, since the whole point of that
        # decision is "there wasn't enough text to quote")
        if decision != "insufficient_evidence" and not text:
            problems.append(f"{rule}: decision {decision!r} has no "
                            "supporting_text and is not recorded as "
                            "insufficient_evidence - every judgement "
                            "needs evidence or an explicit reason it's "
                            "unavailable")

        if decision in ("include", "exclude") and confidence not in \
                CONFIDENCE_LEVELS:
            problems.append(f"{rule}: decision {decision!r} needs a "
                            f"confidence level from {CONFIDENCE_LEVELS}, "
                            f"got {confidence!r}")

    # --- overall-decision consistency -------------------------------------
    # The per-rule fields (e4_decision etc.) hold the CURRENT judgement
    # for each rule - if a second review changes one (say, E8 goes from
    # needs_second_review to exclude after adjudication), that field is
    # updated in place, and correction_reason explains why. What must
    # never happen is original_manual_decision retroactively changing
    # to match: it is the roll-up recorded at the FIRST pass, frozen
    # from then on. So the "does the roll-up match the per-rule fields"
    # check only applies to original_manual_decision when nothing has
    # been corrected yet; once corrected, it is final_reviewed_decision
    # that must match the (now-updated) per-rule fields instead.
    e4, e5, e6, e8 = (row.get(f"{r.lower()}_decision") for r in RULES)
    original = row.get("original_manual_decision")
    final = row.get("final_reviewed_decision")
    corrected = bool(final) and bool(original) and final != original

    if all(d in DECISIONS for d in (e4, e5, e6, e8)):
        current_derivation = derive_overall_decision(e4, e5, e6, e8)
        check_field, check_label = (
            ("final_reviewed_decision", "final_reviewed_decision")
            if corrected else
            ("original_manual_decision", "original_manual_decision"))
        if row.get(check_field) != current_derivation:
            problems.append(
                f"{check_label}={row.get(check_field)!r} does not match "
                f"what the four per-rule decisions currently derive to "
                f"({current_derivation!r}) - never hand-set this field, "
                "it must equal derive_overall_decision(e4, e5, e6, e8)")

        expected_flag = needs_second_review_flag(e4, e5, e6, e8)
        # accept either a real bool or the CSV-friendly "True"/"False"
        # string form - review rows round-trip through csv.DictReader,
        # which only ever hands back strings
        actual_flag = row.get("second_review_required")
        actual_bool = actual_flag in (True, "True", "true", "1")
        if actual_bool != expected_flag:
            problems.append(
                f"second_review_required={actual_flag!r} does not match "
                f"whether any rule is actually needs_second_review "
                f"(expected {expected_flag}) - never hand-set this "
                "field, it must equal needs_second_review_flag(e4, e5, "
                "e6, e8)")

    # --- original vs final: never overwritten, only corrected --------------
    if corrected and not row.get("correction_reason"):
        problems.append("final_reviewed_decision differs from "
                        "original_manual_decision but correction_reason "
                        "is empty - every correction needs an explicit "
                        "reason on record")

    # --- the gate that keeps unresolved records out of any downstream use --
    if final == "include":
        for rule in RULES:
            d = row.get(f"{rule.lower()}_decision")
            if d not in ("include", "not_applicable"):
                problems.append(
                    f"final_reviewed_decision=include but {rule} is "
                    f"still {d!r} - an article cannot be marked "
                    "eligible while any applicable rule is unresolved")

    if problems:
        raise ValidationError(
            f"{prefix}{len(problems)} problem(s):\n  - " +
            "\n  - ".join(problems))
    return True


def is_eligible_for_downstream(row):
    """The ONLY function later pipeline stages (cleaning, deduplication,
    analysis) may use to decide whether a reviewed article counts.
    Anything not a fully-resolved, validated 'include' is kept out -
    there is deliberately no other path into the analysis corpus."""
    if row.get("final_reviewed_decision") != "include":
        return False
    try:
        validate_row(row, context=row.get("article_id", ""))
    except ValidationError:
        return False
    return True
