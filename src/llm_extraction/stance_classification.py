"""Phase 6 / Step 4 - entity stance / sentiment analysis (pure
logic; the runner does the IO, no API call in this module).

A focused layer answering one question per entity: HOW does the
article represent this party / candidate / council / organisation?
Four-value stance (never a single article-level sentiment number),
the narration-vs-quotation origin of that stance, and six
political-context perceptions (competence, integrity, public
support, challenger status, support trajectory, voter switching) -
each row grounded in a verbatim quote with an explanation and a
confidence score. Framing, blame/credit and electoral consequences
are OUT of scope here by specification and the prompt says so
explicitly, to stop scope creep at the source.

Validation rules (T-series; deterministic, sorted output):

    T1  every evidence span must appear VERBATIM in the article body
        (or title when from_title) - the anti-hallucination gate;
    T2  any confidence < 0.5 forces review_status = flagged;
    T3  one row per entity: (target_name, target_type) pairs must be
        unique - duplicate rows would double-count representation in
        downstream aggregation;
    T4  a voter_switching_mentioned flag requires switching_detail -
        a switching claim without the from/to reading is unusable;
    T5  an empty stance set cannot claim extraction_status
        "extracted" and must carry an ambiguity note - "no entity is
        taken a position on" is a stated finding;
    T6  not_attempted records must be empty.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path("llm_context/stance_classification_schema_v1.json")

STANCE_SCHEMA_VERSION = "stance-cls-v1.0-2026-07-27"
STANCE_PROMPT_VERSION = "stance-cls-prompt-v1.0-2026-07-27"
STANCE_RULES_VERSION = "stance-cls-rules-v1.0-2026-07-27"
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
    rows = record.get("entity_stances") or []

    # ---- T1 verbatim + T2 confidence routing ------------------------
    for row in rows:
        span = row.get("evidence_span")
        if isinstance(span, dict):
            haystack = title if span.get("from_title") else body
            text = span.get("text", "")
            if text and text not in haystack:
                errors.append(f"T1 {row.get('target_name', '?')}: "
                              f"evidence span not found verbatim: "
                              f"{text[:60]!r}")
        conf = row.get("confidence")
        if isinstance(conf, (int, float)) and conf < LOW_CONFIDENCE \
                and record.get("review_status") != "flagged":
            errors.append(f"T2 {row.get('target_name', '?')}: "
                          f"confidence {conf} below {LOW_CONFIDENCE} "
                          "but record not flagged")

    # ---- T3 one row per entity --------------------------------------
    keys = [(r.get("target_name", "").strip().lower(),
             r.get("target_type")) for r in rows]
    dupes = sorted({k[0] for k in keys if keys.count(k) > 1})
    if dupes:
        errors.append(f"T3: duplicate entity rows for {dupes}")

    # ---- T4 switching claims need the from/to detail ----------------
    for row in rows:
        if row.get("voter_switching_mentioned") \
                and not row.get("switching_detail"):
            errors.append(f"T4 {row.get('target_name', '?')}: "
                          "voter_switching_mentioned without "
                          "switching_detail")

    # ---- T5 / T6 status consistency ---------------------------------
    if not rows:
        if record.get("extraction_status") == "extracted":
            errors.append("T5: no entity stances yet status is "
                          "'extracted' - empty must be partial/failed "
                          "with a note")
        if record.get("extraction_status") in ("partial", "failed") \
                and not record.get("ambiguity_notes"):
            errors.append("T5: empty stance set requires an "
                          "ambiguity note")
    if record.get("extraction_status") == "not_attempted" and rows:
        errors.append("T6: not_attempted record carries stance rows")
    return sorted(errors)


def validate_stance_record(record: dict, body: str,
                           title: str = "") -> list[str]:
    errors = validate_structure(record)
    if errors:
        return errors
    return validate_rules(record, body, title)


def build_stance_prompt() -> str:
    """Focused system prompt. Byte-stable (no clocks) so the batch
    caches it and reruns render identically."""
    schema = SCHEMA_PATH.read_text().strip()
    return f"""You are a political-stance extraction system for an academic study of \
pre-election news coverage in Surrey, England. For each article, produce ONE \
JSON object conforming exactly to the JSON Schema below: one row per political \
entity (party, candidate, council, organisation) that the article represents \
in any evaluative way. Prompt version: {STANCE_PROMPT_VERSION}.

Hard rules:
1. STANCE IS ABOUT REPRESENTATION. Judge how THE ARTICLE presents the entity \
(positive / neutral / negative / mixed) - never the entity's own opinions, \
and never one overall article sentiment. An article can praise one party and \
criticise another; that is two rows.
2. NAME THE ORIGIN. For every row, say whether the stance comes from the \
journalist's own narration, from direct quotations of other actors, or both. \
Use not_applicable only for purely neutral mentions.
3. EVIDENCE OR NOTHING. Every row's evidence_span.text must be copied \
CHARACTER-FOR-CHARACTER from the article body (or title, with from_title \
true). NEVER shorten a quote with "..." or any ellipsis, NEVER splice \
passages, NEVER reconstruct from memory; choose a shorter contiguous span \
instead. A validator string-matches every span and rejects inexact copies.
4. DO NOT INFER. The six perception fields (competence, integrity, public \
support, challenger, trajectory, switching) default to not_addressed / \
not_indicated / false. Fill them ONLY when the article itself addresses the \
dimension. If voter switching is mentioned, switching_detail must say which \
voters and between which parties, per the article.
5. ONE ROW PER ENTITY. No duplicate (name, type) rows; an entity mentioned \
without any evaluative representation gets NO row.
6. NO article with zero rows may claim status "extracted" - use "partial" \
plus an ambiguity note ("no entity is evaluatively represented").
7. OUT OF SCOPE - do not produce: framing categories, blame or credit \
attribution, electoral consequence estimates. Those are later steps.
8. CONFIDENCE IS HONEST. Confidence in [0,1] per row; if ANY row is below \
0.5, you MUST set review_status to "flagged".
9. Output ONLY the JSON object - no markdown fences, no commentary.

The JSON Schema (contract {STANCE_SCHEMA_VERSION}):

{schema}"""
