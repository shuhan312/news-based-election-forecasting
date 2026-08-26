"""Tests for the development-only v2 eligibility classifier.

No test calls the real API. The suite checks the methodological controls that
must be true before a supervisor-approved validation run can be considered:
complete criteria, arm-specific E5 codes, structured output, defensive local
validation, full-text parity, version hashes, and fail-closed stop handling.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.news_collection.llm_classifier_v2 import (
    CLASSIFIER_VERSION,
    V2ClassificationError,
    allowed_reason_codes,
    build_output_schema,
    build_prompt,
    classify_article_v2,
    parse_structured_response,
    request_metadata,
)
from src.news_collection.audit_llm_pilot_disagreements import (
    disagreement_type,
    semantic_llm_decision,
)
from src.news_collection.manual_review_schema import (
    REASON_CODE_DEFINITIONS,
    REASON_CODES,
)
from src.news_collection.llm_v2_io import (
    article_from_sample_row,
    can_reuse,
)

LOCAL_ARTICLE = {
    "article_id": "NEWS-test-1",
    "headline": "Council approves road scheme in Caterham",
    "text": "Surrey County Council approved a road scheme in Caterham.",
    "text_source": "full_text_path",
    "source_id": "surreylive",
    "election_id": "SCC-2021-05",
    "arm": "local",
    "day_index_from_polling_day": 45,
    "needs_reform_disambiguation": "",
    "search_query_id": "Q-1",
    "ward": "Caterham Hill",
    "query_text": "Caterham AND roads",
    "query_family": "ward_manual",
    "geographic_scope": "ward-level",
}


def valid_local_response():
    return {
        "E4": {
            "decision": "include",
            "reason_code": "E4-CLEAR",
            "supporting_text": "Council approved a road scheme",
            "confidence": "high",
        },
        "E5": {
            "decision": "include",
            "reason_code": "E5-L3-COUNCIL-ISSUE",
            "supporting_text": "road scheme in Caterham",
            "confidence": "high",
        },
        "E8": {
            "decision": "include",
            "reason_code": "E8-EDITORIAL-CONFIRMED",
            "supporting_text": "Surrey County Council approved",
            "confidence": "medium",
        },
    }


class TestCodebookAndPrompt:
    def test_every_reason_code_has_an_operational_definition(self):
        assert REASON_CODE_DEFINITIONS.keys() == REASON_CODES.keys()
        for rule, codes in REASON_CODES.items():
            assert REASON_CODE_DEFINITIONS[rule].keys() == codes.keys()
            assert all(REASON_CODE_DEFINITIONS[rule][code] for code in codes)

    def test_e5_codes_are_arm_specific(self):
        local = set(allowed_reason_codes("E5", arm="local"))
        national = set(allowed_reason_codes("E5", arm="national"))
        assert "E5-L3-COUNCIL-ISSUE" in local
        assert "E5-N2-POLICY-ISSUE" not in local
        assert "E5-N2-POLICY-ISSUE" in national
        assert "E5-L3-COUNCIL-ISSUE" not in national

    def test_prompt_contains_real_definition_context_and_abstention_rule(self):
        prompt = build_prompt(
            LOCAL_ARTICLE, applicable_rules=["E4", "E5", "E8"]
        )
        assert "identifiably affecting the sampled area" in prompt
        assert "Caterham Hill" in prompt
        assert "Caterham AND roads" in prompt
        assert "Use insufficient_evidence only when" in prompt
        assert "apply only L1-L4" in prompt

    def test_schema_constrains_decisions_and_arm_specific_codes(self):
        schema = build_output_schema(
            applicable_rules=["E4", "E5", "E8"], arm="local"
        )
        encoded = json.dumps(schema)
        assert '"decision": {"type": "string", "enum":' in encoded
        assert "E5-L3-COUNCIL-ISSUE" in encoded
        assert "E5-N2-POLICY-ISSUE" not in encoded
        assert schema["additionalProperties"] is False


class TestDefensiveParsing:
    def test_valid_response_parses(self):
        fields = parse_structured_response(
            json.dumps(valid_local_response()),
            applicable_rules=["E4", "E5", "E8"],
            arm="local",
            article_text=LOCAL_ARTICLE["text"],
        )
        assert fields["e5_decision"] == "include"
        assert fields["e5_reason_code"] == "E5-L3-COUNCIL-ISSUE"

    def test_reason_code_in_decision_field_is_rejected(self):
        response = valid_local_response()
        response["E4"]["decision"] = "E4-CLEAR"
        with pytest.raises(V2ClassificationError, match="decision"):
            parse_structured_response(
                json.dumps(response),
                applicable_rules=["E4", "E5", "E8"],
                arm="local",
                article_text=LOCAL_ARTICLE["text"],
            )

    def test_decision_reason_polarity_mismatch_is_rejected(self):
        response = valid_local_response()
        response["E5"]["decision"] = "exclude"
        with pytest.raises(V2ClassificationError, match="mismatch"):
            parse_structured_response(
                json.dumps(response),
                applicable_rules=["E4", "E5", "E8"],
                arm="local",
                article_text=LOCAL_ARTICLE["text"],
            )

    def test_national_code_on_local_record_is_rejected(self):
        response = valid_local_response()
        response["E5"]["reason_code"] = "E5-N2-POLICY-ISSUE"
        with pytest.raises(V2ClassificationError, match="not legal"):
            parse_structured_response(
                json.dumps(response),
                applicable_rules=["E4", "E5", "E8"],
                arm="local",
                article_text=LOCAL_ARTICLE["text"],
            )

    def test_extra_field_is_rejected(self):
        response = valid_local_response()
        response["E8"]["explanation"] = "not in schema"
        with pytest.raises(V2ClassificationError, match="exactly"):
            parse_structured_response(
                json.dumps(response),
                applicable_rules=["E4", "E5", "E8"],
                arm="local",
                article_text=LOCAL_ARTICLE["text"],
            )

    def test_insufficient_evidence_must_be_empty_and_null_confidence(self):
        response = valid_local_response()
        response["E4"] = {
            "decision": "insufficient_evidence",
            "reason_code": "E4-NO-FULL-TEXT",
            "supporting_text": "some quote",
            "confidence": "low",
        }
        with pytest.raises(
            V2ClassificationError, match="empty supporting_text"
        ):
            parse_structured_response(
                json.dumps(response),
                applicable_rules=["E4", "E5", "E8"],
                arm="local",
                article_text=LOCAL_ARTICLE["text"],
            )

    def test_evidence_must_be_a_verbatim_article_substring(self):
        response = valid_local_response()
        response["E4"]["supporting_text"] = (
            "Council approved ... a road scheme"
        )
        with pytest.raises(V2ClassificationError, match="verbatim substring"):
            parse_structured_response(
                json.dumps(response),
                applicable_rules=["E4", "E5", "E8"],
                arm="local",
                article_text=LOCAL_ARTICLE["text"],
            )


class TestAPIRequestAndStops:
    def fake_response(self, *, stop_reason="end_turn", text=None):
        return SimpleNamespace(
            id="msg_test",
            stop_reason=stop_reason,
            content=[
                SimpleNamespace(
                    type="text",
                    text=text or json.dumps(valid_local_response()),
                )
            ],
            usage=SimpleNamespace(input_tokens=100, output_tokens=50),
        )

    def test_request_uses_structured_outputs_and_returns_version_metadata(self):
        client = MagicMock()
        client.messages.create.return_value = self.fake_response()
        result = classify_article_v2(LOCAL_ARTICLE, client=client)
        assert result["status"] == "ok"
        assert result["classifier_version"] == CLASSIFIER_VERSION
        assert result["response_id"] == "msg_test"
        request = client.messages.create.call_args.kwargs
        # The current model rejects the deprecated temperature parameter.
        # Its absence is part of the tested API contract for this version.
        assert "temperature" not in request
        assert request["output_config"]["format"]["type"] == "json_schema"
        assert (
            request["output_config"]["format"]["schema"]
            ["additionalProperties"]
            is False
        )

    def test_max_tokens_stop_fails_before_parsing(self):
        client = MagicMock()
        client.messages.create.return_value = self.fake_response(
            stop_reason="max_tokens", text="{"
        )
        result = classify_article_v2(LOCAL_ARTICLE, client=client)
        assert result["status"] == "incomplete_output"
        assert result["stop_reason"] == "max_tokens"
        assert "e4_decision" not in result


class TestFrozenV2Inputs:
    def test_runner_prefers_full_text_and_adds_query_context(self, tmp_path):
        article_id = "NEWS-test-full"
        full_text = tmp_path / "article.txt"
        full_text.write_text("full article text beyond the spreadsheet lead")
        records = tmp_path / "records"
        records.mkdir()
        (records / f"{article_id}.json").write_text(
            json.dumps(
                {
                    "retrieval": {"search_query_id": "Q-test"},
                    "content": {},
                }
            )
        )
        row = {
            "article_id": article_id,
            "headline": "Headline",
            "article_text_path": str(full_text),
            "article_text_excerpt": "short excerpt",
            "source_id": "surreylive",
            "election_id": "SCC-2021-05",
            "arm": "local",
            "day_index_from_polling_day": "30",
            "needs_reform_disambiguation": "",
        }
        article = article_from_sample_row(
            row,
            query_by_id={
                "Q-test": {
                    "ward": "Addlestone Ward",
                    "query_text": "Addlestone AND roads",
                    "query_family": "ward_manual",
                    "geographic_scope": "ward-level",
                }
            },
            records_dir=records,
        )
        assert article["text"] == full_text.read_text()
        assert article["text_source"] == "full_text_path"
        assert article["ward"] == "Addlestone Ward"
        assert article["query_text"] == "Addlestone AND roads"

    def test_reuse_requires_all_request_hashes_to_match(self):
        previous = {"status": "ok", **request_metadata(LOCAL_ARTICLE)}
        assert can_reuse(previous, LOCAL_ARTICLE)
        changed = {**LOCAL_ARTICLE, "text": "different full text"}
        assert not can_reuse(previous, changed)

class TestV1DisagreementAudit:
    def test_reason_code_in_decision_is_interpreted_but_flagged(self):
        semantic, misaligned = semantic_llm_decision("E4", "E4-CLEAR")
        assert semantic == "include"
        assert misaligned is True

    def test_semantic_repair_is_not_mislabelled_as_raw_agreement(self):
        category = disagreement_type(
            "include",
            "E4-CLEAR",
            "include",
            field_misalignment=True,
        )
        assert category == "field_misalignment_same_semantics"
