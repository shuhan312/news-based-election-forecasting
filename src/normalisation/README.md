# `src/normalisation/` — text normalisation (Layer 2, Phase 4)

Cleaning layer, first half: take the eligible collected articles and produce
clean, structured article text for labelling. Conservative throughout — the aim
is to remove web-template noise and encoding artefacts without altering the
words. Each Phase 4 step is a **pure-logic module** plus a **`build_` runner**
that applies it to every article (logic is testable without IO).

## The Phase 4 steps

```text
1  normalisation_input   lock the eligible population and select each article's text source
2  html_clean            conservative HTML / web-template cleaning
3  char_normalise        conservative Unicode, encoding and character normalisation
4  structure_normalise   whitespace, line-break and paragraph-structure normalisation
5  boundary_resolve      resolve title / body / supporting-text boundaries → structured articles
6  text_quality          text-quality validation and missing-body status
7  final_audit           audit steps 1–6 and run the deterministic language check
```

## Layout

| Module | Role |
| --- | --- |
| `normalisation_input.py`, `html_clean.py`, `char_normalise.py`, `structure_normalise.py`, `boundary_resolve.py`, `text_quality.py`, `final_audit.py` | The pure-logic step implementations |
| `build_normalisation_input.py` … `build_final_layer.py` | The per-step runners that apply each step to every article |

## Running and outputs

Run the `build_` steps in order (from the repository root), e.g.:

```bash
python3 -m src.normalisation.build_normalisation_input
python3 -m src.normalisation.build_html_cleaned_articles
python3 -m src.normalisation.build_char_normalised_articles
python3 -m src.normalisation.build_structure_normalised_articles
python3 -m src.normalisation.build_structured_articles
python3 -m src.normalisation.build_text_quality
python3 -m src.normalisation.build_final_layer
```

The stage is **deterministic** — it reads the frozen eligible corpus and
produces the same cleaned articles on every run. Outputs (the cleaned-article
`*_articles_v1.jsonl` layers and the cleaning logs/review queues) land in the
repository-root `news_collection/` directory; see its README. They are consumed
by `src/dedup/` (Phase 5) and then labelling.

## Discipline

Cleaning is conservative and never rewrites content; every step is audited, and
a missing body is recorded as a status, not silently dropped. Raw article text
is not committed (copyright); see `REPO_MAP.md`.
