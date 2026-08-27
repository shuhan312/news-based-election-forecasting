# Surrey no-news baseline

Stage 1 of the IRP: predict each candidate's vote share in a Surrey county
division using **only information that existed before polling day**, with no
news of any kind. Reform UK is the study party and is reported separately
throughout; Reform UK and UKIP are never merged, and no UKIP observation is
ever treated as evidence about Reform.

This is the supervisor's central comparator — what the news layer must beat.
Its output is a versioned **model bundle** whose out-of-fold predictions are
the news stage's input.

It is a sibling of `surrey-election-extractor`, not a separate Git repository.
The two have different responsibilities:

- `surrey-election-extractor` owns official-source extraction, provenance,
  derived/analysis governance, and publication of model-input contracts;
- `surrey-election-no-news-baseline` owns features, splits, models, metrics
  and the exported bundle.

The modelling layer never edits official election data and never imports the
extractor's internal modules. It reads published JSON contracts, with features
and targets in separate files as a structural leakage control:

```text
surrey-election-extractor/outputs/no_news_candidate_contests/
├── no_news_candidate_contest_features.json
└── no_news_candidate_contest_targets.json
```

---

## 1. The main line

From the repository root, with the project virtualenv active. If the shared
`.venv` at the repository root does not exist yet, create it first as shown in
`surrey-election-extractor/README.md` (`python3 -m venv .venv`, then
`pip install -r` each subproject's `requirements.txt`):

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m no_news_baseline.cli train
```

That reads `config/baseline_model.yaml`, scores three architectures on every
chronological fold, selects one, fits it, and writes the bundle to
`outputs/model_bundle_v1/`. It takes a few minutes.

Before a long run, check what it is about to do — both commands are instant:

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m no_news_baseline.cli config
```

`config` prints the **resolved** settings, after the file and any flags have
been applied, so an override that did not take effect is visible before
anything is fitted. `validate` checks a file and exits.

### The six-page interface

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m streamlit run surrey-election-no-news-baseline/app/streamlit_app.py
```

Upload and validation, model configuration, training, results, explainability
and export. The app **reads bundles and invokes the CLI**; it never extracts
from the workbook and never fits a model in-process, so every figure it shows
came from a command that can be re-run. Training is launched as a subprocess
with its log streamed to the page.

If the contract is missing or stale, regenerate it first:

```bash
PYTHONPATH=surrey-election-extractor .venv/bin/python surrey-election-extractor/scripts/generate_no_news_candidate_contests.py
```

Dependencies: `numpy`, `lightgbm`, `pyyaml`, `pytest`, and `streamlit`, `pandas` and `openpyxl` for the interface. LightGBM is required —
Architecture B is a comparator the brief asks for, and a missing comparator
that failed quietly would let the comparison report two architectures while
claiming three were tried.

### Reproduce the bundle from scratch

From the repository root, with the `.venv` active, in order:

```bash
# 1) Regenerate the candidate contract this package reads (from the extractor)
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_candidate_contests.py

# 2) Emit the split manifest and leakage audit the bundle copies in
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  surrey-election-no-news-baseline/scripts/build_candidate_split_and_leakage.py

# 3) Fit and export the model bundle (a few minutes)
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m no_news_baseline.cli train

# 4) Run the parameter-free benchmarks (the floor the model must clear)
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  surrey-election-no-news-baseline/scripts/run_persistence_benchmark.py
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  surrey-election-no-news-baseline/scripts/run_naive_benchmarks.py

# 5) Confirm nothing is broken
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m pytest surrey-election-no-news-baseline/tests -q
```

Reproduction is confirmed when step 3 logs out-of-fold MAE 9.85 and holdout MAE
4.53, and step 5 reports 444 passing tests. Step 2 matters on a fresh clone:
the bundle builder copies `split_manifest.csv` and `leakage_audit.csv` into
the bundle when they exist and warns otherwise, so emitting them first keeps
the bundle complete.

Every other product under `outputs/` regenerates the same way through its
runner in the file guide below — the uniform pattern is
`PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python
surrey-election-no-news-baseline/scripts/<runner>.py` (for example
`run_model_comparison.py`,
`build_electoral_fundamentals_release.py`).

---

## 2. Complete file guide, grouped by function

### 2.1 The shipped candidate model — core path

The CLI is the public entry point; it delegates the complete training run to
the bundle builder. These are the files needed to understand Stage 1 in the
final report.

| Role | Main file |
| --- | --- |
| Command entry point | `no_news_baseline/cli.py` |
| Complete Stage 1 orchestration and bundle export | `scripts/build_candidate_model_bundle.py` |
| Chronological folds and holdouts | `no_news_baseline/candidate_splits.py` |
| Predictor permission and leakage rules | `no_news_baseline/candidate_leakage_audit.py` |
| 35 predictors to 127 encoded inputs | `no_news_baseline/candidate_features.py` |
| Ridge architecture | `no_news_baseline/candidate_share_model.py` |
| Partial-pooling architecture | `no_news_baseline/candidate_hierarchical_model.py` |
| LightGBM architecture selected for the final baseline | `no_news_baseline/candidate_boosted_model.py` |
| Three-architecture comparison and selection gates | `no_news_baseline/candidate_architecture_selection.py` |
| Candidate, party and Reform UK metrics | `no_news_baseline/candidate_metrics.py` |
| Contest ranking and seat projection | `no_news_baseline/candidate_seat_projection.py` |
| Frozen modelling assumptions | `config/baseline_model.yaml` |

The execution path is:

```text
no_news_baseline/cli.py
    -> scripts/build_candidate_model_bundle.py
    -> splits + leakage audit + feature encoder
    -> Ridge / partial pooling / LightGBM comparison
    -> selected LightGBM fit
    -> outputs/model_bundle_v1/
```

### 2.2 The shipped candidate model — supporting modules

| File | Role |
| --- | --- |
| `candidate_cohort.py` | estimand, cohort membership, within-contest normalisation, ranking and seat allocation |
| `candidate_data_validation.py` | seat-count and polling-date validation of the modelling contract |
| `candidate_contestation.py` | non-contestation records — a party that did not stand has no row and is never recorded as a zero |
| `candidate_evidence_layers.py` | which evidence layer (official / derived / analysis) each field came from |
| `candidate_historical_strength.py` | county-level historical party-strength predictors |
| `candidate_interactions.py` | Reform UK interaction terms and the labelled, off-by-default UKIP block |
| `candidate_probability_model.py` | separately fitted probability of election with a seat-count constraint |
| `candidate_explainability.py`, `candidate_tree_explainability.py` | SHAP, fold-level coefficients and unstable features; tree-specific explanations for the shipped Architecture B |
| `architecture_paired_bootstrap.py` | paired-bootstrap uncertainty for the architecture comparison |
| `configuration.py` | resolves flags → file → defaults and records the result in the bundle |
| `logging_setup.py` | training-run logging, and the one rule about what may be logged |
| `scripts/build_candidate_cohort_report.py`, `scripts/build_candidate_split_and_leakage.py` | cohort/fold report; standalone split-manifest and leakage-audit emitters |

### 2.3 Parameter-free benchmarks (the floor a model must clear)

| File | Role |
| --- | --- |
| `persistence_benchmark.py` | main baseline: previous exact-label party share and previous unique winner |
| `naive_benchmarks.py` | equal-split and party-historical-mean references (measure what area identity is worth) |
| `benchmark_metrics.py` | shared MAE / RMSE / accuracy scoring for every benchmark |
| `temporal_validation.py` + `temporal_validation_report.py` | leakage-safe temporal folds and the fold-by-fold benchmark report |
| `election_dates.py` | shared election-date parsing and ordering |
| `scripts/run_persistence_benchmark.py`, `scripts/run_naive_benchmarks.py`, `scripts/run_temporal_validation_report.py` | benchmark runners |

### 2.4 Earlier party-level groundwork (electoral fundamentals; completed, retained as development evidence)

The one-row-per-election-area-party feature table behind the earlier
party-level models. The shipped Stage 1 is the candidate-level model above;
this layer is kept because the development sequence it records is part of the
project's evidence trail.

| File | Role |
| --- | --- |
| `electoral_fundamentals_schema.py`, `electoral_fundamentals_rows.py`, `electoral_fundamentals_builder.py` | table shape and leakage boundary; row index; assembly with the leakage contract checked |
| `electoral_fundamentals_structure.py`, `electoral_fundamentals_history.py`, `electoral_fundamentals_participation.py`, `electoral_fundamentals_ukip.py`, `electoral_fundamentals_previous_party_zero.py` | one feature class each: contest structure, approved history, participation/incumbency, the separate UKIP context field, and proven previous-party zeros |
| `electoral_fundamentals_release.py`, `electoral_fundamentals_report.py` | the release package (predictors and outcomes in separate allow-lists) and its quality report |
| `regularised_models.py` | the first fitted no-news model: fold-wise ridge on the fundamentals table, kept as a member of the four-way model comparison |
| `model_input_preprocessing.py` | missing-value semantics added without changing source values |
| `independent_previous_share_audit.py` | Independents audited as ballot descriptions, not one continuing party |
| `scripts/build_electoral_fundamentals_release.py`, `scripts/build_model_input_contract.py`, `scripts/generate_independent_previous_share_audit.py` | release and contract runners |

### 2.5 Diagnostics, comparisons and scoping audits

| File | Role |
| --- | --- |
| `cold_start_model.py` | N4: coverage-expanding cold-start baseline for rows with no historical predecessor |
| `coverage_evaluation.py`, `coverage_report.py` | coverage-aware evaluation of how much of the release each model scores |
| `model_comparison.py` | every no-news model compared on one identical, shared contest set |
| `supervisor_alignment.py` + `scripts/build_supervisor_alignment.py` | the three Stage 1 artefacts the supervisor's prompt asks for |
| `scripts/run_cold_start_report.py`, `scripts/run_coverage_report.py`, `scripts/run_model_comparison.py` | diagnostic runners |

### 2.6 Interface and support

| Location | Role |
| --- | --- |
| `app/streamlit_app.py`, `app/loaders.py`, `app/views.py` | the six-page interface: entry point, bundle/contract loading, and the pages; it reads bundles and invokes the CLI, never fitting in-process |
| `config/baseline_model.yaml` | every tunable assumption with its reasoning (see Configuration below) |
| `config/electoral_feature_metadata.csv` | feature field metadata for the fundamentals release |
| `outputs/` | products only — regenerated from versioned code and extractor contracts, excluded from Git |
| `tests/` | 444 tests, roughly one per module; the ones that matter most assert that something *fails* |

---

## What the model does

**Target.** `analysis_vote_share` — a candidate's votes as a share of all
votes cast in that contest. It is fitted on a transformed scale, `share ×
candidates ÷ 100`, which equals 1.0 for a candidate polling exactly an equal
share. Single-member and two-member contests are otherwise on different
scales, and a model fitted across both without the transform learns the seat
count rather than the politics.

**Predictions.** Candidate vote share, then rank within the contest, then
elected status by taking the top *N* where *N* is the known pre-election seat
count, then a probability of election shifted in log-odds until each contest's
probabilities sum to its seats.

**Split.** Strictly chronological and date-bounded, never random. The grouping
unit is `election_id + division_id`, so candidates from one contest are never
separated. Four named development folds, twelve rolling-origin folds, one
**primary holdout** (everything polled on 7 May 2026, treated as a single
period so no same-day event trains on another), and a **secondary holdout**
(Haslemere, 7 July 2026) evaluated both with and without the May results.

**Leakage.** Every column is classified in `candidate_leakage_audit.py` with
the event that first makes it available. Anything derived from the election
being predicted — votes, shares, turnout, winning margin, change in vote share
— is prohibited, and a test fails if one reaches the feature matrix.

---

## Configuration

`config/baseline_model.yaml` holds every tunable assumption with the reasoning
beside it. Each value is also a default in code, so the file can be shortened
to only what you want to change; it ships complete because a configuration a
reader has to reconstruct from source is not a configuration. A test asserts
the file still matches the code defaults, so the two cannot drift apart
silently.

**An unrecognised key stops the run.** A silently ignored typo is the worst
failure mode a configuration file has: the run reports success, the setting
never applied, and nothing records the difference.

Precedence is **command-line flags → file → code defaults**, and the resolved
result is written into the bundle, so a bundle always records what it was
actually built with.

### Selecting an architecture

`selection.mode: auto` runs two gates in complexity order, simplest first. A
challenger must improve Reform UK vote-share MAE by more than 5 per cent *and*
lose on no more than one development fold. Setting `mode` to an architecture
name ships that one instead — the brief's manual mode:

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m no_news_baseline.cli train --architecture C_partial_pooling --output surrey-election-no-news-baseline/outputs/model_bundle_manual_c
```

A manual choice does **not** suppress the comparison. All architectures are
still scored, `architecture_comparison.csv` is still written, and
`architecture.json` records `"overridden": true` beside the verdict the gates
would have reached. An override that erased what it overrode would be
indistinguishable from a selection.

### The UKIP sensitivity run

The brief permits UKIP as a separate contextual feature: clearly labelled, off
by default, and compared against a model that does not use it.

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m no_news_baseline.cli train --ukip-interactions --output surrey-election-no-news-baseline/outputs/model_bundle_ukip
```

This adds UKIP's own interaction columns and nothing else. It does not merge
UKIP into Reform UK.

---

## The bundle

`outputs/model_bundle_v1/` — 29 files. The ones to read first:

| file | what it answers |
| --- | --- |
| `model_card.md` | what the model is, and what it may not be used for |
| `metrics.json` | every metric, broken down by election, party and contest type |
| `reform_metrics.json` | Reform UK separately, plus each rejected architecture's Reform figures |
| `architecture.json` | which architecture, chosen how, on how much evidence |
| `architecture_comparison.csv` | all three on every fold, so the rejected ones stay visible |
| `leakage_audit.csv` | every field, permitted or excluded, and why |
| `split_manifest.csv` | which fold every row belongs to |
| `out_of_fold_predictions.csv` | **Stage 2 training input**: historical out-of-fold predictions used to construct residual targets |
| `holdout_predictions.csv` | **Stage 2 prediction input**: the frozen 2026 Stage 1 baseline to which news adjustments are added |
| `holdout_seat_projection.csv` | predicted winning party per contest, against the actual |
| `holdout_party_seat_totals.csv` | predicted seats per party, against the actual |
| `explainability.json` | SHAP, fold-level coefficients, unstable features, worked examples |
| `data_quality_report.json` | missingness by field and election, party counts by election |
| `training_config.yaml` | the resolved configuration this bundle was built with |
| `bundle_manifest.json` | SHA-256 of every file, so a later stage can prove which bundle it loaded |

`training.log` is appended to on each run and is excluded from the manifest
hashes, being written while the manifest is computed.

The manifest hashes **only the files the run actually wrote**. An output
directory is reused across rebuilds, and a file left behind by an older
version would otherwise be hashed in as though the current code had produced
it — a bundle claiming files a rebuild cannot recreate. Anything else found in
the directory is logged as a warning and listed under
`files_not_written_by_this_run`.

### Hand-off to the news stage

Stage 1 ends at the model bundle. Stage 2 is implemented outside this
subproject in `src/news_modelling/`:

```text
outputs/model_bundle_v1/out_of_fold_predictions.csv
    -> historical residual targets for Stage 2 fitting

outputs/model_bundle_v1/holdout_predictions.csv
    -> frozen 2026 no-news baseline

both files
    -> src/news_modelling/stage1_bundle.py
    -> run_blinded_2026_predictions.py / run_blinded_2026_predictions_v2.py
    -> news_features/blinded_2026_predictions_v1/ / _v2/
```

`stage1_bundle.py` validates the required files, split roles and bundle
integrity before the news model can use them. The bundle is local/generated
output, while its code, configuration and documentation are versioned.

---

## Naive comparators

Three parameter-free benchmarks exist so that any learned model's advantage
can be attributed to something. They remain runnable and their results remain
the floor a model has to clear:

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python surrey-election-no-news-baseline/scripts/run_persistence_benchmark.py
```

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python surrey-election-no-news-baseline/scripts/run_naive_benchmarks.py
```

`previous_result_persistence_v1` predicts the previous approved party share
and the previous winner where political identity transfers safely: 9.50 MAE
percentage points and 80.5 per cent area accuracy over 775 rows in 177
approved single-member areas. Party identity alone reaches 10.43, and an
uninformed equal split only 15.60 — area identity adds much less to the share
estimate than it does to the winner call. See
[`docs/persistence_benchmark.md`](docs/persistence_benchmark.md) and
[`docs/naive_benchmarks.md`](docs/naive_benchmarks.md).

These are party-level and single-member-only, so they are not directly
comparable with the candidate-level model's headline figures; the candidate
model carries its own equal-split reference in every metric block.

---

## Tests

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m pytest surrey-election-no-news-baseline/tests -q
```

444 tests. The ones that matter most assert that something *fails*: a
prohibited field entering the design matrix, a contest split across folds, a
7 May 2026 row reaching training, an unknown value silently becoming zero or
"No", a UKIP block without its Reform base, a configuration key that does not
exist, a seat count larger than the number of candidates, an election with two
polling dates, a published column with no evidence layer. All six Streamlit
pages are rendered headlessly on every run.

---

## Documentation

`docs/` carries the record of what was tried and what it showed, including the
results that did not work:

- [`candidate_level_estimand.md`](docs/candidate_level_estimand.md) — why the
  unit is the candidate, not the party
- [`candidate_split_and_leakage.md`](docs/candidate_split_and_leakage.md) —
  the split design and the leakage audit
- [`candidate_model_card.md`](docs/candidate_model_card.md) — the shipped
  model card
- [`historical_strength_features.md`](docs/historical_strength_features.md) —
  county-level history, and the damage it did to the linear architectures
  before the interactions fixed it
- [`reform_interaction_terms.md`](docs/reform_interaction_terms.md) — the
  interaction experiment, and the underpowered selection design it exposed
- [`ukip_contextual_sensitivity.md`](docs/ukip_contextual_sensitivity.md) —
  the UKIP block run, compared against a model without it, and why it is not
  selected
- [`architecture_selection_evidence.md`](docs/architecture_selection_evidence.md)
  — all three architectures on every split role, what selecting B bought and
  what it cost
- [`run_configuration_and_reproducibility.md`](docs/run_configuration_and_reproducibility.md)
  — the configuration design, and the manifest defect a clean rebuild exposed
- [`technical_report.md`](docs/technical_report.md) — **the concise report for
  the supervisor review**, and the three decisions it asks for
- [`prompt1_compliance_audit.md`](docs/prompt1_compliance_audit.md) — every
  requirement and where it lives, and the seat projection showing Reform
  predicted 0 seats against 12 won
- [`data_validation_and_evidence_layers.md`](docs/data_validation_and_evidence_layers.md)
  — seat and date validation, and why two thirds of the model's inputs are
  derived rather than official
- [`stage2_feasibility_findings.md`](docs/stage2_feasibility_findings.md) —
  what Stage 1 implies for the news layer
- [`cold_start_baseline.md`](docs/cold_start_baseline.md) — the N4 cold-start
  benchmark for rows with no historical predecessor
- [`coverage_aware_evaluation_methodology.md`](docs/coverage_aware_evaluation_methodology.md)
  — how much of the release each model actually scores, and why that matters
- [`data_contract.md`](docs/data_contract.md) — the ownership boundary between
  the extractor's published contract and this package
- [`electoral_feature_release.md`](docs/electoral_feature_release.md) — the
  frozen fundamentals feature-engineering release
- [`naive_benchmarks.md`](docs/naive_benchmarks.md) and
  [`persistence_benchmark.md`](docs/persistence_benchmark.md) — the
  parameter-free benchmark results

Everything under `outputs/` is regenerated from versioned code and extractor
contracts and is excluded from Git. Code, tests, configuration, documentation
and research decisions are version controlled.

---

## Limitations worth knowing before reading any number

- **Reform UK's pre-2026 sample is fourteen distinct rows** across the
  development folds. Every Reform-specific development figure rests on that,
  and `reform_metrics.json` carries a `small_sample_warning` flag for it.
- **Selection and the holdout disagree.** The pooled development folds select
  Architecture B; on the primary holdout Architecture C is clearly better.
  This is reported rather than resolved — choosing on the holdout would spend
  it. It means the development evidence cannot reliably separate the two.
- **The holdout is not blind.** Its metrics were read during development. No
  2026 row entered training and no hyperparameter was chosen against it, but
  the discipline was weaker than the design intended. Disclosed in the model
  card.
- The model predicts statistical patterns in aggregate results. It does not
  establish why any individual voted as they did.
