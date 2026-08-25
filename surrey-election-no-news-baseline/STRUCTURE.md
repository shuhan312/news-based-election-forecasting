# Directory guide (STRUCTURE)

> A map for navigating this package quickly. It is documentation only and takes no part in running the code.
> In one line: **this package only does prediction and evaluation. It reads the contract JSON produced by the extractor and never modifies the official election data.**

## Overview: benchmarks + the shipped candidate model + groundwork + support

| Group | What it does | Role |
| --- | --- | --- |
| **A. benchmarks** | Run parameter-free rules and report prediction accuracy | The floor a model must clear |
| **D. candidate model** | Fit and evaluate the candidate-level vote-share model, select an architecture, export the bundle | **The shipped Stage 1 model — primary holdout and viva focus** |
| **B. fundamentals** | Build a one-row-per-election-area-party feature table | Earlier party-level groundwork |
| **C. model input** | Add missing-value semantics and audit Independents | Finishing step for B |
| Support | scripts / config / docs / outputs / tests | Runners, evidence, docs, products, tests |

Data flow: `extractor no-news contract JSON` → **D (fits the shipped model, produces the bundle)** and A (produces the benchmark floor); B → C build the earlier party-level feature table.

---

## A. benchmarks — baseline evaluation (produces results; viva focus)

Parameter-free: nothing is trained or tuned; a naive rule is run to see how accurate it is on its own.

| File | Role | Importance |
| --- | --- | --- |
| `persistence_benchmark.py` | **Main baseline**: predicted share = previous exact-label party share; predicted winner = previous unique winner | Core |
| `naive_benchmarks.py` | Two references: equal split / party historical mean (ignore area identity, to measure how much local information is worth) | Core |
| `benchmark_metrics.py` | Shared scoring (MAE / RMSE / accuracy) used by both of the above | Support |
| `temporal_validation.py` | Temporal check: confirms every prediction uses only pre-election data (guards against future-information leakage) | Important |
| `election_dates.py` | Election-date ordering logic shared by the above (avoids each copy re-parsing dates and drifting into bugs) | Support |

**Products**: `outputs/persistence_benchmark/`, `outputs/naive_benchmarks/`
**Result write-ups**: `docs/persistence_benchmark.md`, `docs/naive_benchmarks.md`

---

## B. fundamentals — feature-table construction (groundwork; in progress / future work)

Builds an "electoral fundamentals" table: one row per election-area-party, carrying predictors that were known before the election. One module = one class of feature.

**The three-part skeleton (read these three first to understand the shape)**

| File | Role |
| --- | --- |
| `electoral_fundamentals_schema.py` | Defines the table shape first (unit of analysis, leakage boundary); holds no data yet |
| `electoral_fundamentals_rows.py` | Builds rows: one per election × area × party |
| `electoral_fundamentals_builder.py` | Assembles the feature modules in a fixed order, then checks the leakage contract |

**Each adds one class of feature**

| File | Feature it adds |
| --- | --- |
| `electoral_fundamentals_structure.py` | Election type, seat count, number of candidates |
| `electoral_fundamentals_history.py` | Historical result from the approved comparable previous area |
| `electoral_fundamentals_participation.py` | Candidate history, incumbency, approved local party history |
| `electoral_fundamentals_ukip.py` | For a Reform UK target row, records UKIP's previous share as a separate field (kept distinct, not merged) |
| `electoral_fundamentals_previous_party_zero.py` | One-sided inference proving a party scored zero in a new ward |

**Finishing / reporting**

| File | Role |
| --- | --- |
| `electoral_fundamentals_release.py` | Produces 3 CSVs + a quality report in one pass; predictor and outcome columns are kept in separate allow-lists (leakage control) |
| `electoral_fundamentals_report.py` | Generates the feature-table quality report |

**Product**: `outputs/electoral_fundamentals/`

---

## C. model input — finishing step

| File | Role |
| --- | --- |
| `model_input_preprocessing.py` | Adds a missing flag, applicability flag and reason to each nullable predictor, without changing the source values |
| `independent_previous_share_audit.py` | Audits Independents (a ballot description, not one continuing party, so it is not carried forward as a single party) |

**Product**: `outputs/model_input_contract/`

---

## D. candidate-level model — the shipped Stage 1 model (viva focus)

The candidate model the bundle ships. Its estimand is each candidate's vote
share (candidate votes ÷ contest total), so it can be scored on the 7 May 2026
two-member wards where a party share is undefined; the primary holdout lives
here, and the A benchmarks are its floor. Read in pipeline order.

**Estimand, cohort and data**

| File | Role |
| --- | --- |
| `candidate_cohort.py` | The estimand, cohort membership, within-contest normalisation, ranking and seat allocation |
| `candidate_data_validation.py` | Seat-count and polling-date validation of the release |
| `candidate_contestation.py` | Non-contestation records — a party that did not stand has no row and is never recorded as a zero |
| `candidate_evidence_layers.py` | Which evidence layer (official / derived / analysis) each field came from |

**Split**

| File | Role |
| --- | --- |
| `candidate_splits.py` | Date-based chronological splits: named development folds, rolling-origin folds, the 7 May 2026 primary holdout and the Haslemere secondary holdout |

**Features**

| File | Role |
| --- | --- |
| `candidate_features.py` | Assembles the permitted-predictor design matrix |
| `candidate_historical_strength.py` | County-level historical party-strength predictors |
| `candidate_interactions.py` | Interaction terms, including the optional off-by-default UKIP block |

**Leakage audit (the crown jewel)**

| File | Role |
| --- | --- |
| `candidate_leakage_audit.py` | Classifies all published columns; only permitted ones may be modelled; the build fails if a prohibited column reaches the feature matrix |

**Models (three architectures compared)**

| File | Role |
| --- | --- |
| `candidate_share_model.py` | The vote-share model on the transformed target |
| `regularised_models.py` | Architecture A: ridge, closed form (incumbent) |
| `candidate_hierarchical_model.py` | Architecture C: partial pooling on party identity |
| `candidate_boosted_model.py` | Architecture B: LightGBM shallow trees (**shipped**) |
| `candidate_probability_model.py` | Separately fitted probability of election |
| `candidate_seat_projection.py` | Predicted seats per party per contest |
| `cold_start_model.py` | Fallback for a row with no historical predecessor |

**Selection and scoring**

| File | Role |
| --- | --- |
| `candidate_architecture_selection.py` | Runs the two selection gates (Reform MAE > 5% better, lose ≤ 1 development fold) |
| `architecture_paired_bootstrap.py` | Paired-bootstrap uncertainty for the architecture comparison |
| `candidate_metrics.py` | Candidate-level scoring, stratified by contest structure |
| `coverage_evaluation.py`, `coverage_report.py` | Coverage-aware evaluation of how much of the release is scored |
| `model_comparison.py` | Side-by-side comparison across architectures |

**Explainability**

| File | Role |
| --- | --- |
| `candidate_explainability.py` | SHAP, fold-level coefficients, unstable features, worked examples |
| `candidate_tree_explainability.py` | Tree-specific (Architecture B) explanations |

**Orchestration**

| File | Role |
| --- | --- |
| `cli.py` | `train` / `config` / `validate` entry points |
| `configuration.py` | Resolves configuration (flags → file → defaults) and records it in the bundle |

**Product**: `outputs/model_bundle_v1/` (29 files; the news stage reads
`out_of_fold_predictions.csv`).
**Docs**: `candidate_model_card.md`, `candidate_split_and_leakage.md`,
`candidate_level_estimand.md`, `architecture_selection_evidence.md`.

---

## Support (four kinds)

| Location | Role | Contents |
| --- | --- | --- |
| `scripts/` | Runners | `run_persistence_benchmark.py`, `run_naive_benchmarks.py` (benchmarks); the candidate model runs through `python -m no_news_baseline.cli train` (group D); `build_electoral_fundamentals_release.py`, `build_model_input_contract.py` (fundamentals) |
| `config/` | Input evidence | `baseline_model.yaml` (candidate model settings, group D), `electoral_feature_metadata.csv` (feature field metadata) |
| `docs/` | Write-ups | `candidate_model_card.md`, `candidate_split_and_leakage.md`, `architecture_selection_evidence.md` (the shipped model); `persistence_benchmark.md`, `naive_benchmarks.md` (benchmark results) |
| `outputs/` | Products | **`model_bundle_v1/` is the shipped product** (group D, 29 files, excluded from Git, regenerated by `cli train`); plus the benchmark and feature-table folders |
| `tests/` | Tests | 444 tests, roughly one module each; the ones that matter most assert something *fails* (a prohibited field entering the matrix, a 7 May row reaching training, …). No need to read individually |

---

## How to run (from the repository root)

```bash
# 1) If needed, regenerate the candidate contract from the extractor first
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_candidate_contests.py

# 2) Fit and export the shipped candidate model (group D) — the main product
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  -m no_news_baseline.cli train

# 3) Run the parameter-free benchmarks (group A) — the floor it must clear
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  surrey-election-no-news-baseline/scripts/run_persistence_benchmark.py
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  surrey-election-no-news-baseline/scripts/run_naive_benchmarks.py
```

---

## Results at a glance (worth memorising for the viva)

- Main baseline (persistence): **area winner accuracy 80.5%**, **vote-share MAE 9.50 percentage points**.
- Three-way comparison: equal split **15.60** → party historical mean **10.43** → persistence **9.50** (MAE, lower is better).
- Key insight: **area identity helps the winner call a lot (80.5% vs 67.2%) but adds little to the precise share estimate.**
- Purpose: this is the threshold a news model must beat, not the final model.

---

## One rule throughout this package

The prediction layer **only reads** the contract JSON and never modifies official data; **predictor and outcome columns are strictly separated** (target-leakage control); missing values keep their scientific meaning and are only flagged, never filled in.
