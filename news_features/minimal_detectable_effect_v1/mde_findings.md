# Minimal detectable effects of the archived design

**EXPLORATORY design-sensitivity annex. Every number derives from the width of a committed bootstrap interval; nothing is refitted, promoted or selected.**

MDE50 = interval half-width (a true effect that size is detected in ~half of repeated samples); MDE80 = half-width x 1.429 (detected in ~80%). Derived from interval WIDTH only - the observed delta never enters the arithmetic, which is what separates design sensitivity from the discredited observed-effect post-hoc power. Share-point units throughout.

## Summary: the design's resolution

| island | scope | comparisons | median MDE80 | range |
| --- | --- | ---: | ---: | --- |
| holdout_2026_v1 | overall_mae | 12 (1 structural-zero excluded) | 0.364 | [0.02, 0.878] |
| holdout_2026_v2 | overall_mae | 12 (1 structural-zero excluded) | 0.216 | [0.006, 0.581] |
| holdout_2026_v2 | reform_level | 12 (1 structural-zero excluded) | 0.045 | [0.006, 2.226] |
| holdout_2026_v2 | reform_vs_group_contrast | 12 (1 structural-zero excluded) | 0.286 | [0.027, 2.326] |
| validation_2021 | overall_mae | 18 (4 structural-zero excluded) | 0.962 | [0.585, 2.625] |
| validation_2021 | reform_level | 18 (4 structural-zero excluded) | 1.626 | [0.341, 6.19] |
| validation_2021 | reform_mae | 18 (4 structural-zero excluded) | 2.601 | [0.809, 5.273] |
| validation_2021 | reform_vs_group_contrast | 18 (4 structural-zero excluded) | 2.329 | [1.292, 6.612] |

## Reading

The pre-2026 verdict now states its own resolution: the 0-of-18 result bounds any true overall improvement below roughly 0.962 share points of MAE (median MDE80 across the confirmed windows), and any Reform-specific improvement below roughly 2.601 points - an order the six 2021 Reform contests could never certify. "No Reform evidence" is therefore a statement about the design's resolution as much as about news. The 2026 island is the sharp one: with 81 contests the v2 overall comparisons resolve effects down to a median 0.216 points, which is why the small legacy-party level corrections could be certified there at all.

Haslemere and Woking South admit no interval (single contests): their MDE is unbounded, which is the arithmetic form of the register's insistence that they are illustrative case studies.

Caveats: normal-approximation SE from percentile-interval width; asymmetric intervals (bootstrap mean off-centre by more than a tenth of the half-width) are flagged per row and the symmetric half-width is used regardless - 11 of 120 comparisons are flagged, all of them in validation_2021/reform_mae, which is the six-contest corner where the normal approximation is weakest, so its resolution figure is an approximation, not a sharp threshold; every MDE is conditional on this frozen design - features, fitting cells and contest counts - not a claim about news effects in general.
