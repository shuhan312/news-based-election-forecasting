# Reform vs non-Reform delta decomposition

**EXPLORATORY per-party delta decomposition, post-unblinding. Decomposes each arm's MAE delta into Reform and non-Reform components.**

Delta is the change in MAE against the recalibrated control; positive means news improved prediction. The non-Reform delta is derived from the weighted difference: (N_all * delta_all - N_reform * delta_reform) / N_non_reform.

## frozen

| window | all delta (n) | Reform delta (n) | non-Reform delta (n) |
| --- | ---: | ---: | ---: |
| 180_to_91_days | -0.5751 (753) | -2.8046 (162) | +0.0360 (591) |
| 90_to_31_days | +0.2404 (753) | -0.6877 (162) | +0.4948 (591) |
| 30_to_15_days | +0.1339 (753) | -0.1475 (162) | +0.2110 (591) |
| 14_to_8_days | -0.3252 (753) | -2.2729 (162) | +0.2087 (591) |
| 7_to_4_days | -0.0097 (753) | +0.0200 (162) | -0.0178 (591) |
| final_72_hours | +0.1882 (753) | -1.7214 (162) | +0.7116 (591) |

## placebo_party_dummies

| window | all delta (n) | Reform delta (n) | non-Reform delta (n) |
| --- | ---: | ---: | ---: |
| 180_to_91_days | +0.8342 (753) | -0.2929 (162) | +1.1432 (591) |
| 90_to_31_days | +0.8342 (753) | -0.2929 (162) | +1.1432 (591) |
| 30_to_15_days | +0.8342 (753) | -0.2929 (162) | +1.1432 (591) |
| 14_to_8_days | +0.8342 (753) | -0.2929 (162) | +1.1432 (591) |
| 7_to_4_days | +0.8342 (753) | -0.2929 (162) | +1.1432 (591) |
| final_72_hours | +0.8342 (753) | -0.2929 (162) | +1.1432 (591) |

## placebo_reform_dummy

| window | all delta (n) | Reform delta (n) | non-Reform delta (n) |
| --- | ---: | ---: | ---: |
| 180_to_91_days | -0.0302 (753) | -0.7896 (162) | +0.1780 (591) |
| 90_to_31_days | -0.0302 (753) | -0.7896 (162) | +0.1780 (591) |
| 30_to_15_days | -0.0302 (753) | -0.7896 (162) | +0.1780 (591) |
| 14_to_8_days | -0.0302 (753) | -0.7896 (162) | +0.1780 (591) |
| 7_to_4_days | -0.0302 (753) | -0.7896 (162) | +0.1780 (591) |
| final_72_hours | -0.0302 (753) | -0.7896 (162) | +0.1780 (591) |

## Key finding: party dummies at 90-31 days

- Overall delta: **+0.8342** (753 rows)
- Reform delta: **-0.2929** (162 rows)
- Non-Reform delta: **+1.1432** (591 rows)
