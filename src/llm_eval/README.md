# llm_eval

Evaluate an LLM classification task end to end, with one command:

```bash
PYTHONPATH=.:src python -m llm_eval run --config configs/llm_eval/local_relevance.toml
```

| stage | what it does |
|---|---|
| load | reads reference labels, recording each label's provenance and labelling batch |
| **audit** | checks the reference labels **before** any model is scored: rule-set consistency, base-rate drift between batches, AI-assisted provenance |
| estimate | exact input tokens via the free token-counting endpoint, priced at the batch rate |
| run | Message Batches API at half price; **refuses to start over budget**; caches by request hash, so a rerun costs nothing; resumes an interrupted batch |
| score | kappa, precision, recall, F1, agreement, with bootstrap 95% CIs, overall and by subgroup |
| report | `report.md` (verdict, audit, scores) and `results.json` |

Other commands: `audit` (labels only, free) and `estimate` (cost only, free).

## Why the audit comes first

On this project a recorded "classifier failure" (kappa 0.165) turned out to
come mostly from the reference labels: 31 of 39 positives were justified by a
rule set the codebook forbids for that stratum. The audit now finds this
automatically. See the worked example in `v2_design/llm_eval_example/report.md`.

## Adding a task

Register a `Task` factory in `pipeline.TASKS` (how to build a request, how to
parse an answer) and, for API runs, a payload loader in `pipeline.PAYLOADS`.
Then write a TOML config. The stages themselves do not change.

## Tests

```bash
.venv/bin/python -m pytest tests/test_llm_eval_*.py -q   # 29 tests, offline
```

They include acceptance tests on committed data: the toolkit reproduces the
earlier B0 result exactly (test kappa 0.7031) and rediscovers the labelling
defect. API behaviour (budget guard, cache, retry, resume) is tested against a
fake client, with no key and no cost.
