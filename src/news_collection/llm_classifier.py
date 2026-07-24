"""LLM-assisted classifier for the E4/E5/E6/E8 manual-review rules.

classify_article() fails closed with status=not_configured whenever
no ANTHROPIC_API_KEY is set (verified 2026-07-23 against all 168
pilot articles - all 168 correctly produced no classification) rather
than fabricating a result.

Per news_protocol/eligibility_manual_review_methodology.md §7, use of
this module's output is gated on the kappa check: this
module's output is only trustworthy for the ~2,500 records the human
pilot never covered once compare_llm_to_human_agreement.py shows every
rule clearing the same 0.60 bar used for the human blind recheck. See
that script and the pilot results already on record (§3) before
treating any LLM output here as usable.

The prompt is built FROM manual_review_schema.REASON_CODES, not
copied by hand, so the LLM is judged against exactly the same
criteria a human reviewer uses.

Usage:
    python3 -m src.news_collection.run_llm_classification_pilot
"""

import json
import os

from .manual_review_schema import (DECISIONS, REASON_CODES, RULES,
                                   ValidationError, validate_row)

MODEL = "claude-sonnet-5"   # a fixed, disclosed model choice - not
                              # left to whatever the default happens to
                              # be, since the methodology write-up must
                              # be able to name exactly what was used
MAX_TOKENS = 1024


def _rule_block(rule):
    """One rule's codebook entry, formatted for the prompt - pulled
    directly from REASON_CODES so it is word-for-word the same
    criteria a human reviewer works from."""
    lines = [f"Rule {rule}:"]
    for code, decision in REASON_CODES[rule].items():
        if decision == "not_applicable":
            continue   # never a real choice the model should output
        lines.append(f"  - {code} (decision={decision})")
    return "\n".join(lines)


def build_prompt(article, *, applicable_rules):
    """article: dict with headline, text, source_id, election_id,
    arm, day_index_from_polling_day (may be None).
    applicable_rules: subset of RULES actually being asked about (E6
    is omitted entirely for non-Reform-flagged articles - the model is
    never even given the option to invent an E6 opinion on an article
    that was never flagged for it).
    """
    rule_blocks = "\n\n".join(_rule_block(r) for r in applicable_rules)
    day_index_note = (
        f"{article['day_index_from_polling_day']} days before polling day"
        if article.get("day_index_from_polling_day") is not None
        else "unknown")
    return f"""You are applying a pre-registered eligibility codebook to \
one news article for an academic research project. Apply ONLY the \
criteria given below - do not use outside knowledge of the election's \
actual outcome, and do not consider the article's stance or tone.

Article:
  Headline: {article['headline']}
  Source: {article['source_id']} ({article['arm']} arm)
  Election: {article['election_id']}
  Days before polling day: {day_index_note}
  Text:
  \"\"\"
  {article['text']}
  \"\"\"

For EACH rule below, choose exactly one decision from: \
{", ".join(d for d in DECISIONS if d != "not_applicable")}.
Every decision needs a reason_code from that rule's list, a \
supporting_text field quoting the exact words from the article that \
justify it (or "" if decision is insufficient_evidence - do not quote \
anything if there is nothing to quote), and a confidence of high, \
medium, or low.

{rule_blocks}

Respond with ONLY a JSON object, no other text, in exactly this shape:
{{"E4": {{"decision": "...", "reason_code": "...", "supporting_text": \
"...", "confidence": "..."}}, "E5": {{...}}, ...}}
Include only the rules listed above."""


class ClassificationError(Exception):
    pass


def parse_response(raw_text, *, applicable_rules):
    """Turn the model's JSON text into the per-rule fields
    manual_review_schema expects, raising ClassificationError (never
    silently guessing a value) if the response doesn't parse or is
    missing a required rule."""
    try:
        parsed = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError) as e:
        raise ClassificationError(f"response was not valid JSON: {e}")

    fields = {}
    for rule in applicable_rules:
        entry = parsed.get(rule)
        if not isinstance(entry, dict):
            raise ClassificationError(f"response missing an '{rule}' entry")
        prefix = rule.lower()
        fields[f"{prefix}_decision"] = entry.get("decision", "")
        fields[f"{prefix}_reason_code"] = entry.get("reason_code", "")
        fields[f"{prefix}_supporting_text"] = entry.get("supporting_text", "")
        fields[f"{prefix}_confidence"] = entry.get("confidence", "")
    return fields


def classify_article(article, *, api_key=None):
    """One article in, one dict of per-rule fields out (or a dict
    carrying an explicit failure reason - never a guessed decision).

    applicable_rules is derived here, not passed in, from the same
    fact the human sheet uses (needs_reform_disambiguation) - so a
    non-Reform-flagged article is never even asked about E6, exactly
    like build_review_row() pre-fills e6_decision=not_applicable
    without asking a human either.
    """
    applicable_rules = [r for r in RULES if r != "E6" or
                        article.get("needs_reform_disambiguation") == "yes"]

    api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"status": "not_configured",
               "note": "ANTHROPIC_API_KEY not set - no classification "
                       "attempted, nothing fabricated."}

    import anthropic   # imported lazily so the rest of this module
                       # (prompt-building, response parsing) is testable
                       # without the SDK's network/auth machinery involved
    client = anthropic.Anthropic(api_key=api_key)
    prompt = build_prompt(article, applicable_rules=applicable_rules)
    try:
        response = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}])
    except anthropic.APIError as e:
        return {"status": "api_error", "note": str(e)}

    raw_text = "".join(block.text for block in response.content
                       if block.type == "text")
    try:
        fields = parse_response(raw_text, applicable_rules=applicable_rules)
    except ClassificationError as e:
        return {"status": "parse_error", "note": str(e), "raw_text": raw_text}

    # E6 is not_applicable by construction when it wasn't asked about -
    # same rule build_review_row() applies for the human sheet, kept
    # identical here so the two are directly comparable row-for-row.
    if "E6" not in applicable_rules:
        fields["e6_decision"] = "not_applicable"
        fields["e6_reason_code"] = "E6-NOT-REFORM-FLAGGED"
        fields["e6_supporting_text"] = ""
        fields["e6_confidence"] = ""

    fields["status"] = "ok"
    return fields
