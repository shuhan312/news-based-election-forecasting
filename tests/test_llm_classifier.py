"""Tests for the LLM classifier infrastructure (llm_classifier.py).

None of these tests make a real network call - the point of this
module, per its own docstring, is that it must not produce any real
classification before supervisor approval, so the test suite enforces
that boundary too: classify_article() is only ever exercised here with
no key (proving it fails closed) or with the anthropic client mocked
out (proving the plumbing works without ever touching the real API).
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.news_collection.llm_classifier import (ClassificationError,
                                                 build_prompt,
                                                 classify_article,
                                                 parse_response)
from src.news_collection.manual_review_schema import RULES, validate_row

ARTICLE = {
    "headline": "Council approves new road scheme in Caterham",
    "text": "Surrey County Council has approved a new road scheme...",
    "source_id": "surreylive", "election_id": "SCC-2021-05",
    "arm": "local", "day_index_from_polling_day": 45,
    "needs_reform_disambiguation": "",
}

REFORM_ARTICLE = {**ARTICLE, "needs_reform_disambiguation": "yes"}


class TestBuildPrompt:
    def test_includes_article_text_and_headline(self):
        prompt = build_prompt(ARTICLE, applicable_rules=["E4", "E5", "E8"])
        assert ARTICLE["headline"] in prompt
        assert ARTICLE["text"] in prompt

    def test_omits_e6_for_non_reform_flagged_article(self):
        prompt = build_prompt(ARTICLE, applicable_rules=["E4", "E5", "E8"])
        assert "Rule E6:" not in prompt

    def test_includes_e6_when_asked_for(self):
        prompt = build_prompt(REFORM_ARTICLE,
                              applicable_rules=["E4", "E5", "E6", "E8"])
        assert "Rule E6:" in prompt
        assert "E6-PARTY-CONFIRMED" in prompt

    def test_never_includes_not_applicable_as_a_choosable_code(self):
        prompt = build_prompt(REFORM_ARTICLE,
                              applicable_rules=["E4", "E5", "E6", "E8"])
        assert "E6-NOT-REFORM-FLAGGED" not in prompt

    def test_prompt_reflects_codebook_reason_codes_exactly(self):
        # the prompt must be built FROM the schema's REASON_CODES, not
        # a hand-copied duplicate that could drift out of sync
        from src.news_collection.manual_review_schema import REASON_CODES
        prompt = build_prompt(ARTICLE, applicable_rules=["E5"])
        for code in REASON_CODES["E5"]:
            if REASON_CODES["E5"][code] != "not_applicable":
                assert code in prompt


class TestParseResponse:
    def _valid_json(self, rules=("E4", "E5", "E8")):
        return json.dumps({
            r: {"decision": "include", "reason_code": f"{r}-X",
               "supporting_text": "quote", "confidence": "high"}
            for r in rules})

    def test_parses_matching_rules(self):
        raw = self._valid_json(rules=("E4",))
        fields = parse_response(raw, applicable_rules=["E4"])
        assert fields["e4_decision"] == "include"
        assert fields["e4_reason_code"] == "E4-X"
        assert fields["e4_confidence"] == "high"

    def test_non_json_response_raises(self):
        with pytest.raises(ClassificationError, match="not valid JSON"):
            parse_response("this is not json", applicable_rules=["E4"])

    def test_missing_rule_in_response_raises(self):
        raw = json.dumps({"E4": {"decision": "include",
                                "reason_code": "E4-CLEAR",
                                "supporting_text": "x", "confidence": "high"}})
        with pytest.raises(ClassificationError, match="missing an 'E5'"):
            parse_response(raw, applicable_rules=["E4", "E5"])


class TestClassifyArticleFailsClosed:
    def test_no_api_key_produces_not_configured_not_a_guess(self):
        result = classify_article(ARTICLE, api_key=None)
        assert result["status"] == "not_configured"
        # must not contain any decision fields at all - a missing key
        # produces an honest gap, never a fabricated classification
        assert "e4_decision" not in result

    def test_no_api_key_ignores_any_ambient_env_var(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = classify_article(ARTICLE)
        assert result["status"] == "not_configured"


class TestClassifyArticleWithMockedClient:
    def test_successful_classification_is_parsed_and_validatable(self):
        fake_response = MagicMock()
        fake_block = MagicMock()
        fake_block.type = "text"
        fake_block.text = json.dumps({
            "E4": {"decision": "include", "reason_code": "E4-CLEAR",
                  "supporting_text": "no mention of results",
                  "confidence": "high"},
            "E5": {"decision": "include", "reason_code": "E5-L3-COUNCIL-ISSUE",
                  "supporting_text": "road scheme in Caterham",
                  "confidence": "high"},
            "E8": {"decision": "include", "reason_code": "E8-EDITORIAL-CONFIRMED",
                  "supporting_text": "Surrey County Council has approved",
                  "confidence": "medium"},
        })
        fake_response.content = [fake_block]

        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_response

        with patch("anthropic.Anthropic", return_value=fake_client):
            result = classify_article(ARTICLE, api_key="fake-key-for-test")

        assert result["status"] == "ok"
        assert result["e4_decision"] == "include"
        # E6 must be filled in as not_applicable even though the mocked
        # response never mentioned it - this article was never Reform-
        # flagged, so it was never asked
        assert result["e6_decision"] == "not_applicable"
        assert result["e6_reason_code"] == "E6-NOT-REFORM-FLAGGED"

    def test_result_can_populate_a_schema_valid_row(self):
        """The whole point of matching manual_review_schema's field
        names: an LLM classification, once validated, should be able
        to be checked with the SAME validate_row() a human row uses -
        proving the two are genuinely comparable, not just superficially
        similar-looking CSVs."""
        fake_response = MagicMock()
        fake_block = MagicMock()
        fake_block.type = "text"
        fake_block.text = json.dumps({
            "E4": {"decision": "include", "reason_code": "E4-CLEAR",
                  "supporting_text": "quote", "confidence": "high"},
            "E5": {"decision": "include", "reason_code": "E5-L1-PLACE",
                  "supporting_text": "quote", "confidence": "high"},
            "E8": {"decision": "include", "reason_code": "E8-EDITORIAL-CONFIRMED",
                  "supporting_text": "quote", "confidence": "high"},
        })
        fake_response.content = [fake_block]
        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_response

        with patch("anthropic.Anthropic", return_value=fake_client):
            result = classify_article(ARTICLE, api_key="fake-key-for-test")

        from src.news_collection.manual_review_schema import \
            derive_overall_decision
        overall = derive_overall_decision(
            result["e4_decision"], result["e5_decision"],
            result["e6_decision"], result["e8_decision"])
        row = {
            **{f"{r.lower()}_decision": result[f"{r.lower()}_decision"]
              for r in RULES},
            **{f"{r.lower()}_reason_code": result[f"{r.lower()}_reason_code"]
              for r in RULES},
            **{f"{r.lower()}_supporting_text":
              result[f"{r.lower()}_supporting_text"] for r in RULES},
            **{f"{r.lower()}_confidence": result[f"{r.lower()}_confidence"]
              for r in RULES},
            "original_manual_decision": overall,
            "second_review_required": "False",
            "final_reviewed_decision": overall,
            "correction_reason": "",
        }
        assert validate_row(row) is True

    def test_malformed_response_returns_parse_error_not_a_guess(self):
        fake_response = MagicMock()
        fake_block = MagicMock()
        fake_block.type = "text"
        fake_block.text = "not json at all"
        fake_response.content = [fake_block]
        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_response

        with patch("anthropic.Anthropic", return_value=fake_client):
            result = classify_article(ARTICLE, api_key="fake-key-for-test")

        assert result["status"] == "parse_error"
        assert "e4_decision" not in result
