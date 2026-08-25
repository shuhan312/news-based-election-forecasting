# `src/` — the news-side (Stage 2) pipeline

## Purpose and role in the IRP

This directory is the Stage 2 news pipeline. It tests whether pre-election news
provides **additional predictive information beyond the history-only Stage 1
baseline** (`surrey-election-no-news-baseline/`). It turns raw news articles into
validated election–party–window features and fits a residual model whose result
is the project's central comparison.

It holds **code only**. Its outputs and frozen evidence live at the repository
root — `news_collection/`, `llm_context/`, `news_features/` — and the report
tables in `outputs/`. For the full eight-layer pipeline and how any reported
number traces to the code that produced it, see [`../REPO_MAP.md`](../REPO_MAP.md).

## Pipeline overview

```text
News sources
   │   eligibility screening (pre-election window, leakage rules)
   ▼
Cleaning and deduplication
   ▼
LLM labelling (issue / stance / framing)  →  validated to κ ≥ 0.60, then frozen
   ▼
Feature construction (election × party × window)
   ▼
Stage 2 residual model
   ▼
Evaluation against the frozen Stage 1 baseline
```

## Layout

| Location | What it does |
| --- | --- |
| `news_collection/` | News retrieval and eligibility / leakage screening |
| `dedup/`, `normalisation/`, `news_store/` | Cleaning, standardisation, and the article store |
| `llm_extraction/` | LLM issue / stance / framing labels and their validation |
| `news_features/` | Feature construction and leakage audits |
| `news_modelling/` | Stage 2 residual modelling, blinding, unblinding, diagnostics |
| top-level scripts | Build the `data/elections/` result tables and calendar the pipeline aligns news against |
| `legacy_pre_supervisor_news/` | Earlier exploratory code, retained for provenance; not part of the final pipeline |

Each subdirectory's own README lists its files and the ordered steps within it.

### Top-level collection scripts

The loose scripts directly under `src/` are the Layer 1 preparation step: each
builds a shared input the rest of the pipeline aligns against (the
`data/elections/` result tables, the election calendar, the name-standardisation
tables). They are standalone scripts, not a multi-step sub-pipeline, which is why
they sit at the top level rather than in a package. Grouped by role:

- **Official results → the `data/elections/` tables** — `fetch_official_scc_results.py`, `fetch_2026_surrey_results.py`, `convert_2013_extractor_output.py`, `convert_2026_extractor_output.py`, `add_2013_wikipedia_turnout.py` (fills the 2013 turnout gap the official page lacks), `fetch_election_results.py`, `build_election_calendar.py`, `audit_turnout.py`, `validate_election_results.py`
- **Name standardisation, sampling and workbook** — `build_name_standardisation.py`, `build_division_sample.py`, `build_research_workbook.py` (with `workbook_spec.json`)
- **News-coverage checks** — `check_newsapi_coverage.py`, `pilot_news_retrieval.py`, `verify_news_coverage_audit.py`
- **Early prototype (superseded, retained as history)** — `aggregate_results.py` → `build_model_dataset.py` produced the first model-ready dataset (`data/processed/model_dataset.csv`); nothing downstream now reads it and no reported number traces to it — the shipped pipeline uses the official-extractor contracts instead

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

## News collection and eligibility

The corpus is retrieved from SerpAPI, publisher search and web archives,
restricted to the pre-election window, with eligibility and leakage screening.
Every keep/drop decision is recorded, so the corpus is auditable rather than
taken on trust.

## Cleaning and standardisation

Exact and near-duplicate articles are collapsed, and party names, candidate
names and character encodings are standardised, before any labelling runs.

## LLM extraction and validation

Claude produces structured issue, stance and framing labels for each eligible
article. The labels are **validated against human annotation before use**: they
are accepted only when inter-rater agreement reaches κ ≥ 0.60, and the accepted
set is then frozen. Downstream features read only the frozen labels, so the
modelling never depends on an unvalidated or re-runnable labelling pass. This is
the answer to "why trust the LLM labels?" — they are gated and frozen, not used
raw.

## Feature construction

Article-level labels are aggregated into the same election–party–window
structure used in the modelling analysis, so news exposure and stance signals
are comparable across periods and parties. A leakage audit checks that no
feature encodes the outcome being predicted.

## Stage 2 modelling

Stage 2 **does not predict vote share directly**. It models the residual error
of the frozen Stage 1 baseline — a per-window ridge on those residuals — to test
whether news explains variation beyond historical information. Predictions are
frozen and blinded before the 2026 results are opened; the one-time unblinding
and every post-unblinding diagnostic are recorded. This residual design is the
core of the IRP: it isolates any news signal from what history already explains.

## Reproducibility and leakage controls

The pipeline is one-way — each layer reads only the layer above. Predictors and
outcomes stay separated, missing values are flagged rather than filled, and every
reported number traces to a committed, hash-pinned artefact (see `REPO_MAP.md`).
Large raw inputs under `data/` are local by design per the IRP large-file rule.

## Outputs and provenance

Each reported result links to a committed artefact: the news corpus
(`news_collection/`), the frozen LLM labels (`llm_context/`), the feature tables
and frozen evidence (`news_features/`), and the report tables
(`outputs/report_tables_v1/`). One early artefact is kept only for provenance:
`aggregate_results.py` → `build_model_dataset.py` produced the first model-ready
dataset (`data/processed/model_dataset.csv`), which nothing downstream now reads
and no reported number traces to; the shipped pipeline uses the official-extractor
contracts instead.
