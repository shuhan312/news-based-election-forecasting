# Directory guide (STRUCTURE)

> A map for navigating this package quickly. It is documentation only and takes no part in running the code.
> In one line: **this package only does prediction and evaluation. It reads the contract JSON produced by the extractor and never modifies the official election data.**

## Overview: two subsystems + a finishing layer + support

| Group | What it does | Role |
| --- | --- | --- |
| **A. benchmarks** | Run parameter-free rules and report prediction accuracy | Current results / thesis results chapter |
| **B. fundamentals** | Build a one-row-per-election-area-party feature table | Input for later learned / news-aware models |
| **C. model input** | Add missing-value semantics and audit Independents | Finishing step for B |
| Support | scripts / config / docs / outputs / tests | Runners, evidence, docs, products, tests |

Data flow: `extractor no-news contract JSON` → A (produces results) and B → C (produces the feature table).

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

## Support (four kinds)

| Location | Role | Contents |
| --- | --- | --- |
| `scripts/` | Runners | `run_persistence_benchmark.py`, `run_naive_benchmarks.py` (results); `build_electoral_fundamentals_release.py`, `build_model_input_contract.py` (feature table); `generate_independent_previous_share_audit.py` |
| `config/` | Input evidence | `electoral_feature_metadata.csv` (feature field metadata) |
| `docs/` | Write-ups | `persistence_benchmark.md`, `naive_benchmarks.md` (results); `data_contract.md`, `electoral_feature_release.md` (leakage contract) |
| `outputs/` | Products | Four directories matching the products above. **Only the two result folders matter now; the two feature-table folders are for later** |
| `tests/` | Tests | 18 files, one per module, showing the pipeline is reproducible. No need to read individually |

---

## How to run (from the repository root)

```bash
# 1) If needed, regenerate the input contract from the extractor first
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_party_contests.py

# 2) Run the main baseline
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  surrey-election-no-news-baseline/scripts/run_persistence_benchmark.py

# 3) Run the two naive references
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
