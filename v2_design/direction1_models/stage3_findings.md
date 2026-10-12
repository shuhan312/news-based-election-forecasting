# Direction 1, stage 3: model selection on 2017–2023 (findings)

**2026-10-12.** Produced by `PYTHONPATH=.:src python -m forecast.models
validate`. Train on 2017→2021 and 2018→2022 (19,159 ward × party units);
validate on 2019→2023 (17,265). No 2025 row was loaded. Cost: zero.

## Result

| model | validation MAE (pp) | cold start | warm | Reform |
|---|---:|---:|---:|---:|
| **LightGBM, 15 leaves, 1000 rounds** | **8.06** | 7.10 | 8.20 | 4.47 |
| ridge + council intercepts (α 10, k 10) | 8.70 | 8.15 | 8.78 | 3.09 |
| proportional swing (best baseline) | 9.39 | 9.49 | 9.38 | 2.82 |
| uniform swing | 9.42 | 9.52 | 9.40 | **2.75** |
| persistence | 9.74 | 9.49 | 9.78 | 2.81 |

The best ML model beats the best classical baseline by **1.33 pp**, with a
council-bootstrap 95% CI of [1.05, 1.62]. This is the validation preview of
H1; the confirmatory test is the single 2025 run.

## Frozen for H1 (`selected_config.json`)

- Best baseline: **proportional swing**.
- Best ML: **LightGBM, 15 leaves, 1000 rounds**, learning rate 0.05, fitted
  on the uniform-swing residual. It is refitted on all three rounds before
  2025.
- The LightGBM grid was widened once (to 1000 and 2000 rounds) because the
  first run's winner sat on the grid edge at 500. The final winner is
  interior: 2000 rounds is worse. This was validation-only model selection.

## Finding that changes H2: the ML model mishandles Reform's cold start

On Reform rows (all of which are cold starts), every ML model is worse than
every classical baseline. LightGBM predicts a mean Reform share of 10.3%
against an actual 6.8%. Its cold-start correction comes mostly from other
parties' first candidacies, which are targeted and beat the national poll;
Reform's are not. Design amendment A1 therefore sets H2's no-news reference
to the strongest model on Reform cold-start rows (uniform swing, 2.75 pp), so
that news cannot win by correcting a biased reference.

This is also a substantive result. An England-wide model trained on how new
candidacies usually behave gets a genuinely new party wrong. That is the
cold-start problem V1 set out to study.

## Other observations

- Boundary-fallback rows are harder (LightGBM 9.66 vs 7.40 pp on id-matched
  rows). The ward's own history matters.
- Ward × party MAE around 8 pp is large in absolute terms. Single-ward local
  contests are noisy, and about 30% of wards have no matched history.

## Bug found by the tests

`renormalise` truncated shares to integers when every input was an integer.
Real inputs are floats, so no reported number changed. Fixed, and covered by
a test.
