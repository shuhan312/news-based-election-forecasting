"""Phase 6 / Step 3 - issue / topic classification (pure logic; the
runner does the IO, no API call in this module).

A focused layer, not a re-run of the full 11-layer contract: for
every canonical article, WHAT political issue it discusses (primary
+ up to five secondary, against the approved issues-v1.2 taxonomy),
each assignment carrying a verbatim quote, an explanation and a
confidence score - plus the political-relevance determination
(election-competition link, affected actors, possible influence on
voter perceptions). Stance, framing, blame/credit and consequences
are OUT of scope here by specification.

Validation rules (S-series; deterministic, sorted output):

    S1  every evidence span must appear VERBATIM in the article body
        (or title when from_title) - the anti-hallucination gate,
        identical in spirit to the pilot's R1;
    S2  any confidence < 0.5 forces review_status = flagged;
    S3  primary/secondary separation: the primary code must not
        reappear in secondary_issues, and secondary codes must be
        unique - one assignment per code per article;
    S4  political-relevance claims need support: if either boolean
        is true, an evidence span is required - no unsupported
        interpretation;
    S5  an empty classification (no primary, no secondary) cannot
        claim extraction_status "extracted" and must carry an
        ambiguity note - "no political issue" is a stated finding;
    S6  not_attempted records must be empty;
    S7  the v1.3 national codes (national_politics,
        national_economy) are only valid when the record stamps
        taxonomy issues-v1.3 - pilot records stamped v1.2 predate
        them and stay traceable as such (same discipline as the
        main schema's R9).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path("llm_context/issue_classification_schema_v1.json")
# v1.3: national codes added after the pilot showed national-arm
# articles were uncodable under the local-oriented taxonomy (see
# llm_context/issue_layer_decisions_v1.md; supervisor ratification
# pending, adopted provisionally)
TAXONOMY_PATH = Path("llm_context/issue_taxonomy_v1.3.json")

CLS_SCHEMA_VERSION = "issue-cls-v1.1-2026-07-27"
CLS_PROMPT_VERSION = "issue-cls-prompt-v1.1-2026-07-27"
CLS_RULES_VERSION = "issue-cls-rules-v1.1-2026-07-27"
TAXONOMY_CURRENT = "issues-v1.3"
NATIONAL_CODES = {"national_politics", "national_economy"}
LOW_CONFIDENCE = 0.5


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _issues(record: dict) -> list[dict]:
    iss = record.get("issues") or {}
    return ([iss["primary_issue"]] if iss.get("primary_issue")
            else []) + (iss.get("secondary_issues") or [])


def validate_structure(record: dict) -> list[str]:
    validator = Draft202012Validator(load_schema())
    return sorted(f"{'/'.join(str(p) for p in e.absolute_path)}: "
                  f"{e.message}" for e in validator.iter_errors(record))


def validate_rules(record: dict, body: str, title: str = "") -> list[str]:
    errors: list[str] = []
    iss = record.get("issues") or {}
    claims = _issues(record)

    # ---- S1 verbatim + S2 confidence routing ------------------------
    rel = record.get("political_relevance") or {}
    spans = [("issues", c.get("evidence_span"), c.get("confidence"))
             for c in claims]
    if rel.get("evidence_span"):
        spans.append(("political_relevance", rel["evidence_span"], None))
    for section, span, conf in spans:
        if not isinstance(span, dict):
            continue
        haystack = title if span.get("from_title") else body
        text = span.get("text", "")
        if text and text not in haystack:
            errors.append(f"S1 {section}: evidence span not found "
                          f"verbatim: {text[:60]!r}")
        if isinstance(conf, (int, float)) and conf < LOW_CONFIDENCE \
                and record.get("review_status") != "flagged":
            errors.append(f"S2 {section}: confidence {conf} below "
                          f"{LOW_CONFIDENCE} but record not flagged")

    # ---- S3 primary/secondary separation ----------------------------
    primary = (iss.get("primary_issue") or {}).get("issue_code")
    secondary = [c.get("issue_code")
                 for c in iss.get("secondary_issues") or []]
    if primary and primary in secondary:
        errors.append(f"S3 issues: primary code {primary!r} repeated "
                      "in secondary_issues")
    dupes = sorted({c for c in secondary if secondary.count(c) > 1})
    if dupes:
        errors.append(f"S3 issues: duplicate secondary codes {dupes}")

    # ---- S4 relevance claims need support ---------------------------
    if (rel.get("election_competition_related")
            or rel.get("may_influence_voter_perceptions")) \
            and not rel.get("evidence_span"):
        errors.append("S4 political_relevance: relevance asserted "
                      "without an evidence span")

    # ---- S5 / S6 status consistency ---------------------------------
    if not claims:
        if record.get("extraction_status") == "extracted":
            errors.append("S5: no issues assigned yet status is "
                          "'extracted' - empty must be partial/failed "
                          "with a note")
        if record.get("extraction_status") in ("partial", "failed") \
                and not record.get("ambiguity_notes"):
            errors.append("S5: empty classification requires an "
                          "ambiguity note")
    if record.get("extraction_status") == "not_attempted" and claims:
        errors.append("S6: not_attempted record carries issue claims")

    # ---- S7 national codes gated by taxonomy version ----------------
    codes = {c.get("issue_code") for c in claims}
    used_national = sorted(codes & NATIONAL_CODES)
    if used_national and iss.get("taxonomy_version") != "issues-v1.3":
        errors.append(f"S7 issues: {used_national} require "
                      "taxonomy_version issues-v1.3")
    return sorted(errors)


def validate_issue_record(record: dict, body: str,
                          title: str = "") -> list[str]:
    errors = validate_structure(record)
    if errors:
        return errors
    return validate_rules(record, body, title)


def build_issue_prompt() -> str:
    """Focused system prompt - taxonomy definitions from the approved
    v1.2 artifact plus the compact schema. Byte-stable (no clocks),
    so the batch caches it and reruns render identically."""
    taxonomy = json.loads(TAXONOMY_PATH.read_text())
    tax_lines = "\n".join(f"- {code}: {desc}"
                          for code, desc in taxonomy["codes"].items())
    schema = SCHEMA_PATH.read_text().strip()
    return f"""You are an issue-classification system for an academic study of \
pre-election news coverage in Surrey, England. For each article, produce ONE \
JSON object conforming exactly to the JSON Schema below: the article's PRIMARY \
political issue, up to five SECONDARY issues, and the political-relevance \
determination. Prompt version: {CLS_PROMPT_VERSION}.

The taxonomy (issues-v1.3; set taxonomy_version to "issues-v1.3") - use ONLY \
these codes, never invent one. The two national_* codes are for NATIONAL \
politics/economy coverage that fits no local code - prefer a specific code \
(healthcare, immigration, scandal...) whenever one applies:
{tax_lines}

Hard rules:
1. EVIDENCE OR NOTHING. Every issue assignment and any asserted political \
relevance must carry evidence_span.text copied CHARACTER-FOR-CHARACTER from \
the article body (or title, with from_title true). NEVER shorten a quote \
with "..." or any ellipsis, NEVER splice passages, NEVER reconstruct from \
memory; choose a shorter contiguous span instead. A validator string-matches \
every span and rejects anything that is not an exact copy.
2. EXPLAIN EVERY ASSIGNMENT. Each issue carries a one-or-two sentence \
explanation of why the code applies.
3. DO NOT GUESS. An article with no political issue gets primary_issue null, \
empty secondary_issues, extraction_status "partial" and an ambiguity note. \
Never force a code.
4. PRIMARY vs SECONDARY. Exactly one main issue (or null); secondary issues \
are genuinely present additional topics, most relevant first, no repeats of \
the primary code, maximum five.
5. RELEVANCE NEEDS PROOF. Set election_competition_related and \
may_influence_voter_perceptions honestly; if either is true, provide the \
supporting evidence_span. List affected_actors only when the article names \
them. Do NOT predict election outcomes.
6. CONFIDENCE IS HONEST. Confidence in [0,1] per assignment; if any is \
below 0.5, set review_status to "flagged".
7. Output ONLY the JSON object - no markdown fences, no commentary.

The JSON Schema (contract {CLS_SCHEMA_VERSION}):

{schema}"""
