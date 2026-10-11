"""Tests for llm_eval's pricing, task hashing and runner.

The runner is tested against a fake Anthropic client that records every call,
so each test can assert exactly what was (and was not) sent. No network, no
API key, no cost.
"""

import json
from types import SimpleNamespace

import pytest

from llm_eval.pricing import cost_usd
from llm_eval.runner import BudgetExceeded, estimate, run
from llm_eval.task import Task, request_hash


class FakeClient:
    """Stands in for anthropic.Anthropic(). Answers 'yes' for payloads
    containing 'yes', with fixed token counts; can be told to fail items."""

    def __init__(self, fail=(), tokens_per_request=1000):
        self.calls = {"count_tokens": 0, "create": 0, "retrieve": 0,
                      "results": 0}
        self.fail = set(fail)
        self.tokens = tokens_per_request
        self.submitted = []
        outer = self

        class Batches:
            def create(self, requests):
                outer.calls["create"] += 1
                outer.submitted = requests
                return SimpleNamespace(id="batch_1")

            def retrieve(self, batch_id):
                outer.calls["retrieve"] += 1
                return SimpleNamespace(processing_status="ended")

            def results(self, batch_id):
                outer.calls["results"] += 1
                for req in outer.submitted:
                    text = req["params"]["messages"][0]["content"]
                    if text in outer.fail:
                        yield SimpleNamespace(custom_id=req["custom_id"],
                                              result=SimpleNamespace(
                                                  type="errored"))
                        continue
                    answer = "yes" if "yes" in text else "no"
                    yield SimpleNamespace(
                        custom_id=req["custom_id"],
                        result=SimpleNamespace(type="succeeded",
                                               message=SimpleNamespace(
                            content=[SimpleNamespace(type="text",
                                                     text=answer)],
                            stop_reason="end_turn",
                            usage=SimpleNamespace(input_tokens=outer.tokens,
                                                  output_tokens=100))))

        class Messages:
            batches = Batches()

            def count_tokens(self, **kwargs):
                outer.calls["count_tokens"] += 1
                return SimpleNamespace(input_tokens=outer.tokens)

        self.messages = Messages()


def toy_task(model="claude-haiku-4-5"):
    return Task(name="toy", model=model, max_tokens=50,
                build_request=lambda text: {
                    "messages": [{"role": "user", "content": text}]},
                parse=lambda raw, text: {"yes": 1, "no": 0}.get(raw),
                expected_output_tokens=100)


ITEMS = {"a": "yes please", "b": "no thanks", "c": "yes again"}


# --- pricing ---------------------------------------------------------------------

def test_cost_applies_prices_and_batch_discount():
    # haiku: $1 in / $5 out per MTok; 1M in + 1M out = $6, batch halves it.
    assert cost_usd("claude-haiku-4-5", 1_000_000, 1_000_000,
                    batch=False) == pytest.approx(6.0)
    assert cost_usd("claude-haiku-4-5", 1_000_000, 1_000_000) == \
        pytest.approx(3.0)


def test_unknown_model_is_never_priced_as_free():
    with pytest.raises(KeyError):
        cost_usd("claude-imaginary", 10, 10)


# --- request hashing -----------------------------------------------------------------

def test_request_hash_changes_with_the_prompt_and_is_a_valid_custom_id():
    t = toy_task()
    h1, h2 = request_hash(t.params("x")), request_hash(t.params("x "))
    assert h1 != h2                      # one character changes the version
    assert len(h1) == 64 and h1.isalnum()
    assert request_hash(t.params("x")) == h1     # deterministic


# --- runner -------------------------------------------------------------------------

def test_estimate_counts_tokens_for_free_and_prices_them(tmp_path):
    client = FakeClient()
    est = estimate(toy_task(), ITEMS, client=client, cache_dir=tmp_path)
    assert est["requests"] == 3 and est["input_tokens"] == 3000
    # 3000 in * $1 + 300 out * $5 = $0.0045, halved for batch
    assert est["estimated_cost_usd"] == pytest.approx(0.0045 / 2, abs=1e-4)
    assert client.calls["create"] == 0   # estimating sends nothing paid


def test_budget_guard_refuses_before_any_paid_call(tmp_path):
    client = FakeClient(tokens_per_request=10_000_000)
    with pytest.raises(BudgetExceeded):
        run(toy_task(), ITEMS, client=client, cache_dir=tmp_path,
            budget_usd=1.0, poll_seconds=0)
    assert client.calls["create"] == 0


def test_run_answers_items_and_reports_usage(tmp_path):
    client = FakeClient()
    out = run(toy_task(), ITEMS, client=client, cache_dir=tmp_path,
              budget_usd=1.0, poll_seconds=0)
    assert out["predictions"] == {"a": 1, "b": 0, "c": 1}
    assert out["failed"] == []
    assert out["usage"]["input_tokens"] == 3000
    assert client.calls["create"] == 1   # one batch for everything


def test_a_rerun_sends_nothing_and_costs_nothing(tmp_path):
    run(toy_task(), ITEMS, client=FakeClient(), cache_dir=tmp_path,
        budget_usd=1.0, poll_seconds=0)
    again = FakeClient()
    out = run(toy_task(), ITEMS, client=again, cache_dir=tmp_path,
              budget_usd=1.0, poll_seconds=0)
    assert out["predictions"] == {"a": 1, "b": 0, "c": 1}
    assert again.calls == {"count_tokens": 0, "create": 0, "retrieve": 0,
                           "results": 0}


def test_failed_items_are_not_cached_and_are_retried(tmp_path):
    first = run(toy_task(), ITEMS, client=FakeClient(fail={"no thanks"}),
                cache_dir=tmp_path, budget_usd=1.0, poll_seconds=0)
    assert first["failed"] == ["b"]
    retry = FakeClient()
    second = run(toy_task(), ITEMS, client=retry, cache_dir=tmp_path,
                 budget_usd=1.0, poll_seconds=0)
    assert second["predictions"]["b"] == 0
    assert len(retry.submitted) == 1     # only the failed item was resent


def test_an_interrupted_run_resumes_without_resubmitting(tmp_path):
    # Simulate a crash after submission: the state file exists and the
    # fake service still holds the submitted batch.
    client = FakeClient()
    task = toy_task()
    client.submitted = [{"custom_id": request_hash(task.params(t)),
                         "params": task.params(t)} for t in ITEMS.values()]
    (tmp_path / "_batch_state.json").write_text(
        json.dumps({"batch_id": "batch_1"}))
    out = run(task, ITEMS, client=client, cache_dir=tmp_path,
              budget_usd=1.0, poll_seconds=0)
    assert client.calls["create"] == 0   # resumed, not paid for twice
    assert out["predictions"] == {"a": 1, "b": 0, "c": 1}
    assert not (tmp_path / "_batch_state.json").exists()


def test_v1_task_builds_the_frozen_prompt_and_swaps_only_the_county():
    from news_collection import llm_classifier_v2 as clf
    from llm_eval.task import v1_local_relevance_task
    article = {"article_id": "x", "headline": "h", "text": "Council met.",
               "text_source": "t", "source_id": "s", "election_id": "e",
               "arm": "local", "day_index_from_polling_day": 40,
               "needs_reform_disambiguation": "no", "search_query_id": "",
               "ward": "", "query_text": "", "query_family": "",
               "geographic_scope": ""}
    surrey = v1_local_relevance_task("Surrey").params(article)
    kent = v1_local_relevance_task("Kent").params(article)
    s_text = surrey["messages"][0]["content"]
    k_text = kent["messages"][0]["content"]
    assert surrey["model"] == "claude-sonnet-5"
    assert "Surrey council" in s_text and "Kent council" in k_text
    assert k_text.replace("Kent", "Surrey") == s_text
    # The module-level definitions are restored after building.
    assert "Surrey council" in json.dumps(clf.REASON_CODE_DEFINITIONS)
