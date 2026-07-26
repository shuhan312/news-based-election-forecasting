"""Phase 6 / Step 1 - schema validation for LLM context extraction
records (no LLM is called anywhere in this module).

Two validation layers, both deterministic:

    1. structural   jsonschema Draft 2020-12 validation against the
                    versioned schema file llm_context/
                    llm_context_schema_v1.json - types, enums,
                    required fields, additionalProperties: false
                    (unknown fields are errors, not surprises).
    2. cross-field  research-integrity rules that JSON Schema cannot
                    express, from llm_context_validation_rules_v1.md:

        R1  evidence grounding: every evidence span must appear
            VERBATIM in the article body (or title when flagged
            from_title) - the span is the audit trail proving the
            claim came from the text, so a span that does not match
            is a fabrication and fails hard;
        R2  span offsets, when given, must slice the body to exactly
            the span text;
        R3  a low-confidence claim (< 0.5) requires the record to be
            review-routed (review_status flagged) - uncertainty is
            surfaced, never silently included;
        R4  an empty extraction (no entities AND no issues AND no
            stances) must carry extraction_status partial/failed/
            not_attempted plus an ambiguity note - "nothing found"
            must be an explicit statement, not an accident;
        R5  status consistency: extracted requires at least one
            populated section; not_attempted requires ALL sections
            empty.

Returns error-message lists rather than raising, so callers (tests
now, the Step 2+ extraction pipeline later) can log every problem at
once. Stage M compatibility is inherent: validation is per-record
against a versioned schema, so future articles validate identically
and processed records are never re-touched.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path("llm_context/llm_context_schema_v1.json")
SCHEMA_VERSION = "llm-context-v1.0-2026-07-26"

# record sections holding claim lists (each claim carries evidence)
CLAIM_SECTIONS = ("entities", "stances", "frames", "credit_blame",
                  "electoral_consequences")
LOW_CONFIDENCE = 0.5


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _iter_claims(record: dict):
    """Yield (section, claim) for every evidence-bearing claim."""
    for section in CLAIM_SECTIONS:
        for claim in record.get(section) or []:
            yield section, claim
    issues = record.get("issues") or {}
    if issues.get("primary_issue"):
        yield "issues", issues["primary_issue"]
    for claim in issues.get("secondary_issues") or []:
        yield "issues", claim
    rel = record.get("relevance") or {}
    if rel.get("evidence_span"):
        yield "relevance", rel


def validate_structure(record: dict) -> list[str]:
    """Layer 1: JSON Schema errors as sorted strings (deterministic
    output for identical input)."""
    validator = Draft202012Validator(load_schema())
    return sorted(f"{'/'.join(str(p) for p in e.absolute_path)}: "
                  f"{e.message}" for e in validator.iter_errors(record))


def validate_rules(record: dict, body_text: str,
                   title: str = "") -> list[str]:
    """Layer 2: cross-field research-integrity rules R1-R5."""
    errors: list[str] = []

    populated = 0
    for section, claim in _iter_claims(record):
        span = claim.get("evidence_span")
        if not isinstance(span, dict):
            continue                    # structural layer reports it
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

    core_empty = (not record.get("entities")
                  and not (record.get("issues") or {}).get("primary_issue")
                  and not record.get("stances"))
    if core_empty and record.get("extraction_status") == "extracted":
        errors.append("R4: no entities, no primary issue and no "
                      "stances, yet extraction_status is 'extracted' "
                      "- an empty result must be partial/failed with "
                      "an ambiguity note")
    if core_empty and record.get("extraction_status") in (
            "partial", "failed") and not record.get("ambiguity_notes"):
        errors.append("R4: empty core sections require an "
                      "ambiguity_notes entry explaining why")
    if record.get("extraction_status") == "not_attempted" and populated:
        errors.append("R5: not_attempted record carries extracted "
                      "claims")
    return sorted(errors)


def validate_record(record: dict, body_text: str,
                    title: str = "") -> list[str]:
    """Full validation: structure first (a structurally broken record
    is not worth rule-checking), then the cross-field rules."""
    errors = validate_structure(record)
    if errors:
        return errors
    return validate_rules(record, body_text, title)
