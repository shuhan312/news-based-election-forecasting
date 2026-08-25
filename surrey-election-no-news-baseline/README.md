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

## Quick start

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

# 2) Fit and export the model bundle (a few minutes)
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m no_news_baseline.cli train

# 3) Run the parameter-free benchmarks (the floor the model must clear)
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  surrey-election-no-news-baseline/scripts/run_persistence_benchmark.py
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  surrey-election-no-news-baseline/scripts/run_naive_benchmarks.py

# 4) Confirm nothing is broken
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m pytest surrey-election-no-news-baseline/tests -q
```

Reproduction is confirmed when step 2 logs out-of-fold MAE 9.85 and holdout MAE
4.53, and step 4 reports 444 passing tests.

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
| `out_of_fold_predictions.csv` | **the news stage's input** |
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
- [`n5_candidate_specifications.md`](docs/n5_candidate_specifications.md) — the
  specified (not-yet-implemented) hierarchical Dirichlet model and its
  method-anchor references (Hanretty 2021; Stoetzer et al. 2019; Chen, Garnett &
  Montgomery 2023), with DOIs
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
