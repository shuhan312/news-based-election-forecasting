# Stance vs volume: margins

**EXPLORATORY stance-vs-volume margin table, post-unblinding. Replaces the sign count in section 5 with per-period margins.**

Each row runs one single-feature arm through the frozen harness. Stance = `net_portrayal` (favourable minus unfavourable articles). Volume = `party_article_count` (how many articles mention a party). Delta is the change in election-wide MAE against the recalibrated control; positive is better. Margin = stance delta minus volume delta. All arms share the 45 frozen fitting cells.

## Non-overlapping windows (the independent set)

| window | stance delta | 95% CI | volume delta | 95% CI | margin |
| --- | ---: | --- | ---: | --- | ---: |
| 180_to_91_days | +0.2885 | [+0.1037, +0.4566] | +0.1684 | [+0.1383, +0.1974] | +0.1202 |
| 90_to_31_days | +0.3574 | [+0.2335, +0.4711] | +0.2247 | [+0.1901, +0.2585] | +0.1327 |
| 30_to_15_days | +0.0188 | [-0.0052, +0.0423] | +0.1259 | [+0.0666, +0.1889] | -0.1071 |
| 14_to_8_days | +0.0645 | [+0.0416, +0.0875] | -0.0043 | [-0.0087, +0.0009] | +0.0688 |
| 7_to_4_days | -0.0059 | [-0.0109, -0.0011] | -0.0148 | [-0.0259, -0.0040] | +0.0089 |
| final_72_hours | +0.3943 | [+0.1803, +0.5856] | +0.0221 | [+0.0010, +0.0443] | +0.3722 |

Stance wins in **5 of 6** non-overlapping windows. Mean margin: **+0.0993**.

## Cumulative windows (sensitivity, not independent)

| window | stance delta | volume delta | margin |
| --- | ---: | ---: | ---: |
| previous_72_hours | +0.3943 | +0.0221 | +0.3722 |
| previous_7_days | +0.3741 | +0.0220 | +0.3521 |
| previous_14_days | +0.3394 | +0.0058 | +0.3337 |
| previous_30_days | +0.2203 | +0.0335 | +0.1868 |
| previous_90_days | +0.3701 | +0.1791 | +0.1910 |
| previous_180_days | +0.3315 | +0.1843 | +0.1472 |

Stance wins in **6 of 6** cumulative windows.

Overall: stance wins **11 of 12** periods. Mean margin across all: **+0.1816**.

## Is stance volume-weighted underneath?

Pearson r between `net_portrayal` (stance) and `party_article_count` (volume) across covered fitting cells, per window. A high |r| would mean stance is largely a volume proxy with a sign.

| window | covered cells | r | r-squared |
| --- | ---: | ---: | ---: |
| 180_to_91_days | 19 | -0.8068 | 0.6509 |
| 90_to_31_days | 19 | -0.7780 | 0.6053 |
| 30_to_15_days | 18 | -0.4530 | 0.2052 |
| 14_to_8_days | 14 | -0.3118 | 0.0972 |
| 7_to_4_days | 9 | -0.5636 | 0.3177 |
| final_72_hours | 8 | -0.4909 | 0.2410 |
| previous_72_hours | 8 | -0.4909 | 0.2410 |
| previous_7_days | 13 | -0.5342 | 0.2854 |
| previous_14_days | 15 | -0.3286 | 0.1080 |
| previous_30_days | 18 | -0.4738 | 0.2245 |
| previous_90_days | 19 | -0.7257 | 0.5266 |
| previous_180_days | 19 | -0.7977 | 0.6363 |

At the headline window (90-31 days), r = **-0.7780** (r-squared = 0.6053). This is a strong correlation: much of what stance captures is volume with a sign. The margins above should be read with that caveat.
