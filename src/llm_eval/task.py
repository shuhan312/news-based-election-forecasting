"""A classification task: how to build each request and read each answer.

A Task is the only task-specific part of the toolkit. The runner, metrics,
audit and report know nothing about news or elections; they only call
`build_request` and `parse`.

Each request is identified by a hash of everything that reaches the model
(model, max_tokens, messages, output schema). Change one character of the
prompt and the hash changes, so cached answers from the old prompt are never
reused for the new one. That hash is the prompt version.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Task:
    name: str
    model: str
    max_tokens: int
    # item payload -> request body without model/max_tokens
    # (messages, output_config, ...)
    build_request: Callable[[Any], dict]
    # (raw model text, item payload) -> 1 / 0, or None if unusable
    parse: Callable[[str, Any], int | None]
    # Expected output tokens per request, for cost estimates. The input side
    # is counted exactly; output can only be estimated before the run.
    expected_output_tokens: int = 750

    def params(self, payload: Any) -> dict:
        return {"model": self.model, "max_tokens": self.max_tokens,
                **self.build_request(payload)}


def request_hash(params: dict) -> str:
    """sha256 of the exact request. 64 hex characters, which is also a valid
    Batches API custom_id, so results can be matched back without a lookup
    table."""
    blob = json.dumps(params, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --- worked example: V1's frozen local-relevance classifier ----------------------

def v1_local_relevance_task(county: str = "Surrey") -> Task:
    """V1's frozen v2 classifier (claude-sonnet-5) as a Task.

    The payload is the article dict V1's classifier expects. For a county
    other than Surrey, the word "Surrey" in the L3/L4 reason-code definitions
    is replaced by the county name, and nothing else changes. That is the
    same adaptation used in v2_design/outlet_pilot_v1.
    """
    from news_collection import llm_classifier_v2 as clf

    def county_codes():
        patched = copy.deepcopy(clf.REASON_CODE_DEFINITIONS)
        for codes in patched.values():
            for code, text in codes.items():
                codes[code] = text.replace("Surrey", county)
        return patched

    def build(article: dict) -> dict:
        original = clf.REASON_CODE_DEFINITIONS
        if county != "Surrey":
            clf.REASON_CODE_DEFINITIONS = county_codes()
        try:   # restore in `finally`, so V1 code never sees the patch
            rules = clf.applicable_rules_for(article)
            prompt = clf.build_prompt(article, applicable_rules=rules)
            schema = clf.build_output_schema(applicable_rules=rules,
                                             arm=article["arm"])
        finally:
            clf.REASON_CODE_DEFINITIONS = original
        return {"messages": [{"role": "user", "content": prompt}],
                "output_config": {"format": {"type": "json_schema",
                                             "schema": schema}}}

    def parse(raw: str, article: dict) -> int | None:
        # V1's own parser: schema check plus the verbatim-evidence audit.
        try:
            fields = clf.parse_structured_response(
                raw, applicable_rules=clf.applicable_rules_for(article),
                arm=article["arm"], article_text=article["text"])
        except clf.V2ClassificationError:
            return None
        return int(fields.get("e5_decision") == "include")

    return Task(name=f"v1_local_relevance_{county.lower()}",
                model=clf.MODEL, max_tokens=clf.MAX_TOKENS,
                build_request=build, parse=parse,
                expected_output_tokens=750)   # V1 corpus mean: 752
