# Stance vs volume on the 2021 validation harness

**EXPLORATORY stance-vs-volume on the 2021 validation harness, post-unblinding. Reproduces the 10-of-10 claim with code.**

Fit: surrey-county-council-2017 (5 parties, no Reform)
Evaluation: surrey-county-council-2021

## All non-empty periods

| period | kind | stance delta | volume delta | margin | stance wins |
| --- | --- | ---: | ---: | ---: | --- |
| 180_to_91_days | non_overlapping | -0.6898 | -2.1769 | +1.4871 | yes |
| 90_to_31_days | non_overlapping | -2.2616 | -3.2666 | +1.0050 | yes |
| 30_to_15_days | non_overlapping | -0.8753 | -1.2476 | +0.3723 | yes |
| 14_to_8_days | non_overlapping | +0.1164 | -7.4133 | +7.5297 | yes |
| 7_to_4_days | non_overlapping | -0.3673 | -0.8417 | +0.4744 | yes |
| previous_7_days | cumulative | -0.6983 | -12.7046 | +12.0063 | yes |
| previous_14_days | cumulative | +0.1579 | -2.5492 | +2.7070 | yes |
| previous_30_days | cumulative | +0.0256 | -1.5876 | +1.6132 | yes |
| previous_90_days | cumulative | -1.5748 | -2.8205 | +1.2458 | yes |
| previous_180_days | cumulative | -0.7831 | -1.8513 | +1.0682 | yes |

Stance wins in **10 of 10** non-empty periods.

Non-overlapping only: **5 of 5**.
