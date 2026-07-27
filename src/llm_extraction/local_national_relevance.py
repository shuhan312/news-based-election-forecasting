"""Phase 6 / Step 8 - local / national relevance extraction (pure
logic; the runner does the IO, no API call in this module).

The axis the whole comparison rests on: is this article local
Surrey context, national political context, or both? Five-level
geographic scope, named geographic entities (wards, divisions,
towns, boroughs), the four specification mention flags, an issue
scope, DUAL 0-1 relevance scores with explicit reasoning (an
article can be highly relevant on both axes - two scores, not one
slider), an electoral interpretation, and the Reform UK
national-to-local addendum that serves the study's key question:
does national momentum convert into local ward-level signals?

Validation rules (G-series; deterministic, sorted output):

    G1  the scope-classification evidence span (and the Reform
        addendum's, when present) must appear VERBATIM in the
        article - the anti-hallucination gate;
    G2  any confidence < 0.5 forces review_status = flagged;
    G3  flag/entity coherence: ward_mentioned requires a named ward
        or division (and vice versa) - a flag without its entity is
        an unsupported geographic assumption;
    G4  scope/score coherence: ward_specific_local requires
        local_score > national_score; national requires
        national_score > local_score; mixed requires both scores
        >= 0.3 - the labels and the sliders must tell one story;
    G5  Reform UK consistency (the R6 pattern): applicable=false
        forbids any positive flag; positive content requires an
        evidence span. connects_national_to_local additionally
        requires BOTH national_momentum and local_surrey_activity -
        an article cannot connect what it does not carry;
    G6  not_attempted records carry no scope judgement.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(
    "llm_context/local_national_relevance_schema_v1.json")

LN_SCHEMA_VERSION = "loc-nat-v1.0-2026-07-27"
LN_PROMPT_VERSION = "loc-nat-prompt-v1.0-2026-07-27"
LN_RULES_VERSION = "loc-nat-rules-v1.0-2026-07-27"
LOW_CONFIDENCE = 0.5

REFORM_FLAGS = ("national_momentum", "local_surrey_activity",
                "connects_national_to_local",
                "ward_level_conversion_signal")


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def validate_structure(record: dict) -> list[str]:
    validator = Draft202012Validator(load_schema())
    return sorted(f"{'/'.join(str(p) for p in e.absolute_path)}: "
                  f"{e.message}" for e in validator.iter_errors(record))


def validate_rules(record: dict, body: str, title: str = "") -> list[str]:
    errors: list[str] = []

    # ---- G1 verbatim + G2 confidence routing ------------------------
    reform = record.get("reform_uk") or {}
    spans = [("scope", record.get("evidence_span"),
              record.get("confidence"))]
    if reform.get("evidence_span"):
        spans.append(("reform_uk", reform["evidence_span"],
                      reform.get("confidence")))
    for name, span, conf in spans:
        if isinstance(span, dict):
            haystack = title if span.get("from_title") else body
            text = span.get("text", "")
            if text and text not in haystack:
                errors.append(f"G1 {name}: evidence span not found "
                              f"verbatim: {text[:60]!r}")
        if isinstance(conf, (int, float)) and conf < LOW_CONFIDENCE \
                and record.get("review_status") != "flagged":
            errors.append(f"G2 {name}: confidence {conf} below "
                          f"{LOW_CONFIDENCE} but record not flagged")

    # ---- G3 flag/entity coherence -----------------------------------
    ents = record.get("geographic_entities") or {}
    flags = record.get("mention_flags") or {}
    has_ward = bool(ents.get("wards") or ents.get("divisions"))
    if flags.get("ward_mentioned") and not has_ward:
        errors.append("G3: ward_mentioned is true but no ward or "
                      "division is named")
    if has_ward and not flags.get("ward_mentioned"):
        errors.append("G3: wards/divisions named but ward_mentioned "
                      "is false")

    # ---- G4 scope/score coherence -----------------------------------
    scope = record.get("geographic_scope")
    rel = record.get("relevance") or {}
    ls, ns = rel.get("local_score"), rel.get("national_score")
    if isinstance(ls, (int, float)) and isinstance(ns, (int, float)):
        if scope == "ward_specific_local" and not ls > ns:
            errors.append("G4: ward_specific_local requires "
                          "local_score > national_score")
        if scope == "national" and not ns > ls:
            errors.append("G4: national scope requires "
                          "national_score > local_score")
        if scope == "mixed_national_local" and (ls < 0.3 or ns < 0.3):
            errors.append("G4: mixed scope requires both scores "
                          ">= 0.3")

    # ---- G5 Reform UK consistency -----------------------------------
    positives = [f for f in REFORM_FLAGS if reform.get(f)]
    if not reform.get("applicable") and positives:
        errors.append(f"G5 reform_uk: applicable is false but flags "
                      f"set: {sorted(positives)}")
    if reform.get("applicable") and positives \
            and not reform.get("evidence_span"):
        errors.append("G5 reform_uk: positive flags require an "
                      "evidence span")
    if reform.get("connects_national_to_local") \
            and not (reform.get("national_momentum")
                     and reform.get("local_surrey_activity")):
        errors.append("G5 reform_uk: connects_national_to_local "
                      "requires both national_momentum and "
                      "local_surrey_activity")

    # ---- G6 status consistency --------------------------------------
    if record.get("extraction_status") == "not_attempted" \
            and record.get("geographic_scope"):
        errors.append("G6: not_attempted record carries a scope "
                      "judgement")
    return sorted(errors)


def validate_ln_record(record: dict, body: str,
                       title: str = "") -> list[str]:
    errors = validate_structure(record)
    if errors:
        return errors
    return validate_rules(record, body, title)


def build_ln_prompt() -> str:
    """Focused system prompt. Byte-stable (no clocks) so the batch
    caches it and reruns render identically."""
    schema = SCHEMA_PATH.read_text().strip()
    return f"""You are a geographic-relevance classification system for an academic \
study of pre-election news coverage in Surrey, England. For each article, \
produce ONE JSON object conforming exactly to the JSON Schema below: the \
article's geographic and political scope. \
Prompt version: {LN_PROMPT_VERSION}.

Hard rules:
1. SCOPE FROM THE TEXT. Choose the five-level geographic_scope from what \
the article actually covers; name every ward, division, town/village and \
borough it mentions; set the four mention flags honestly (a flag without \
its named entity is invalid). "Mixed" means the article genuinely carries \
BOTH local Surrey and national content, not merely a national article that \
names Surrey once.
2. TWO SCORES, ONE STORY. local_score and national_score are independent \
0-1 judgements weighing geographic specificity, affected population, the \
political actors involved, issue ownership and electoral context - explain \
the weighing in reasoning. The scores must agree with the scope label: \
ward-specific articles score local above national, national articles the \
reverse, mixed articles at least 0.3 on both.
3. EVIDENCE OR NOTHING. The evidence_span justifying the scope decision \
must be copied CHARACTER-FOR-CHARACTER from the article body (or title, \
with from_title true). NEVER shorten a quote with "..." or any ellipsis, \
NEVER splice passages, NEVER reconstruct from memory; choose a shorter \
contiguous span instead. A validator string-matches every span.
4. ELECTORAL INTERPRETATION WITHOUT ASSUMPTION. local_campaign_signal, \
national_political_trend or national_local_interaction - but NEVER assume \
national coverage affects local voting: interaction requires the article \
itself to make the connection. Use "none" for articles with no electoral \
reading.
5. REFORM UK ADDENDUM. When the article materially concerns Reform UK, \
record whether it carries national momentum, local Surrey activity, \
whether the ARTICLE connects national growth to local competition (only \
valid when both elements are present), and whether local coverage carries \
ward-level conversion signals. National popularity is NEVER assumed to \
convert into local votes.
6. CONFIDENCE IS HONEST. If any confidence is below 0.5, set \
review_status to "flagged".
7. Output ONLY the JSON object - no markdown fences, no commentary.

The JSON Schema (contract {LN_SCHEMA_VERSION}):

{schema}"""
