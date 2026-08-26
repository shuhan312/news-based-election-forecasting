# `src/news_modelling/` — Stage 2 news modelling (Layer 5)

The central test of the IRP: does pre-election news improve prediction beyond the
history-only Stage 1 baseline? This directory fits the news-layer estimator,
freezes its **blinded** 2026 predictions, runs the **one-time unblinding** against
the real results, and carries every post-unblinding diagnostic. It reads the
frozen Stage 1 bundle (`surrey-election-no-news-baseline/outputs/model_bundle_v1/`)
and the v1/v2 feature tables in `news_features/`; its outputs are the frozen
prediction and unblinding artefacts under `news_features/`.

## Main input-output path

```text
surrey-election-no-news-baseline/outputs/model_bundle_v1/
    |- out_of_fold_predictions.csv  -> Stage 2 residual training targets
    `- holdout_predictions.csv      -> frozen 2026 Stage 1 baseline

news_features/news_feature_table_v1.csv / news_feature_table_v2.csv
    + Stage 1 bundle
    -> stage1_bundle.py (validation and loading)
    -> news_estimator.py (per-window residual Ridge)
    -> run_blinded_2026_predictions.py / _v2.py
    -> news_features/blinded_2026_predictions_v1/ / _v2/
    -> unblind_2026.py
    -> news_features/unblinding_2026_v1/
```

v1 is the frozen pre-enrichment reference. v2 preserves the same feature and
model specification while adding the by-election corpus and training cells;
it is the enriched confirmatory release behind the final report's main
positive results.

## The estimator

`news_estimator.py` implements two approaches:

- **Approach A (residual)** — model the residual error of the frozen Stage 1
  baseline, so any news signal is isolated from what history already explains.
- **Approach B (joint)** — a joint specification, reported alongside A.

## Blinding and unblinding

The design is pre-registered and blind:

- `blinded_2026_predictions.py` / `_v2.py` — implement construction of the
  blinded prediction records.
- `run_blinded_2026_predictions.py` / `_v2.py` — executable freeze entry
  points; they bind input hashes and write the v1/v2 frozen artefacts **before
  any 2026 outcome is read**.
- `unblind_2026.py` — the **one-time** unblinding: score the frozen predictions
  against reality. It is the only step that reads the 2026 outcomes.
- The Woking South blind test is stricter still: `woking_south_blind_protocol.py`
  freezes the protocol before any contact, `woking_south_blind_predict.py`
  predicts without reading the outcome, and `woking_south_unseal.py` is the
  protocol's single authorised reader of that outcome.

## Diagnostics (post-unblinding)

Each is a **report-used** post-unblinding check; the report section it backs is
named so its output can be traced. All read frozen inputs and are not imported
by the prediction path.

| Module | Question it answers | Report use |
| --- | --- | --- |
| `identity_placebos.py` | Is the news layer anything more than the party's name? | §6.2 |
| `stage1_party_sensitivity.py` | Does the news improvement survive Stage 1 absorbing per-party mean residuals? (0.2404 → 0.3004 removing four parties, → 0.0428 removing six) | §6.2 (sole source of these figures + CIs) |
| `stance_volume_margins.py` | Stance vs volume, measured by margins rather than sign counts | §5.3 |
| `exploratory_decompositions.py` | Attribution and mechanism decompositions | §5.4 |
| `reform_decomposition.py` | Per-party ΔMAE decomposition; its JSON drives `reform_party_split_figure.py` | §5.4, Figure 5 (sole source) |
| `per_party_bootstrap.py` | Contest-bootstrap uncertainty for the per-party split | §5.4 |
| `production_news_lopo.py` | Leave-one-party-out: which party's training cells the gain depends on | §5.2, Appendix Table a17 (sole source) |
| `minimal_detectable_effect.py` | What effect size the archived design could even have detected | §6.3 |
| `local_v3_rerun.py` | The exploratory local-vs-national re-run | §5.2 |
| `haslemere_probe_prediction.py` | The 7 July 2026 transfer probe with frozen v2 specifications | §5.6 |

## Running and reproducibility

Modelling reads **frozen** inputs — the Stage 1 bundle and the feature tables —
so scoring is **deterministic** and re-runs reproduce the same numbers. The
blinded predictions are frozen artefacts (their sha256 committed beside them),
and unblinding is a one-time act recorded in `news_features/unblinding_2026_v1/`.
Representative entry points, from the repository root:

```bash
PYTHONPATH=src .venv/bin/python -m news_modelling.run_blinded_2026_predictions      # freeze v1 predictions
PYTHONPATH=src .venv/bin/python -m news_modelling.run_blinded_2026_predictions_v2   # freeze v2 (enriched) predictions
PYTHONPATH=src .venv/bin/python -m news_modelling.unblind_2026                      # one-time scoring vs reality
```

## Discipline

Predictions are frozen before outcomes are seen; unblinding happens once and is
recorded; a null result is reported with its minimal detectable effect rather
than as proof of no effect; Reform UK is reported separately and never merged
with UKIP. See `REPO_MAP.md` and `news_features/PRODUCTION_NEWS_EVIDENCE_REGISTER.md`
for which report section each artefact backs.
