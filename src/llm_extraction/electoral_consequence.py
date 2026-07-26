"""Phase 6 / Step 7 - expected electoral consequence extraction
(pure logic; the runner does the IO, no API call in this module).

The last extraction layer: what potential electoral advantages or
disadvantages the reported context MAY create - the mechanisms
linking news to voter behaviour that the research design wants to
test. The hard line this layer walks: consequences are the
ARTICLE'S implications, never our predictions. That line is
enforced three ways:

    structurally  the schema has no winner, vote-share or outcome
                  field - direct prediction is unrepresentable;
    by vocabulary every direction/signal value is prefixed or
                  phrased as potential/suggested;
    by prompt     rule 1 states the distinction and forbids crossing
                  it.

Validation rules (E-series; deterministic, sorted output):

    E1  every evidence span must appear VERBATIM in the article body
        (or title when from_title) - the anti-hallucination gate;
    E2  any confidence < 0.5 forces review_status = flagged;
    E3  no duplicate consequences: (actor, direction, mechanism,
        signal) tuples must be unique - the same signal recorded
        twice would double-weight it downstream. Rows sharing actor,
        direction and mechanism but carrying DIFFERENT signals are
        legitimately distinct (rules v1.1 refinement: the pilot
        showed the v1.0 triple key wrongly rejected such rows);
    E4  Reform UK consistency (the R6 pattern): applicable=false
        forbids any positive flag or non-empty list; any positive
        content requires an evidence span;
    E5  an empty consequence set cannot claim extraction_status
        "extracted" and must carry an ambiguity note - "no electoral
        implication" is a stated finding;
    E6  not_attempted records must be empty.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path("llm_context/electoral_consequence_schema_v1.json")

EC_SCHEMA_VERSION = "elect-consq-v1.0-2026-07-27"
EC_PROMPT_VERSION = "elect-consq-prompt-v1.0-2026-07-27"
EC_RULES_VERSION = "elect-consq-rules-v1.1-2026-07-27"
LOW_CONFIDENCE = 0.5

REFORM_POSITIVE_FLAGS = ("growth_suggested", "credible_challenger")
REFORM_LIST_FIELDS = ("established_support_affected",
                      "switching_directions", "signal_nature")


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def validate_structure(record: dict) -> list[str]:
    validator = Draft202012Validator(load_schema())
    return sorted(f"{'/'.join(str(p) for p in e.absolute_path)}: "
                  f"{e.message}" for e in validator.iter_errors(record))


def validate_rules(record: dict, body: str, title: str = "") -> list[str]:
    errors: list[str] = []
    rows = record.get("consequences") or []

    # ---- E1 verbatim + E2 confidence routing ------------------------
    spans = [(r.get("affected_actor_name", "?"), r.get("evidence_span"),
              r.get("confidence")) for r in rows]
    reform = record.get("reform_uk") or {}
    if reform.get("evidence_span"):
        spans.append(("reform_uk", reform["evidence_span"],
                      reform.get("confidence")))
    for name, span, conf in spans:
        if isinstance(span, dict):
            haystack = title if span.get("from_title") else body
            text = span.get("text", "")
            if text and text not in haystack:
                errors.append(f"E1 {name}: evidence span not found "
                              f"verbatim: {text[:60]!r}")
        if isinstance(conf, (int, float)) and conf < LOW_CONFIDENCE \
                and record.get("review_status") != "flagged":
            errors.append(f"E2 {name}: confidence {conf} below "
                          f"{LOW_CONFIDENCE} but record not flagged")

    # ---- E3 no duplicate (actor, direction, mechanism) --------------
    keys = [(r.get("affected_actor_name", "").strip().lower(),
             r.get("direction"), r.get("impact_mechanism"),
             r.get("electoral_signal"))
            for r in rows]
    dupes = sorted({k[0] for k in keys if keys.count(k) > 1})
    if dupes:
        errors.append(f"E3: duplicate consequence rows for {dupes}")

    # ---- E4 Reform UK consistency ------------------------------------
    positives = [f for f in REFORM_POSITIVE_FLAGS if reform.get(f)]
    filled = [f for f in REFORM_LIST_FIELDS if reform.get(f)]
    if not reform.get("applicable"):
        if positives or filled:
            errors.append(f"E4 reform_uk: applicable is false but "
                          f"content set: {sorted(positives + filled)}")
    elif (positives or filled) and not reform.get("evidence_span"):
        errors.append("E4 reform_uk: positive content requires an "
                      "evidence span")

    # ---- E5 / E6 status consistency ---------------------------------
    if not rows:
        if record.get("extraction_status") == "extracted":
            errors.append("E5: no consequences yet status is "
                          "'extracted' - empty must be partial/failed "
                          "with a note")
        if record.get("extraction_status") in ("partial", "failed") \
                and not record.get("ambiguity_notes"):
            errors.append("E5: empty consequence set requires an "
                          "ambiguity note")
    if record.get("extraction_status") == "not_attempted" and rows:
        errors.append("E6: not_attempted record carries consequences")
    return sorted(errors)


def validate_ec_record(record: dict, body: str,
                       title: str = "") -> list[str]:
    errors = validate_structure(record)
    if errors:
        return errors
    return validate_rules(record, body, title)


def build_ec_prompt() -> str:
    """Focused system prompt. Byte-stable (no clocks) so the batch
    caches it and reruns render identically."""
    schema = SCHEMA_PATH.read_text().strip()
    return f"""You are an electoral-consequence extraction system for an academic study \
of pre-election news coverage in Surrey, England. For each article, produce \
ONE JSON object conforming exactly to the JSON Schema below: the POTENTIAL \
electoral implications the article's content may carry. \
Prompt version: {EC_PROMPT_VERSION}.

Hard rules:
1. IMPLICATIONS, NEVER PREDICTIONS. You record what the article's content \
MAY mean for electoral behaviour, through which mechanism - you never state \
who will win, estimate vote shares, or assert that any outcome WILL happen. \
The schema has no field for outcomes; do not smuggle predictions into free \
text either.
2. MECHANISM WITH REASONING. Every consequence names its impact mechanism \
from the listed vocabulary and explains in mechanism_reasoning how the \
article's content produces it. No mechanism without textual basis; use \
"other" only when the reasoning names a real mechanism outside the list.
3. EVIDENCE OR NOTHING. Every row's evidence_span.text must be copied \
CHARACTER-FOR-CHARACTER from the article body (or title, with from_title \
true). NEVER shorten a quote with "..." or any ellipsis, NEVER splice \
passages, NEVER reconstruct from memory; choose a shorter contiguous span \
instead. A validator string-matches every span and rejects inexact copies.
4. VOTER GROUPS ONLY WITH BASIS. List possible affected groups only when \
the article gives grounds; an empty list is the honest default.
5. REFORM UK ADDENDUM. If the article materially concerns Reform UK, set \
reform_uk.applicable true and fill the addendum from the text: growth, \
challenger credibility, which established parties may be affected, \
switching directions (Con/Lab/LD to Reform), and whether the signal is \
national momentum, local campaign strength, protest voting or \
anti-incumbent sentiment. Coverage is NEVER assumed to create votes - you \
record signals, with evidence. If not applicable, everything stays \
false/empty/null.
6. DO NOT FORCE. An article with no electoral implication gets an empty \
list, extraction_status "partial" and an ambiguity note.
7. CONFIDENCE IS HONEST. Confidence in [0,1] per row; if ANY is below 0.5, \
you MUST set review_status to "flagged".
8. Output ONLY the JSON object - no markdown fences, no commentary.

The JSON Schema (contract {EC_SCHEMA_VERSION}):

{schema}"""
