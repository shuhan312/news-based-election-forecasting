"""End-to-end tests for llm_eval's pipeline, report and command line.

The first test runs the committed local-relevance config and checks the
toolkit's acceptance criteria in one go. The others build a small toy task
in a temporary folder and drive it through the API path with a fake client,
so no network, key or money is involved.
"""

import csv
import json
from types import SimpleNamespace

import pytest

from llm_eval import cli, pipeline, report
from llm_eval.task import Task

CONFIG = "configs/llm_eval/local_relevance.toml"


# --- acceptance: the committed config reproduces V2's results ------------------------

def test_committed_config_reproduces_b0_and_the_audit_findings():
    result = pipeline.run_pipeline(pipeline.load_config(CONFIG))
    assert result["overall"]["kappa"] == 0.7031
    assert result["overall"]["recall"] == 0.8333
    assert result["gate"]["pass"]
    checks = {f["check"] for f in result["audit"]["flags"]}
    assert checks == {"rule_consistency", "base_rate_drift", "provenance"}
    md = report.to_markdown(result)
    assert "PASS, with 3 reference-label audit flags" in md
    assert "31 of 39 labels" in md


# --- a toy task for the API path ---------------------------------------------------

class FakeClient:
    """Minimal fake Anthropic client: says 'yes' when the text contains 'good'."""

    def __init__(self):
        self.created = 0
        outer = self

        class Batches:
            def create(self, requests):
                outer.created += 1
                outer.requests = requests
                return SimpleNamespace(id="b1")

            def retrieve(self, batch_id):
                return SimpleNamespace(processing_status="ended")

            def results(self, batch_id):
                for r in outer.requests:
                    text = r["params"]["messages"][0]["content"]
                    yield SimpleNamespace(
                        custom_id=r["custom_id"],
                        result=SimpleNamespace(type="succeeded",
                                               message=SimpleNamespace(
                            content=[SimpleNamespace(
                                type="text",
                                text="yes" if "good" in text else "no")],
                            stop_reason="end_turn",
                            usage=SimpleNamespace(input_tokens=100,
                                                  output_tokens=5))))

        class Messages:
            batches = Batches()

            def count_tokens(self, **kwargs):
                return SimpleNamespace(input_tokens=100)

        self.messages = Messages()


@pytest.fixture
def toy(tmp_path, monkeypatch):
    """A labelled CSV, a toy task and a toy payload loader, all registered."""
    rows = [("1", "good news", "pos"), ("2", "bad news", "neg"),
            ("3", "good day", "pos"), ("4", "plain", "pos")]
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["id", "text", "label"])
        w.writerows(rows)
    texts = {i: t for i, t, _ in rows}
    monkeypatch.setitem(pipeline.TASKS, "toy", lambda: Task(
        name="toy", model="claude-haiku-4-5", max_tokens=5,
        build_request=lambda t: {"messages": [{"role": "user",
                                               "content": t}]},
        parse=lambda raw, t: {"yes": 1, "no": 0}.get(raw),
        expected_output_tokens=5))
    monkeypatch.setitem(pipeline.PAYLOADS, "toy",
                        lambda ids: {i: texts[i] for i in ids})
    cfg = {
        "task": {"name": "toy", "classifier": "toy",
                 "classifier_is_llm": True},
        "labels": [{"path": str(labels), "origin": "batch", "provenance":
                    "human", "id_col": "id", "label_col": "label",
                    "positive": "pos", "negative": "neg"}],
        "split": {"salt": "s", "evaluate": "test"},
        "predictions": {"source": "api", "budget_usd": 1.0,
                        "cache_dir": str(tmp_path / "cache"),
                        "poll_seconds": 0, "payloads": {"loader": "toy"}},
        "output": {"dir": str(tmp_path / "out")},
    }
    return cfg


def test_api_path_runs_scores_and_reports_cost(toy):
    client = FakeClient()
    result = pipeline.run_pipeline(toy, client=client)
    assert client.created == 1
    assert result["run"]["source"] == "api"
    assert result["run"]["usage"]["input_tokens"] > 0
    assert result["audit"]["clean"]          # human labels, no flags
    md, js = report.write(result, toy["output"]["dir"])
    assert "## Cost" in md.read_text()
    assert json.loads(js.read_text())["task"] == "toy"


def test_api_path_needs_a_client(toy):
    with pytest.raises(ValueError):
        pipeline.run_pipeline(toy, client=None)


def test_same_id_in_two_batches_is_rejected(toy):
    toy["labels"].append(dict(toy["labels"][0], origin="again"))
    with pytest.raises(ValueError):
        pipeline.load_examples(toy)


# --- command line -------------------------------------------------------------------

def test_cli_audit_exits_nonzero_on_flags(capsys):
    assert cli.main(["audit", "--config", CONFIG]) == 1
    assert "rule_consistency" in capsys.readouterr().out


def test_cli_run_writes_the_report(tmp_path):
    text = open(CONFIG).read().replace(
        'dir = "v2_design/llm_eval_example"', f'dir = "{tmp_path}"')
    cfg = tmp_path / "cfg.toml"
    cfg.write_text(text)
    assert cli.main(["run", "--config", str(cfg)]) == 0
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "results.json").exists()
