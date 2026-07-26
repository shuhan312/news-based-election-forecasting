"""Phase 6 / Step 5 - narrative framing detection (pure logic; the
runner does the IO, no API call in this module).

A focused layer answering: WHAT STORY does the article tell about
political events and actors - the interpretive structure, not the
sentiment (Step 4's job) and not the topic (Step 3's job). "Council
criticised over potholes" and "residents left behind by a failing
council" share issue and stance but frame differently: the first is
accountability, the second governance failure with a community-impact
overlay - and framing differences between local and national outlets
are one of the study's comparison dimensions.

Per frame the record carries the specification's context: affected
entity, how the narrative is constructed, the political mechanism AS
THE ARTICLE SUGGESTS IT (descriptive - consequence estimation is a
later step), who the frame benefits or damages, a verbatim quote and
a confidence score.

Validation rules (F-series; deterministic, sorted output):

    F1  every evidence span must appear VERBATIM in the article body
        (or title when from_title) - the anti-hallucination gate;
    F2  any confidence < 0.5 forces review_status = flagged;
    F3  the primary frame's category must not reappear among the
        secondary frames, and secondary categories must be unique -
        one narrative, one row;
    F4  frame_category "other" requires frame_other_label (a named
        frame, not a shrug) - the specification allows other "only
        if justified";
    F5  an empty framing record (no primary, no secondaries) cannot
        claim extraction_status "extracted" and must carry an
        ambiguity note;
    F6  not_attempted records must be empty.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path("llm_context/framing_detection_schema_v1.json")

FRAME_SCHEMA_VERSION = "framing-v1.0-2026-07-27"
FRAME_PROMPT_VERSION = "framing-prompt-v1.0-2026-07-27"
FRAME_RULES_VERSION = "framing-rules-v1.0-2026-07-27"
LOW_CONFIDENCE = 0.5


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _frames(record: dict) -> list[dict]:
    return ([record["primary_frame"]] if record.get("primary_frame")
            else []) + (record.get("secondary_frames") or [])


def validate_structure(record: dict) -> list[str]:
    validator = Draft202012Validator(load_schema())
    return sorted(f"{'/'.join(str(p) for p in e.absolute_path)}: "
                  f"{e.message}" for e in validator.iter_errors(record))


def validate_rules(record: dict, body: str, title: str = "") -> list[str]:
    errors: list[str] = []
    frames = _frames(record)

    # ---- F1 verbatim + F2 confidence routing ------------------------
    for f in frames:
        span = f.get("evidence_span")
        if isinstance(span, dict):
            haystack = title if span.get("from_title") else body
            text = span.get("text", "")
            if text and text not in haystack:
                errors.append(f"F1 {f.get('frame_category', '?')}: "
                              f"evidence span not found verbatim: "
                              f"{text[:60]!r}")
        conf = f.get("confidence")
        if isinstance(conf, (int, float)) and conf < LOW_CONFIDENCE \
                and record.get("review_status") != "flagged":
            errors.append(f"F2 {f.get('frame_category', '?')}: "
                          f"confidence {conf} below {LOW_CONFIDENCE} "
                          "but record not flagged")

    # ---- F3 primary/secondary separation ----------------------------
    primary = (record.get("primary_frame") or {}).get("frame_category")
    secondary = [f.get("frame_category")
                 for f in record.get("secondary_frames") or []]
    if primary and primary in secondary:
        errors.append(f"F3: primary frame {primary!r} repeated in "
                      "secondary_frames")
    dupes = sorted({c for c in secondary if secondary.count(c) > 1})
    if dupes:
        errors.append(f"F3: duplicate secondary frames {dupes}")

    # ---- F4 'other' must be a named frame ---------------------------
    for f in frames:
        if f.get("frame_category") == "other" \
                and not f.get("frame_other_label"):
            errors.append("F4: frame 'other' without frame_other_label")

    # ---- F5 / F6 status consistency ---------------------------------
    if not frames:
        if record.get("extraction_status") == "extracted":
            errors.append("F5: no frames yet status is 'extracted' - "
                          "empty must be partial/failed with a note")
        if record.get("extraction_status") in ("partial", "failed") \
                and not record.get("ambiguity_notes"):
            errors.append("F5: empty framing requires an ambiguity "
                          "note")
    if record.get("extraction_status") == "not_attempted" and frames:
        errors.append("F6: not_attempted record carries frames")
    return sorted(errors)


def validate_framing_record(record: dict, body: str,
                            title: str = "") -> list[str]:
    errors = validate_structure(record)
    if errors:
        return errors
    return validate_rules(record, body, title)


def build_framing_prompt() -> str:
    """Focused system prompt. Byte-stable (no clocks) so the batch
    caches it and reruns render identically."""
    schema = SCHEMA_PATH.read_text().strip()
    return f"""You are a narrative-framing detection system for an academic study of \
pre-election news coverage in Surrey, England. For each article, produce ONE \
JSON object conforming exactly to the JSON Schema below: the article's \
DOMINANT narrative frame plus up to four secondary frames. \
Prompt version: {FRAME_PROMPT_VERSION}.

Framing is the INTERPRETIVE STRUCTURE of the piece - what kind of story it \
tells - not its topic and not its sentiment. "Council criticised over \
potholes" (accountability) and "residents left behind by a failing council" \
(governance_failure + local_community_impact) share topic and negativity but \
frame differently.

Hard rules:
1. USE ONLY THE 16 LISTED FRAME CATEGORIES. Never invent one. Use "other" \
only when a real, nameable frame fits no category - then frame_other_label \
must name it and the explanation must justify it.
2. EVIDENCE OR NOTHING. Every frame's evidence_span.text must be copied \
CHARACTER-FOR-CHARACTER from the article body (or title, with from_title \
true). NEVER shorten a quote with "..." or any ellipsis, NEVER splice \
passages, NEVER reconstruct from memory; choose a shorter contiguous span \
instead. A validator string-matches every span and rejects inexact copies.
3. FRAME CONTEXT, NOT CONSEQUENCES. For each frame give the affected \
entity, how the narrative is constructed, and the political mechanism AS THE \
ARTICLE SUGGESTS IT. Fill benefits/damages only when the article itself \
supports naming a favoured or harmed party/candidate; otherwise null. Do \
NOT estimate electoral outcomes and do NOT attribute blame or credit - \
those are later steps.
4. DO NOT FORCE. An article with no political framing gets primary_frame \
null, empty secondary_frames, extraction_status "partial" and an ambiguity \
note. One dominant frame only; secondaries must be genuinely present, most \
salient first, no repeats, maximum four.
5. CONFIDENCE IS HONEST. Confidence in [0,1] per frame; if ANY is below \
0.5, you MUST set review_status to "flagged".
6. Output ONLY the JSON object - no markdown fences, no commentary.

The JSON Schema (contract {FRAME_SCHEMA_VERSION}):

{schema}"""
