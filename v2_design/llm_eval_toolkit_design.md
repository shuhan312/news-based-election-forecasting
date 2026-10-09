# `llm_eval`: design of a reusable LLM classification evaluation toolkit

**2026-10-09. Design document, written before any toolkit code.**

## Why

V2's LLM evaluation work is real, but it lives in one-off scripts and in
findings documents:

- the label audit that showed V1's "local classifier failure" was mostly
  reference labels applying the wrong rule set was ad hoc code in a
  conversation, and **cannot be re-run from the repository**;
- the batch runner, cost estimate and metrics are hard-wired into single
  experiments (`outlet_pilot.py`, `local_relevance_eval.py`);
- **there are no tests** for any V2 code.

`llm_eval` turns those capabilities into one package, with a stable
interface, offline tests and a single command, so that any LLM
classification task can be evaluated the same way. The local-relevance task
is the worked example that proves it.

## What it does: one command, six stages

```bash
python -m llm_eval run --config configs/llm_eval/local_relevance.toml
```

| stage | does | why it matters |
|---|---|---|
| 1. **load** | reads examples and reference labels, recording each label's provenance (`human`, `ai_assisted`, `model`) | a reference standard's independence decides what agreement means |
| 2. **audit** | checks the reference labels before any model is scored (rules below) | V2's main finding: the "model failure" was in the labels |
| 3. **estimate** | exact input tokens via the free token-counting endpoint, then cost from a price table, with the batch discount applied | the cost is known before anything is spent |
| 4. **run** | sends requests (Batches API by default), **refuses** if the estimate exceeds the configured budget, caches each answer by (example, prompt hash, model), and resumes after failure | a rerun never pays twice; nothing is spent past the budget |
| 5. **score** | kappa, precision, recall, F1, agreement, each with a bootstrap 95% CI, overall and per subgroup | subgroup breakdown is how the V1 failure was localised |
| 6. **report** | writes one Markdown page and one JSON file | readable by a person, diffable by a machine |

Predictions can also come from an archived file instead of the API
(`source = "archived"`). That is how V1's frozen classifier is scored at no
cost.

## Package layout (`src/llm_eval/`)

| module | content | origin |
|---|---|---|
| `dataset.py` | `Example` record; CSV loader; salted-hash dev/test split | `local_relevance_split.py`, `local_relevance_eval.py` |
| `task.py` | `Task`: prompt builder, output schema, model, label parser; prompt hash for versioning | wraps V1's frozen classifier |
| `pricing.py` | per-model input/output prices; batch discount | price table, 2026-09-25 |
| `runner.py` | `estimate()`; `run()` with budget guard, batch submit/poll/collect, answer cache | `outlet_pilot.py` count/submit/collect, generalised |
| `metrics.py` | kappa, precision, recall, F1, bootstrap CIs, subgroup scores | `local_relevance_eval.py` |
| `audit.py` | label audit rules (below) | **new**: this session's audit, made reusable |
| `report.py` | Markdown and JSON report | new |
| `cli.py`, `__main__.py` | `run`, plus the single stages `audit`, `estimate`, `score` | new |

The config is TOML, read with the standard library's `tomllib`. **No new
dependency.**

## Label audit rules

1. **Rule-set consistency.** Each label carries a reason code. The config
   maps each stratum (e.g. `arm=local`) to the reason-code families it may
   use (e.g. `E5-L*`). Labels justified by a family outside their stratum are
   flagged. This is exactly the V1 defect: 31 of 39 local includes justified
   by national N-rules.
2. **Base-rate drift between label batches.** The include rate is compared
   across label batches (origins) within the same source. A large gap is
   flagged: V1's validation batch included 83% of Guardian local articles,
   the later batch 19%.
3. **Provenance warning.** If the reference labels are `ai_assisted` and the
   classifier is an LLM, the report states that agreement is not an
   independent validation.

## Tests (`tests/test_llm_eval_*.py`, all offline)

| test | proves |
|---|---|
| metrics on hand-computed cases | kappa, precision, recall and F1 are correct, including edge cases (no positives) |
| split is deterministic and label-stratified | the same ids always land in the same split |
| audit flags an injected rule mismatch and an injected base-rate gap, and stays silent on clean data | the audit finds what it claims to, without false alarms |
| budget guard refuses an over-budget run | no spend past the limit |
| cache prevents a second request for the same (example, prompt, model) | reruns are free |
| batch runner against a fake client | submit/collect works with no network or key |

## Acceptance criteria (the toolkit is done when)

1. One command reproduces V2's B0 result from archived outputs **exactly**:
   test kappa 0.7031, include recall 0.8333 (`local_relevance_v1/baseline_b0.json`).
2. The audit, run on V1's labels, reproduces the finding: the
   local-arm/N-rule mismatch in the validation batch, and the base-rate gap.
3. All tests pass offline, with no API key.
4. A run against the API states its estimated cost and refuses one over
   budget.

## Out of scope

Prompt optimisation, multi-model comparison runs and a UI. The toolkit
evaluates; it does not tune. Direction 1 will use it for its news module.

## Estimated effort

About a week: dataset/metrics/audit (1–2 days), runner/pricing (1–2 days),
CLI/report/config (1 day), tests and acceptance (1–2 days).
