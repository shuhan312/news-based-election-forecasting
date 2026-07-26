"""Phase 6 / Step 6 - credit / blame attribution (pure logic; the
runner does the IO, no API call in this module).

Responsibility attribution is the classic mechanism linking coverage
to incumbent vote share, and it needs FOUR elements the earlier
layers do not carry together: who receives credit or blame (target),
who assigns it (source - the journalist's own narration is a
different signal from a quoted rival politician or an angry
resident), for what (the attributed outcome), and why (the
reasoning as the article gives it). Each attribution also links back
to the issue layer via an issues-v1.3 code and records the possible
electoral reading AS THE ARTICLE SUGGESTS IT - descriptive only;
consequence estimation is the next step's job and is excluded here.

Validation rules (C-series; deterministic, sorted output):

    C1  every evidence span must appear VERBATIM in the article body
        (or title when from_title) - the anti-hallucination gate;
    C2  any confidence < 0.5 forces review_status = flagged;
    C3  no duplicate attributions: (target_name, attribution_type,
        attributed_outcome) triples must be unique - the same blame
        for the same outcome counted twice would double-weight it in
        downstream aggregation. Separate praise and criticism of the
        same target are legitimately separate rows;
    C4  a non-'unclear' implication_direction requires the
        electoral_implication text - a directional political claim
        without its reading is unsupported;
    C5  an empty attribution set cannot claim extraction_status
        "extracted" and must carry an ambiguity note - "nobody is
        credited or blamed" is a stated finding;
    C6  not_attempted records must be empty.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path("llm_context/credit_blame_schema_v1.json")

CB_SCHEMA_VERSION = "credit-blame-v1.1-2026-07-27"
CB_PROMPT_VERSION = "credit-blame-prompt-v1.1-2026-07-27"
CB_RULES_VERSION = "credit-blame-rules-v1.0-2026-07-27"
LOW_CONFIDENCE = 0.5


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def validate_structure(record: dict) -> list[str]:
    validator = Draft202012Validator(load_schema())
    return sorted(f"{'/'.join(str(p) for p in e.absolute_path)}: "
                  f"{e.message}" for e in validator.iter_errors(record))


def validate_rules(record: dict, body: str, title: str = "") -> list[str]:
    errors: list[str] = []
    rows = record.get("attributions") or []

    # ---- C1 verbatim + C2 confidence routing ------------------------
    for row in rows:
        span = row.get("evidence_span")
        if isinstance(span, dict):
            haystack = title if span.get("from_title") else body
            text = span.get("text", "")
            if text and text not in haystack:
                errors.append(f"C1 {row.get('target_name', '?')}: "
                              f"evidence span not found verbatim: "
                              f"{text[:60]!r}")
        conf = row.get("confidence")
        if isinstance(conf, (int, float)) and conf < LOW_CONFIDENCE \
                and record.get("review_status") != "flagged":
            errors.append(f"C2 {row.get('target_name', '?')}: "
                          f"confidence {conf} below {LOW_CONFIDENCE} "
                          "but record not flagged")

    # ---- C3 no duplicate (target, type, outcome) triples ------------
    keys = [(r.get("target_name", "").strip().lower(),
             r.get("attribution_type"),
             r.get("attributed_outcome", "").strip().lower())
            for r in rows]
    dupes = sorted({k[0] for k in keys if keys.count(k) > 1})
    if dupes:
        errors.append(f"C3: duplicate attribution rows for {dupes}")

    # ---- C4 directional implication needs its reading ---------------
    for row in rows:
        if row.get("implication_direction") != "unclear" \
                and not row.get("electoral_implication"):
            errors.append(f"C4 {row.get('target_name', '?')}: "
                          f"direction "
                          f"{row.get('implication_direction')!r} "
                          "without electoral_implication text")

    # ---- C5 / C6 status consistency ---------------------------------
    if not rows:
        if record.get("extraction_status") == "extracted":
            errors.append("C5: no attributions yet status is "
                          "'extracted' - empty must be partial/failed "
                          "with a note")
        if record.get("extraction_status") in ("partial", "failed") \
                and not record.get("ambiguity_notes"):
            errors.append("C5: empty attribution set requires an "
                          "ambiguity note")
    if record.get("extraction_status") == "not_attempted" and rows:
        errors.append("C6: not_attempted record carries attributions")
    return sorted(errors)


def validate_cb_record(record: dict, body: str,
                       title: str = "") -> list[str]:
    errors = validate_structure(record)
    if errors:
        return errors
    return validate_rules(record, body, title)


def build_cb_prompt() -> str:
    """Focused system prompt. Byte-stable (no clocks) so the batch
    caches it and reruns render identically."""
    schema = SCHEMA_PATH.read_text().strip()
    return f"""You are a responsibility-attribution extraction system for an academic \
study of pre-election news coverage in Surrey, England. For each article, \
produce ONE JSON object conforming exactly to the JSON Schema below: one row \
per distinct credit or blame attribution the article carries. \
Prompt version: {CB_PROMPT_VERSION}.

Hard rules:
1. FOUR ELEMENTS PER ROW. Use target_type "candidate" for candidates in the \
studied Surrey elections and "politician" for other named individual \
politicians (ministers, party leaders, MPs). Who receives the credit/blame (target), who \
assigns it (source - the journalist's own narration vs a quoted politician, \
resident, organisation or public group are DIFFERENT signals; name the \
assigner when the article names them), WHAT outcome is being attributed, \
and WHY, per the article's own account.
2. EVIDENCE OR NOTHING. Every row's evidence_span.text must be copied \
CHARACTER-FOR-CHARACTER from the article body (or title, with from_title \
true). NEVER shorten a quote with "..." or any ellipsis, NEVER splice \
passages, NEVER reconstruct from memory; choose a shorter contiguous span \
instead. A validator string-matches every span and rejects inexact copies.
3. NO INVENTED RESPONSIBILITY. Record only attributions the article itself \
makes or reports. Never construct a causal chain the text does not state. \
Praise and criticism of the same target are separate rows; use "mixed" only \
when a SINGLE attribution carries both directions.
4. POLITICAL READING, NOT PREDICTION. affected_issue links the attribution \
to the issue taxonomy (issues-v1.3 codes; null if none fits). \
electoral_implication records the possible electoral reading AS THE ARTICLE \
SUGGESTS IT; implication_direction says whether it may damage or benefit \
the target. If the direction is anything but "unclear", the implication \
text is required. Do NOT predict election results and do NOT analyse voter \
switching - those are later steps.
5. DO NOT FORCE. An article attributing nothing gets an empty list, \
extraction_status "partial" and an ambiguity note.
6. CONFIDENCE IS HONEST. Confidence in [0,1] per row; if ANY is below 0.5, \
you MUST set review_status to "flagged".
7. Output ONLY the JSON object - no markdown fences, no commentary.

The JSON Schema (contract {CB_SCHEMA_VERSION}):

{schema}"""
