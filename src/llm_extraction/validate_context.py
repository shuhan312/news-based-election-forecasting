"""Phase 6 / Step 1 - schema validation for LLM context extraction
records (no LLM is called anywhere in this module).

Two validation layers, both deterministic:

    1. structural   jsonschema Draft 2020-12 validation against the
                    versioned schema file llm_context/
                    llm_context_schema_v1.json (v1.1 contract) -
                    types, enums, required fields,
                    additionalProperties: false.
    2. cross-field  research-integrity rules JSON Schema cannot
                    express, from llm_context_validation_rules_v1.md
                    as amended by llm_context_validation_rules_v1.1.md
                    (RULES_VERSION below tracks the enforced revision):

        R1  evidence grounding: every evidence span must appear
            VERBATIM in the article body (or title when flagged
            from_title) - a non-matching span is a fabricated quote
            and fails hard (the anti-hallucination gate);
        R2  span offsets, when given, must slice the source text to
            exactly the span text;
        R3  a claim with confidence < 0.5 requires review_status =
            flagged - uncertainty is surfaced, never silent;
        R4  an empty extraction (no entities, no primary issue, no
            party rows) must carry extraction_status partial/failed/
            not_attempted plus an ambiguity note;
        R5  status consistency: not_attempted requires zero claims;
        R6  Reform UK consistency: with reform_uk_present false, no
            positive Reform flag or score may be set; with any
            positive flag set, an evidence span is required - the
            specialised layer must never assert emergence without a
            quote;
        R7  leakage flags (poll/prediction/result) require an
            evidence span AND (rules v1.1) an explanation - a
            leakage-risk claim is a claim, and unsupported leakage
            classification is forbidden;
        R8  party_context rows are unique per party - one feature
            row per party, no duplicates for downstream joins;
        R9  (rules v1.1) the election_administration issue code is
            only valid under taxonomy issues-v1.2 - records stamped
            v1.1 predate the code and stay traceable as such.

Returns error-message lists rather than raising, so callers (tests
now, the Step 2+ extraction pipeline later) log every problem at
once. Stage M compatibility is inherent: validation is per-record
against a pinned schema version.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path("llm_context/llm_context_schema_v1.json")
SCHEMA_VERSION = "llm-context-v1.1-2026-07-26"
RULES_VERSION = "rules-v1.1-2026-07-26"   # Step 2.5: R7 upgraded, R9 added
TAXONOMY_CURRENT = "issues-v1.2"

LOW_CONFIDENCE = 0.5

# array sections whose items are evidence-bearing claims
ARRAY_CLAIM_SECTIONS = ("entities", "party_context",
                        "candidate_context", "council_accountability",
                        "electoral_consequences", "frames")

REFORM_POSITIVE_FLAGS = ("in_headline", "candidate_mentioned",
                         "candidate_quoted", "local_campaign_activity",
                         "gaining_support", "credible_challenger",
                         "switching_con_to_reform",
                         "switching_lab_to_reform",
                         "switching_ld_to_reform",
                         "protest_anti_incumbent_support",
                         "national_momentum")


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _iter_claims(record: dict):
    """Yield (section, claim_dict) for every evidence-bearing claim
    across all eleven layers."""
    for section in ARRAY_CLAIM_SECTIONS:
        for claim in record.get(section) or []:
            yield section, claim
    issues = record.get("issues") or {}
    if issues.get("primary_issue"):
        yield "issues", issues["primary_issue"]
    for claim in issues.get("secondary_issues") or []:
        yield "issues", claim
    for section in ("event_context", "reform_uk", "geographic",
                    "leakage"):
        obj = record.get(section)
        if isinstance(obj, dict) and obj.get("evidence_span"):
            yield section, obj


def validate_structure(record: dict) -> list[str]:
    """Layer 1: JSON Schema errors as sorted strings (deterministic
    output for identical input)."""
    validator = Draft202012Validator(load_schema())
    return sorted(f"{'/'.join(str(p) for p in e.absolute_path)}: "
                  f"{e.message}" for e in validator.iter_errors(record))


def validate_rules(record: dict, body_text: str,
                   title: str = "") -> list[str]:
    """Layer 2: cross-field research-integrity rules R1-R8."""
    errors: list[str] = []
    populated = 0

    for section, claim in _iter_claims(record):
        span = claim.get("evidence_span")
        if not isinstance(span, dict):
            continue
        populated += 1
        haystack = title if span.get("from_title") else body_text
        text = span.get("text", "")
        if text and text not in haystack:
            errors.append(f"R1 {section}: evidence span not found "
                          f"verbatim in the "
                          f"{'title' if span.get('from_title') else 'body'}"
                          f": {text[:60]!r}")
        if "char_start" in span and "char_end" in span and text:
            if haystack[span["char_start"]:span["char_end"]] != text:
                errors.append(f"R2 {section}: span offsets do not "
                              f"slice to the span text")
        conf = claim.get("confidence")
        if isinstance(conf, (int, float)) and conf < LOW_CONFIDENCE \
                and record.get("review_status") != "flagged":
            errors.append(f"R3 {section}: confidence {conf} below "
                          f"{LOW_CONFIDENCE} but record not "
                          f"review-routed (review_status != flagged)")

    # ---- R4/R5: emptiness must be explicit --------------------------
    core_empty = (not record.get("entities")
                  and not (record.get("issues") or {}).get("primary_issue")
                  and not record.get("party_context"))
    if core_empty and record.get("extraction_status") == "extracted":
        errors.append("R4: no entities, no primary issue and no party "
                      "context, yet extraction_status is 'extracted' "
                      "- an empty result must be partial/failed with "
                      "an ambiguity note")
    if core_empty and record.get("extraction_status") in (
            "partial", "failed") and not record.get("ambiguity_notes"):
        errors.append("R4: empty core sections require an "
                      "ambiguity_notes entry explaining why")
    if record.get("extraction_status") == "not_attempted" and populated:
        errors.append("R5: not_attempted record carries extracted "
                      "claims")

    # ---- R6: Reform UK layer consistency ----------------------------
    reform = record.get("reform_uk") or {}
    positives = [f for f in REFORM_POSITIVE_FLAGS if reform.get(f)]
    if not reform.get("reform_uk_present"):
        if positives:
            errors.append(f"R6 reform_uk: reform_uk_present is false "
                          f"but positive flags set: {sorted(positives)}")
        for score in ("credibility_score", "momentum_score"):
            if reform.get(score) is not None and score in reform:
                errors.append(f"R6 reform_uk: {score} set while "
                              "reform_uk_present is false")
    elif positives and not reform.get("evidence_span"):
        errors.append("R6 reform_uk: positive flags require an "
                      "evidence span - emergence is never asserted "
                      "without a quote")

    # ---- R7 (v1.1): leakage flags need evidence AND explanation -----
    leak = record.get("leakage") or {}
    leak_flags = [f for f in ("contains_poll", "contains_prediction",
                              "contains_election_result")
                  if leak.get(f)]
    if leak_flags and not leak.get("evidence_span"):
        errors.append(f"R7 leakage: {sorted(leak_flags)} set without "
                      "an evidence span")
    if leak_flags and not leak.get("explanation"):
        errors.append(f"R7 leakage: {sorted(leak_flags)} set without "
                      "an explanation")

    # ---- R9 (v1.1): new taxonomy code gated by taxonomy version -----
    issues = record.get("issues") or {}
    codes = [c.get("issue_code") for c in
             ([issues.get("primary_issue")] if issues.get("primary_issue")
              else []) + (issues.get("secondary_issues") or [])]
    if "election_administration" in codes \
            and issues.get("taxonomy_version") != "issues-v1.2":
        errors.append("R9 issues: election_administration requires "
                      "taxonomy_version issues-v1.2")

    # ---- R8: one context row per party ------------------------------
    parties = [p.get("party") for p in record.get("party_context") or []]
    dupes = sorted({p for p in parties if parties.count(p) > 1})
    if dupes:
        errors.append(f"R8 party_context: duplicate party rows: "
                      f"{dupes}")

    return sorted(errors)


def validate_record(record: dict, body_text: str,
                    title: str = "") -> list[str]:
    """Full validation: structure first (a structurally broken record
    is not worth rule-checking), then the cross-field rules."""
    errors = validate_structure(record)
    if errors:
        return errors
    return validate_rules(record, body_text, title)
