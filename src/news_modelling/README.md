# `src/news_modelling/` — Stage 2 news modelling (Layer 5)

The central test of the IRP: does pre-election news improve prediction beyond the
history-only Stage 1 baseline? This directory fits the news-layer estimator,
freezes its **blinded** 2026 predictions, runs the **one-time unblinding** against
the real results, and carries every post-unblinding diagnostic. It reads the
frozen Stage 1 bundle (`surrey-election-no-news-baseline/outputs/model_bundle_v1/`)
and the feature tables in `news_features/`; its outputs are the frozen prediction
and unblinding artefacts under `news_features/`.

## The estimator

`news_estimator.py` implements two approaches:

- **Approach A (residual)** — model the residual error of the frozen Stage 1
  baseline, so any news signal is isolated from what history already explains.
- **Approach B (joint)** — a joint specification, reported alongside A.

## Blinding and unblinding

The design is pre-registered and blind:

- `blinded_2026_predictions.py` / `_v2.py` — freeze the news layer's 2026
  predictions **before any 2026 outcome is read** (v1, and the enriched v2).
- `unblind_2026.py` — the **one-time** unblinding: score the frozen predictions
  against reality. It is the only step that reads the 2026 outcomes.
- The Woking South blind test is stricter still: `woking_south_blind_protocol.py`
  freezes the protocol before any contact, `woking_south_blind_predict.py`
  predicts without reading the outcome, and `woking_south_unseal.py` is the
  protocol's single authorised reader of that outcome.

## Diagnostics (post-unblinding)

| Module | Question it answers |
| --- | --- |
| `identity_placebos.py` | Is the news layer anything more than the party's name? |
| `stance_volume_margins.py`, `stance_volume_2021.py` | Stance vs volume, measured by margins rather than sign counts |
| `exploratory_decompositions.py` | Attribution and mechanism decompositions |
| `per_party_bootstrap.py` | Contest-bootstrap uncertainty for the per-party split |
| `minimal_detectable_effect.py` | What effect size the archived design could even have detected |
| `local_v3_rerun.py` | The exploratory local-vs-national re-run |
| `haslemere_probe_prediction.py` | The 7 July 2026 transfer probe with frozen v2 specifications |

## Running and reproducibility

Modelling reads **frozen** inputs — the Stage 1 bundle and the feature tables —
so scoring is **deterministic** and re-runs reproduce the same numbers. The
blinded predictions are frozen artefacts (their sha256 committed beside them),
and unblinding is a one-time act recorded in `news_features/unblinding_2026_v1/`.
Representative entry points, from the repository root:

```bash
python3 -m src.news_modelling.blinded_2026_predictions      # freeze v1 predictions
python3 -m src.news_modelling.blinded_2026_predictions_v2   # freeze v2 (enriched) predictions
python3 -m src.news_modelling.unblind_2026                  # one-time scoring vs reality
```

## Discipline

Predictions are frozen before outcomes are seen; unblinding happens once and is
recorded; a null result is reported with its minimal detectable effect rather
than as proof of no effect; Reform UK is reported separately and never merged
with UKIP. See `REPO_MAP.md` and `news_features/PRODUCTION_NEWS_EVIDENCE_REGISTER.md`
for which report section each artefact backs.
