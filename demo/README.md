# Viva demonstrator (`demo/`)

A local, offline research demonstrator for the viva, built for the study
**"Context to Consequence — AI-Driven News Categorisation and Event
Prediction"** (2026 Surrey local elections, Reform UK focus).

## Separation statement

This directory is **not part of the work the reported results rest on**.
Nothing here feeds the pipeline, the frozen predictions, the report tables
or the report figures. It is a *viewing layer only*: every number shown is
**read at build time from the committed, frozen artefacts** in
`outputs/report_tables_v1/` (whose `manifest.json` pins the sha256 of every
upstream input) and every figure is embedded from the committed
`outputs/report_figures_v1/`. The build **fails** if any headline number in
the pack disagrees with the frozen artefacts. No number is invented, and
exploratory results are labelled as such, exactly as in the report.

## What it produces

`demo/viva_pack.html` — a single self-contained HTML file (no server, no
network, no API keys) with eight sections following the demonstrator brief:

1. Research overview
2. Data and code
3. Methodology
4. Technical results
5. Research interpretation
6. Interactive demonstration (frozen-model scenarios + confirmatory explorer)
7. Limitations and responsible use
8. Exports and provenance

plus built-in **viva guidance**: a suggested run order, per-section speaking
notes, and anticipated questions with artefact-grounded answers.

a **code navigator** (section 9: every tracked Python file in `src/`,
`app/`, `tests/` and `demo/`, embedded verbatim with search and
line-numbered viewing, so any examiner question can be answered by
opening the exact file), and the live-demonstration pairing required by
the supervisor's viva guidance: the static pack carries the frozen
evidence and its code trail, while `app/news_app.py` (Streamlit) accepts
inputs — party, tone, arm, article count, window — and runs the frozen
model live; the pack verifies at build time that the live app's inputs
are present on the machine.

Two further features are wired through the whole page:

- **Number-to-code provenance.** Every table, figure and headline number
  carries a "code behind these numbers" button. It opens the full chain:
  the frozen input artefact (with its manifest sha256), the pipeline
  module that computed the numbers (docstring plus the exact functions,
  e.g. the bootstrap and scoring code in `unblind_2026.py`), and the
  function in `build_report_tables.py` that wrote the CSV. All excerpts
  are extracted from the repository by `ast` at build time — never
  copied by hand — so they cannot drift from the committed code.
- **Synthetic what-if scenarios.** Section 6.2 replays the design's
  scenario layer (`synthetic_news_scenarios.py`): hypothetical stories
  injected into the frozen v2 model's feature cells, with the injection
  mechanics, the frozen-coefficient assertion and the stated boundary
  (the issue axis cannot flow through the model) shown alongside the
  committed outputs.

## Run instructions

From the repository root:

```bash
.venv/bin/python demo/build_viva_pack.py
open demo/viva_pack.html
```

Dependencies: only `pandas` (already in the project `requirements.txt`).
No environment variables, keys or network access are needed — the pack is
static and works offline in any browser.

Tests:

```bash
.venv/bin/python -m pytest demo/test_viva_pack.py -q
```

## Live-model demonstration (optional, separate)

The repository also contains `app/news_app.py`, a Streamlit app that runs
synthetic scenarios against the *frozen* Stage 2 model live (it re-verifies
the frozen coefficients before running anything). The static pack embeds the
committed scenario outputs (`t18_synthetic_scenarios.csv`) instead, so the
viva demonstration works with zero setup; the Streamlit app is the fallback
if a live run is requested and the local model bundle is present.

## Provenance

| input | role |
| --- | --- |
| `outputs/report_tables_v1/*.csv` | all tabular numbers (frozen, sha256-pinned via `manifest.json`) |
| `outputs/report_tables_v1/latex/a1_stage1_predictors.tex`, `a5_llm_validation.tex` | predictor dictionary and LLM validation evidence |
| `outputs/report_figures_v1/*.png` | all figures (committed) |
| `git ls-files` | the repository map and test counts (computed, not typed) |

The generated `viva_pack.html` is a build artefact and is git-ignored
(see `demo/.gitignore`), per the repository's generated-artefact rule.
