"""Development-only v2 classifier for E4/E5/E6/E8.

Research status
---------------
This module is a feasibility prototype, not a validated production
classifier. It deliberately does not replace ``llm_classifier.py`` or its
2026-07-24 v1 pilot output. The existing 168-article pilot is preserved as
the audit baseline and may be used to develop this version, but it cannot
also serve as the final independent validation set after prompt changes.

The supervisor requirement says that false-positive uses of the word
"reform" should be removed manually. Consequently, even a high-agreement E6
prediction from this module is a recommendation for human review unless the
supervisor explicitly approves a validated LLM-assisted or hybrid procedure.

What v2 changes, and why
------------------------
* The complete operational definitions are supplied to the model. V1 exposed
  code names and polarities but not the prose criteria needed to apply them.
* E5 is arm-specific: local records may use L-codes, national records may use
  N-codes. This mirrors the supervisor's local-versus-national design.
* ``output_config.format`` constrains the response with JSON Schema. The
  schema couples each decision to reason codes of the same polarity, so a
  reason code cannot be written into the decision field.
* The structured response is still validated locally. Structured output can
  be interrupted by a refusal or token limit, and defence in depth makes an
  invalid value fail closed rather than enter an agreement calculation.
* Every result carries version and hash metadata so a later runner cannot
  silently mix outputs from different prompts, inputs, or schemas.

No call made by this module changes eligibility data or sends a result into
the analysis corpus. A separate development runner writes to a separate
versioned file.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from typing import Any

from .manual_review_schema import (
    CONFIDENCE_LEVELS,
    DECISIONS,
    REASON_CODE_DEFINITIONS,
    REASON_CODES,
    RULE_DEFINITIONS,
    RULES,
)

CLASSIFIER_VERSION = "v2-development-2026-07-24"
MODEL = "claude-sonnet-5"
MAX_TOKENS = 4096

# Only these four decisions are model choices. ``not_applicable`` is filled
# mechanically for E6 when the record was not produced by a Reform query.
MODEL_DECISIONS = tuple(d for d in DECISIONS if d != "not_applicable")

# E5 is not "any L or N code". The collection arm determines the relevant
# test. Shared codes cover a genuine failure, arm-specific uncertainty, and
# unavailable evidence.
_E5_CODES_BY_ARM = {
    "local": {
        "E5-L1-PLACE",
        "E5-L2-CANDIDATE",
        "E5-L3-COUNCIL-ISSUE",
        "E5-L4-COUNTY-WIDE",
        "E5-NO-L-OR-N-RULE-MET",
        "E5-BORDERLINE-PLACE-MENTION",
        "E5-NO-FULL-TEXT",
    },
    "national": {
        "E5-N1-PARTY-POLITICS",
        "E5-N2-POLICY-ISSUE",
        "E5-N3-REFORM-GROWTH",
        "E5-NO-L-OR-N-RULE-MET",
        "E5-BORDERLINE-POLICY-RELEVANCE",
        "E5-NO-FULL-TEXT",
    },
}


class V2ClassificationError(Exception):
    """A response failed the v2 format or codebook-consistency checks."""


def _stable_hash(value: Any) -> str:
    """SHA-256 of a JSON-serialisable value with deterministic ordering."""
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def applicable_rules_for(article: dict[str, Any]) -> list[str]:
    """Return rules the model should judge for this article.

    E6 is omitted when it is not applicable. Omitting it is safer than asking
    the model to reproduce a mechanical value: the model cannot invent an E6
    judgement for an article that never matched a Reform-related query.
    """
    return [
        rule
        for rule in RULES
        if rule != "E6"
        or article.get("needs_reform_disambiguation") == "yes"
    ]


def allowed_reason_codes(rule: str, *, arm: str) -> tuple[str, ...]:
    """Return the legal model-selectable codes for one rule and arm."""
    if rule not in RULES:
        raise ValueError(f"unknown rule {rule!r}")
    if arm not in _E5_CODES_BY_ARM:
        raise ValueError(f"arm must be 'local' or 'national', got {arm!r}")

    codes = set(REASON_CODES[rule])
    if rule == "E5":
        codes &= _E5_CODES_BY_ARM[arm]
    if rule == "E6":
        codes.discard("E6-NOT-REFORM-FLAGGED")
    return tuple(code for code in REASON_CODES[rule] if code in codes)


def _rule_output_schema(rule: str, *, arm: str) -> dict[str, Any]:
    """Build one rule's JSON Schema with decision/code polarity coupled.

    A flat pair of independent enums would prevent invented values but would
    still allow ``decision=include`` with an exclusion reason code. The
    ``anyOf`` branches below make each legal decision-code combination a
    separate grammar branch, preventing that mismatch during generation.
    """
    codes_by_decision: dict[str, list[str]] = defaultdict(list)
    for code in allowed_reason_codes(rule, arm=arm):
        decision = REASON_CODES[rule][code]
        if decision in MODEL_DECISIONS:
            codes_by_decision[decision].append(code)

    branches = []
    for decision in MODEL_DECISIONS:
        reason_codes = codes_by_decision.get(decision)
        if not reason_codes:
            continue

        confidence_schema: dict[str, Any]
        if decision in ("include", "exclude"):
            confidence_schema = {
                "type": "string",
                "enum": list(CONFIDENCE_LEVELS),
            }
        else:
            # Null is explicit and unambiguous in JSON. The CSV runner later
            # serialises it as an empty cell to match the human-review schema,
            # which does not require confidence for unresolved decisions.
            confidence_schema = {"type": "null"}

        supporting_schema: dict[str, Any] = {"type": "string"}
        if decision == "insufficient_evidence":
            supporting_schema["const"] = ""

        branches.append(
            {
                "type": "object",
                "properties": {
                    "decision": {"type": "string", "const": decision},
                    "reason_code": {
                        "type": "string",
                        "enum": reason_codes,
                    },
                    "supporting_text": supporting_schema,
                    "confidence": confidence_schema,
                },
                "required": [
                    "decision",
                    "reason_code",
                    "supporting_text",
                    "confidence",
                ],
                "additionalProperties": False,
            }
        )

    return {"anyOf": branches}


def build_output_schema(
    *, applicable_rules: list[str], arm: str
) -> dict[str, Any]:
    """Build the exact response schema for this article."""
    unknown = set(applicable_rules) - set(RULES)
    if unknown:
        raise ValueError(f"unknown applicable rule(s): {sorted(unknown)}")
    return {
        "type": "object",
        "properties": {
            rule: _rule_output_schema(rule, arm=arm)
            for rule in applicable_rules
        },
        "required": list(applicable_rules),
        "additionalProperties": False,
    }


def _rule_block(rule: str, *, arm: str) -> str:
    """Render the full operational rule and legal codes into the prompt."""
    lines = [f"Rule {rule}: {RULE_DEFINITIONS[rule]}"]
    for code in allowed_reason_codes(rule, arm=arm):
        decision = REASON_CODES[rule][code]
        lines.append(
            f"- {code} (decision={decision}): "
            f"{REASON_CODE_DEFINITIONS[rule][code]}"
        )
    return "\n".join(lines)


def build_prompt(
    article: dict[str, Any], *, applicable_rules: list[str]
) -> str:
    """Create the versioned v2 research prompt.

    Collection context is supplied because the supervisor's local relevance
    definition depends on the ward/town/query that produced the article.
    Supplying it is not answer leakage: it is information the human codebook
    explicitly requires to decide L1-L3.
    """
    arm = article["arm"]
    rule_blocks = "\n\n".join(
        _rule_block(rule, arm=arm) for rule in applicable_rules
    )
    day_index = article.get("day_index_from_polling_day")
    day_note = (
        f"{day_index} days before polling day"
        if day_index is not None
        else "unknown"
    )
    ward = article.get("ward") or "not specified / county or national scope"
    query_text = article.get("query_text") or "not available"
    query_family = article.get("query_family") or "not available"
    geographic_scope = article.get("geographic_scope") or "not available"

    return f"""Classifier version: {CLASSIFIER_VERSION}

You are applying a documented article-eligibility codebook for an academic
research development study. Apply only the supplied rules and article text.
Do not use knowledge of the eventual election result. Do not judge political
stance, tone, writing quality, or whether you agree with the article.

Collection context:
- Election: {article['election_id']}
- Collection arm: {arm}
- Sampled ward/division: {ward}
- Geographic scope of originating search: {geographic_scope}
- Query family: {query_family}
- Exact originating query: {query_text}
- Source: {article['source_id']}
- Publication timing: {day_note}
- Headline: {article['headline']}

Important arm rule for E5:
- If arm=local, apply only L1-L4 and never include an article merely because
  it satisfies a national N-rule.
- If arm=national, apply only N1-N3 and never include an article merely
  because it satisfies a local L-rule.

Abstention rule:
Use insufficient_evidence only when the lawfully available input is
materially incomplete or unreadable AND that limitation prevents the rule
from being decided. If the supplied text is readable and sufficient to
apply the codebook, choose include, exclude, or needs_second_review.
Do not use insufficient_evidence merely because the case is difficult.

Evidence rule:
For every decision except insufficient_evidence, quote a short exact passage
from the supplied article in supporting_text. For insufficient_evidence,
supporting_text must be the empty string. Confidence is high, medium, or low
only for include/exclude; unresolved decisions use JSON null.

{rule_blocks}

Article text:
\"\"\"
{article['text']}
\"\"\"

Return only the structured response required by the supplied JSON Schema."""


def parse_structured_response(
    raw_text: str,
    *,
    applicable_rules: list[str],
    arm: str,
) -> dict[str, Any]:
    """Parse and defensively validate a structured-output response."""
    try:
        parsed = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise V2ClassificationError(
            f"response was not valid JSON: {exc}"
        ) from exc

    if not isinstance(parsed, dict):
        raise V2ClassificationError("top-level response must be an object")
    expected_rules = set(applicable_rules)
    actual_rules = set(parsed)
    if actual_rules != expected_rules:
        raise V2ClassificationError(
            "top-level rules do not match request: "
            f"expected {sorted(expected_rules)}, got {sorted(actual_rules)}"
        )

    fields: dict[str, Any] = {}
    expected_entry_fields = {
        "decision",
        "reason_code",
        "supporting_text",
        "confidence",
    }
    for rule in applicable_rules:
        entry = parsed[rule]
        if not isinstance(entry, dict):
            raise V2ClassificationError(f"{rule} entry must be an object")
        if set(entry) != expected_entry_fields:
            raise V2ClassificationError(
                f"{rule} fields must be exactly "
                f"{sorted(expected_entry_fields)}, got {sorted(entry)}"
            )

        decision = entry["decision"]
        reason_code = entry["reason_code"]
        supporting_text = entry["supporting_text"]
        confidence = entry["confidence"]

        if decision not in MODEL_DECISIONS:
            raise V2ClassificationError(
                f"{rule} decision {decision!r} is not legal"
            )
        legal_codes = allowed_reason_codes(rule, arm=arm)
        if reason_code not in legal_codes:
            raise V2ClassificationError(
                f"{rule} reason code {reason_code!r} is not legal for "
                f"arm={arm}"
            )
        expected_decision = REASON_CODES[rule][reason_code]
        if decision != expected_decision:
            raise V2ClassificationError(
                f"{rule} decision/code mismatch: {decision!r} versus "
                f"{reason_code!r} ({expected_decision!r})"
            )
        if not isinstance(supporting_text, str):
            raise V2ClassificationError(
                f"{rule} supporting_text must be a string"
            )
        if decision == "insufficient_evidence":
            if supporting_text != "":
                raise V2ClassificationError(
                    f"{rule} insufficient_evidence must have empty "
                    "supporting_text"
                )
            if confidence is not None:
                raise V2ClassificationError(
                    f"{rule} insufficient_evidence confidence must be null"
                )
        else:
            if not supporting_text.strip():
                raise V2ClassificationError(
                    f"{rule} {decision} needs a non-empty evidence quote"
                )
            if decision in ("include", "exclude"):
                if confidence not in CONFIDENCE_LEVELS:
                    raise V2ClassificationError(
                        f"{rule} {decision} needs confidence from "
                        f"{CONFIDENCE_LEVELS}"
                    )
            elif confidence is not None:
                raise V2ClassificationError(
                    f"{rule} unresolved decision confidence must be null"
                )

        prefix = rule.lower()
        fields[f"{prefix}_decision"] = decision
        fields[f"{prefix}_reason_code"] = reason_code
        fields[f"{prefix}_supporting_text"] = supporting_text
        fields[f"{prefix}_confidence"] = confidence or ""

    return fields


def request_metadata(article: dict[str, Any]) -> dict[str, str]:
    """Return version/hash metadata without making an API request.

    The development runner uses this before carrying a previous successful
    row forward. Reuse is allowed only when classifier version, model, input,
    complete prompt, schema, and requested-rule set are all identical.
    """
    applicable_rules = applicable_rules_for(article)
    prompt = build_prompt(article, applicable_rules=applicable_rules)
    schema = build_output_schema(
        applicable_rules=applicable_rules, arm=article["arm"]
    )
    return {
        "classifier_version": CLASSIFIER_VERSION,
        "model": MODEL,
        "input_sha256": _stable_hash(article),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "schema_sha256": _stable_hash(schema),
        "requested_rules": ",".join(applicable_rules),
    }


def classify_article_v2(
    article: dict[str, Any],
    *,
    api_key: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Classify one article, failing closed on every incomplete state.

    A client may be injected by unit tests. Production use creates the
    Anthropic client lazily so prompt/schema tests do not require the SDK or a
    network connection.
    """
    applicable_rules = applicable_rules_for(article)
    prompt = build_prompt(article, applicable_rules=applicable_rules)
    schema = build_output_schema(
        applicable_rules=applicable_rules, arm=article["arm"]
    )
    metadata = request_metadata(article)

    if client is None:
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return {
                **metadata,
                "status": "not_configured",
                "note": "ANTHROPIC_API_KEY not set; no request attempted.",
            }
        try:
            import anthropic
        except ImportError as exc:
            return {
                **metadata,
                "status": "sdk_not_installed",
                "note": f"anthropic SDK is not installed: {exc}",
            }
        client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": schema,
                }
            },
        )
    except TypeError as exc:
        # A TypeError here commonly means the installed SDK predates
        # output_config. It is a configuration failure, not an article
        # classification and must never be silently retried as free text.
        return {
            **metadata,
            "status": "client_configuration_error",
            "note": str(exc),
        }
    except Exception as exc:  # SDK/network boundary: preserve, never guess.
        return {**metadata, "status": "api_error", "note": str(exc)}

    stop_reason = getattr(response, "stop_reason", None)
    raw_text = "".join(
        getattr(block, "text", "")
        for block in getattr(response, "content", [])
        if getattr(block, "type", None) == "text"
    )
    response_id = getattr(response, "id", "")
    usage = getattr(response, "usage", None)
    response_metadata = {
        **metadata,
        "response_id": response_id,
        "stop_reason": stop_reason or "",
        "input_tokens": getattr(usage, "input_tokens", "") if usage else "",
        "output_tokens": getattr(usage, "output_tokens", "") if usage else "",
        "raw_text": raw_text,
    }

    # Structured JSON is only guaranteed on a normal completion. Refusals and
    # max-token stops can legally return non-schema text, so inspect the stop
    # reason before parsing.
    if stop_reason != "end_turn":
        return {
            **response_metadata,
            "status": "incomplete_output",
            "note": f"unexpected stop_reason={stop_reason!r}",
        }

    try:
        fields = parse_structured_response(
            raw_text,
            applicable_rules=applicable_rules,
            arm=article["arm"],
        )
    except V2ClassificationError as exc:
        return {
            **response_metadata,
            "status": "schema_error",
            "note": str(exc),
        }

    if "E6" not in applicable_rules:
        fields.update(
            {
                "e6_decision": "not_applicable",
                "e6_reason_code": "E6-NOT-REFORM-FLAGGED",
                "e6_supporting_text": "",
                "e6_confidence": "",
            }
        )

    return {
        **response_metadata,
        **fields,
        "status": "ok",
        "note": "",
    }
