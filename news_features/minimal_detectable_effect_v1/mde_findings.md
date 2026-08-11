# Minimal detectable effects of the archived design

**EXPLORATORY design-sensitivity annex. Every number derives from the width of a committed bootstrap interval; nothing is refitted, promoted or selected.**

MDE50 = interval half-width (a true effect that size is detected in ~half of repeated samples); MDE80 = half-width x 1.429 (detected in ~80%). Derived from interval WIDTH only - the observed delta never enters the arithmetic, which is what separates design sensitivity from the discredited observed-effect post-hoc power. Share-point units throughout.

## Summary: the design's resolution

| island | scope | party | distinct estimable | median MDE80 | range |
| --- | --- | --- | ---: | ---: | --- |
| holdout_2026_v1 | overall_mae | - | 11 (1 structural-zero excluded) | 0.364 | [0.02, 0.878] |
| holdout_2026_v2 | overall_mae | - | 11 (1 structural-zero excluded) | 0.216 | [0.006, 0.581] |
| holdout_2026_v2 | party_level | conservative | 11 (1 structural-zero excluded) | 0.073 | [0.011, 3.016] |
| holdout_2026_v2 | party_level | green | 11 (1 structural-zero excluded) | 1.049 | [0.084, 1.508] |
| holdout_2026_v2 | party_level | labour | 11 (1 structural-zero excluded) | 0.038 | [0.008, 0.229] |
| holdout_2026_v2 | party_level | liberal_democrat | 11 (1 structural-zero excluded) | 0.056 | [0.01, 3.976] |
| holdout_2026_v2 | party_level | reform_uk | 11 (1 structural-zero excluded) | 0.045 | [0.006, 2.226] |
| holdout_2026_v2 | reform_vs_group_contrast | - | 11 (1 structural-zero excluded) | 0.286 | [0.027, 2.326] |
| validation_2021 | overall_mae | - | 13 (4 structural-zero, 1 duplicate-vector excluded) | 0.962 | [0.585, 2.625] |
| validation_2021 | party_level | conservative | 13 (4 structural-zero, 1 duplicate-vector excluded) | 1.478 | [0.706, 8.707] |
| validation_2021 | party_level | green | 13 (4 structural-zero, 1 duplicate-vector excluded) | 1.11 | [0.392, 2.959] |
| validation_2021 | party_level | labour | 13 (4 structural-zero, 1 duplicate-vector excluded) | 1.105 | [0.158, 4.09] |
| validation_2021 | party_level | liberal_democrat | 13 (4 structural-zero, 1 duplicate-vector excluded) | 2.074 | [1.286, 5.583] |
| validation_2021 | party_level | reform_uk | 13 (4 structural-zero, 1 duplicate-vector excluded) | 1.626 | [0.341, 6.19] |
| validation_2021 | party_level | ukip | 13 (4 structural-zero, 1 duplicate-vector excluded) | 4.179 | [0.909, 5.076] |
| validation_2021 | reform_mae | reform_uk | 13 (4 structural-zero, 1 duplicate-vector excluded) | 2.601 | [0.809, 5.273] |
| validation_2021 | reform_vs_group_contrast | - | 13 (4 structural-zero, 1 duplicate-vector excluded) | 2.329 | [1.292, 6.612] |

## Headline window, party by party (combined arm, 90-31 days)

| island | party | observed d\|bias\| | MDE80 | detectable |
| --- | --- | ---: | ---: | --- |
| holdout_2026_v2 | conservative | -1.696 | 0.067 | yes |
| holdout_2026_v2 | green | +1.051 | 1.072 | NO - inside the blind zone |
| holdout_2026_v2 | labour | -0.549 | 0.031 | yes |
| holdout_2026_v2 | liberal_democrat | -2.752 | 0.055 | yes |
| holdout_2026_v2 | reform_uk | +1.836 | 0.034 | yes |
| validation_2021 | conservative | +3.925 | 1.171 | yes |
| validation_2021 | green | +4.705 | 1.408 | yes |
| validation_2021 | labour | +1.054 | 3.994 | NO - inside the blind zone |
| validation_2021 | liberal_democrat | +6.244 | 2.029 | yes |
| validation_2021 | reform_uk | -9.142 | 0.648 | yes |
| validation_2021 | ukip | -4.713 | 1.404 | yes |

## Reading

The pre-2026 verdict now states its own resolution. The eighteen confirmed 2021 specifications are fewer looks at the data than they appear: four windows admitted no articles, leaving the news prediction identical to the control, and one further pair is byte-identical because `combined = local + national` collapses where one component is empty. That leaves 13 distinct estimable comparisons, not eighteen. Across them the 0-of-18 result bounds any true overall improvement below roughly 0.962 share points of MAE (median MDE80 across the confirmed windows), and any Reform-specific improvement below roughly 2.601 points - an order the six 2021 Reform contests could never certify. "No Reform evidence" is therefore a statement about the design's resolution as much as about news. The 2026 island is the sharp one: with 81 contests the v2 overall comparisons resolve effects down to a median 0.216 points, which is why the small legacy-party level corrections could be certified there at all.

Haslemere and Woking South admit no interval (single contests): their MDE is unbounded, which is the arithmetic form of the register's insistence that they are illustrative case studies.

Per-party resolutions are NOT interchangeable. Inside the 2026 headline window they span 0.031 (Labour) to 1.072 (Green), a thirty-fold range, and party size does not explain it: Green stood 146 candidates against Labour's 126. The driver is the absolute value in |bias| itself, which has a corner at zero. A party whose level error already sits near zero - Green's baseline bias is +0.25 - has resampled biases that fall on both sides of that corner and get folded together, widening and skewing its interval. So a well-calibrated party is intrinsically the hardest place to certify a level change, and Green's undetectable cell should be read as that, not as a weaker measurement of the same kind. The same mechanism explains 2021 Labour (bias +3.74 but volatile across contests; threshold 3.99, observed 1.05, inside the blind zone).

Caveats: normal-approximation SE from percentile-interval width; asymmetric intervals (bootstrap mean off-centre by more than a tenth of the half-width) are flagged per row and the symmetric half-width is used regardless - 11 of 258 comparisons are flagged, all of them in validation_2021/reform_mae, which is the six-contest corner where the normal approximation is weakest, so its resolution figure is an approximation, not a sharp threshold; every MDE is conditional on this frozen design - features, fitting cells and contest counts - not a claim about news effects in general.
