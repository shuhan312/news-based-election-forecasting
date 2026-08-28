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

## Complete file guide

One pure-logic module and one `build_` runner per step; `tests/test_<step>.py`
covers each logic module.

| Step | Logic module | Runner | What the runner writes |
| --- | --- | --- | --- |
| 1 | `normalisation_input.py` | `build_normalisation_input.py` | the locked eligible population and each article's selected text source (manifest + records + review queue) |
| 2 | `html_clean.py` | `build_html_cleaned_articles.py` | HTML/web-template-cleaned article text and its log |
| 3 | `char_normalise.py` | `build_char_normalised_articles.py` | Unicode/encoding-normalised text and its log |
| 4 | `structure_normalise.py` | `build_structure_normalised_articles.py` | whitespace/paragraph-structure-normalised text and its log |
| 5 | `boundary_resolve.py` | `build_structured_articles.py` | title/body/supporting-text boundaries → structured articles |
| 6 | `text_quality.py` | `build_text_quality.py` | per-article text-quality verdicts, resolutions queue and summary |
| 7 | `final_audit.py` | `build_final_layer.py` | the audited final text layer (`normalised_text_layer_v1_provisional.jsonl`, git-ignored) plus its committed manifest, audit and quality report |

`_v1_provisional` is the frozen intermediate layer's historical version name,
not an indication that the final repository is waiting for more text-cleaning
work. Downstream loaders pin this exact layer and its manifest.

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

## Hand-off and verification

The step-7 audited text layer is what downstream article loaders read:
`src/llm_extraction/run_pilot.py` (the shared article loader behind the
production extraction) loads
`news_collection/normalised_text_layer_v1_provisional.jsonl` directly, with
the committed manifest carrying its hashes. The offline test suite for this
package:

```bash
.venv/bin/python -m pytest tests/test_normalisation_input.py \
    tests/test_html_cleaning.py tests/test_char_normalisation.py \
    tests/test_structure_normalisation.py tests/test_boundary_resolution.py \
    tests/test_text_quality.py tests/test_final_audit.py -q
```

## Discipline

Cleaning is conservative and never rewrites content; every step is audited, and
a missing body is recorded as a status, not silently dropped. Raw article text
is not committed (copyright); see `REPO_MAP.md`.
