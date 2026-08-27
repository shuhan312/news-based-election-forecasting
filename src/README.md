# `src/` — news-pipeline code (Layers 1–5)

## Purpose and role in the IRP

This directory contains the code that prepares the news side of the project and
fits the Stage 2 news model. It tests whether pre-election news provides
**additional predictive information beyond the history-only Stage 1 baseline**
(`surrey-election-no-news-baseline/`). It turns raw news articles into validated
election–party–window features and fits the residual model used in the project's
central comparison.

It holds **code only**. Its outputs and frozen evidence live at the repository
root — `news_collection/`, `llm_context/`, `news_features/` — and the report
tables in `outputs/`. For the full eight-layer pipeline and how any reported
number traces to the code that produced it, see [`../REPO_MAP.md`](../REPO_MAP.md).

## Numbering: layers are not modelling stages

The repository uses two deliberately different numbering systems:

- **Pipeline Layers 1–8** describe the end-to-end data and evidence flow.
- **Modelling Stages 1–2** distinguish the history-only baseline (Stage 1) from
  the news residual model (Stage 2).

Stage 2 modelling therefore sits in **Pipeline Layer 5**. Collection's internal
query stages (A–H, M, M2) and eligibility stages (1–5) are local workflow labels,
not modelling stages or pipeline layers.

Some Layer 2 READMEs also retain numbers from the original news-processing
protocol: text normalisation was **Phase 4** and deduplication was **Phase 5**.
Those are historical within-layer workflow labels, not extra pipeline layers.
Both components belong to current **Pipeline Layer 2**; the phase numbers are
kept only so the code can still be traced to the original protocol.

## Layers represented in `src/`

| Pipeline layer | Code location | Responsibility |
| --- | --- | --- |
| **1A — official-election inputs** | top-level `src/*.py`; `surrey-election-extractor/` | build and validate the election results, calendar and name tables against which news is aligned |
| **1B — news collection and eligibility** | `news_collection/` | retrieve the pre-election corpus and record every include/exclude decision |
| **2 — cleaning and canonicalisation** | `normalisation/`, `news_store/`, `dedup/` | clean text, maintain article records, collapse duplicates and select one canonical article |
| **3 — LLM extraction and validation** | `llm_extraction/` | extract issue/stance/framing labels, apply the human-agreement gate and freeze accepted labels |
| **4 — feature construction** | `news_features/` | aggregate accepted labels to election–party–window feature tables and apply leakage guards |
| **5 — modelling** | `news_modelling/`; Stage 1 sibling project | load the frozen Stage 1 bundle, fit Stage 2 residual models, freeze predictions and unblind once |

Layers 6–8 live outside `src/`: frozen evidence in `news_features/` and
`news_protocol/`, report tables/figures in `outputs/`, and the final consumers
in `report/`, `app/` and `demo/`. See [`../REPO_MAP.md`](../REPO_MAP.md) for the
authoritative eight-layer map and report-to-code trace.

## Pipeline overview

```text
Layer 1  official-election inputs + news collection and eligibility
   ↓
Layer 2  text normalisation + article store + deduplication
   ↓
Layer 3  LLM issue / stance / framing → validation gate → frozen labels
   ↓
Layer 4  election × party × window feature tables
   ↓
Layer 5  Stage 1 historical baseline + Stage 2 news residual model
   ↓
Layers 6–8  frozen evidence → report pack → report/app/viva consumers
```

## Layout

| Location | What it does |
| --- | --- |
| `news_collection/` | Layer 1B: news retrieval and eligibility/leakage screening |
| `normalisation/`, `news_store/`, `dedup/` | Layer 2: cleaning, article storage and canonicalisation |
| `llm_extraction/` | Layer 3: LLM labels, validation and freeze evidence |
| `news_features/` | Layer 4: deterministic feature construction and leakage guards |
| `news_modelling/` | Layer 5: Stage 2 residual modelling, blinding, unblinding and diagnostics |
| top-level scripts | Layer 1A: build the election tables and calendar to which news is aligned |

Each subdirectory's own README lists its files and the ordered steps within it.

## How to run the code

Not every `.py` file is an executable program. The supported entry points are
the documented `run_*` and `build_*` modules; schemas, validators, estimators
and comparison helpers are normally imported by those entry points. Running a
helper directly is neither required nor a separate reproduction step.

| Layer | Where the supported commands are documented | Execution rule |
| --- | --- | --- |
| 1A | the top-level-script guide below | run only the required standalone builder or validator from the repository root |
| 1B | [`news_collection/README.md`](news_collection/README.md) | use the collection CLI for query stages and the documented builders for eligibility/release work |
| 2 | [`normalisation/README.md`](normalisation/README.md), [`dedup/README.md`](dedup/README.md), [`news_store/README.md`](news_store/README.md) | run the ordered `build_*` chains; `news_store` is a library and has no standalone CLI |
| 3 | [`llm_extraction/README.md`](llm_extraction/README.md) | use the production batch runner and health check; validation modules support the recorded evidence, and API runs are not repeated casually |
| 4 | [`news_features/README.md`](news_features/README.md) | run the required v1/v2 or explicitly named extension builder |
| 5 | [`news_modelling/README.md`](news_modelling/README.md) | use the named freeze/unblind runners; the remaining modules are report diagnostics, figure builders or imported modelling logic |

Each layer README also gives its offline verification command. The complete
repository reproduction order is documented in `REPO_MAP.md`; a file's presence
in a file guide does not imply that it must be run independently.

### Layer 1A: top-level official-election input scripts

The loose scripts directly under `src/` are the official-election branch of
Layer 1: each builds a shared input the rest of the pipeline aligns against (the
`data/elections/` result tables, the election calendar, the name-standardisation
tables). They are standalone scripts, not a multi-step sub-pipeline, which is why
they sit at the top level rather than in a package. Grouped by role:

- **Official results → the `data/elections/` tables** — `fetch_official_scc_results.py`, `fetch_2026_surrey_results.py`, `convert_2013_extractor_output.py`, `convert_2026_extractor_output.py`, `add_2013_wikipedia_turnout.py` (fills the 2013 turnout gap the official page lacks), `fetch_election_results.py`, `aggregate_results.py` (writes `ward_party_results.csv` and `ward_winners.csv`, which the pre-registered division sample reads), `build_election_calendar.py`, `audit_turnout.py`, `validate_election_results.py`
- **Name standardisation, sampling and workbook** — `build_name_standardisation.py`, `build_division_sample.py`, `build_research_workbook.py` (with `workbook_spec.json`)
- **News-coverage checks** — `check_newsapi_coverage.py`, `pilot_news_retrieval.py`, `verify_news_coverage_audit.py`

Superseded early code — the `build_model_dataset.py` prototype and the
pre-supervisor news scripts (`legacy_pre_supervisor_news/`) — has been removed
from the working tree and remains in Git history.

**Outputs and reproduction.** These scripts write the committed `data/elections/`
reference tables (`2013_scc_results.csv`, `2026_east/west_surrey_results.csv`,
`election_calendar.csv`, `candidate_name_standardisation.csv` and their logs), so
those tables are already in the repository and need not be regenerated. The
`convert_*` scripts read the frozen extractor output and reproduce
deterministically; the `fetch_*`, calendar and Wikipedia-turnout scripts read
external sources, so re-running them yields a fresh snapshot rather than a
bit-for-bit copy of the committed table. Run a script from the repository root
(some, such as `build_name_standardisation.py`, import a sibling module and need
`PYTHONPATH=src`).

## Reproducibility and leakage controls

The pipeline is one-way — each layer reads only the layer above. Predictors and
outcomes stay separated, missing values are flagged rather than filled, LLM
labels enter Layer 4 only after the κ ≥ 0.60 human-agreement gate and are then
frozen, and Stage 2 models the residuals of the frozen Stage 1 baseline to test
whether news features add predictive information beyond history. Reported
numbers trace to committed artefacts, and the report table pack pins the
sha256 of every input it reads (see `REPO_MAP.md` and the root
`REPRODUCIBILITY.md`). Large raw inputs under `data/` are local by design per
the IRP large-file rule.
