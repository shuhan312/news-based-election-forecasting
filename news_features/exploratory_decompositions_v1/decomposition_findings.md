# The two pre-declared decompositions

**EXPLORATORY, post-unblinding, pre-declared in register section 16. Nothing here joins the confirmatory verdict.**

## 1. Attribution: refit without the seven Reform cells

Fitting cells 45 -> 38.

| analysis | window | full-fit delta | no-Reform delta | verdict |
| --- | --- | ---: | ---: | --- |
| combined_exploratory | 180_to_91_days | -0.5751 | -1.2684 | no full-fit improvement to attribute |
| combined_exploratory | 90_to_31_days | +0.2404 | +0.0773 | improvement survives without Reform cells |
| combined_exploratory | 30_to_15_days | +0.1339 | +0.0333 | improvement survives without Reform cells |
| combined_exploratory | 14_to_8_days | -0.3252 | -0.8817 | no full-fit improvement to attribute |
| combined_exploratory | 7_to_4_days | -0.0097 | -0.0010 | no full-fit improvement to attribute |
| combined_exploratory | final_72_hours | +0.1882 | -1.1328 | improvement collapses without Reform cells |
| national_exploratory | 180_to_91_days | -0.5896 | -1.2782 | no full-fit improvement to attribute |
| national_exploratory | 90_to_31_days | +0.2682 | -0.0015 | improvement collapses without Reform cells |
| national_exploratory | 30_to_15_days | -0.0156 | -2.6482 | no full-fit improvement to attribute |
| national_exploratory | 14_to_8_days | +0.0048 | +0.0029 | improvement survives without Reform cells |
| national_exploratory | 7_to_4_days | +0.0000 | +0.0000 | no full-fit improvement to attribute |
| national_exploratory | final_72_hours | -0.0231 | -0.0050 | no full-fit improvement to attribute |

Of the full fit's positive deltas: **3 survive** without Reform cells, **2 collapse**.

## 2. Mechanism: bias against dispersion

| analysis | window | baseline bias / dispersion | news bias / dispersion | bias change | dispersion change |
| --- | --- | --- | --- | ---: | ---: |
| combined_exploratory | 14_to_8_days | 0.280 / 4.486 | 0.311 / 4.824 | +0.0309 | +0.3384 |
| combined_exploratory | 180_to_91_days | 0.280 / 4.486 | 0.314 / 5.046 | +0.0335 | +0.5599 |
| combined_exploratory | 30_to_15_days | 0.280 / 4.486 | 0.319 / 4.361 | +0.0385 | -0.1248 |
| combined_exploratory | 7_to_4_days | 0.280 / 4.486 | 0.239 / 4.498 | -0.0407 | +0.0123 |
| combined_exploratory | 90_to_31_days | 0.280 / 4.486 | 0.317 / 4.258 | +0.0372 | -0.2281 |
| combined_exploratory | final_72_hours | 0.280 / 4.486 | 0.137 / 4.271 | -0.1432 | -0.2151 |
| national_exploratory | 14_to_8_days | 0.280 / 4.486 | 0.281 / 4.486 | +0.0011 | -0.0003 |
| national_exploratory | 180_to_91_days | 0.280 / 4.486 | 0.318 / 5.061 | +0.0379 | +0.5748 |
| national_exploratory | 30_to_15_days | 0.280 / 4.486 | 0.654 / 4.528 | +0.3735 | +0.0415 |
| national_exploratory | 7_to_4_days | 0.280 / 4.486 | 0.267 / 4.490 | -0.0133 | +0.0039 |
| national_exploratory | 90_to_31_days | 0.280 / 4.486 | 0.357 / 4.239 | +0.0766 | -0.2475 |
| national_exploratory | final_72_hours | 0.280 / 4.486 | 0.212 / 4.507 | -0.0685 | +0.0211 |

Reading this table honestly requires one arithmetic fact: the pooled bias is pinned near zero by contest normalisation (every contest's shares sum to 100, so pooled over-predictions and under-predictions largely cancel). A party-level tide-gauge correction therefore does NOT appear in the pooled bias column - it appears as pooled dispersion, because shifting parties' relative levels re-arranges errors across candidates. The observed pattern - dispersion falls in exactly the mid-range windows where MAE improved (90-31 and 30-15 days) and rises where MAE worsened (180-91 days) - is consistent with the tide-gauge reading in that pooled form. The sharper per-party test follows.

## 2b. Per-party bias against dispersion (the declared refinement)

Split by party the normalisation pinning disappears: each party's
bias is the election-wide level error a broadcast adjustment CAN
move, and its dispersion is the ward geography it cannot. Reform,
the central party, across all twelve specifications (signed bias:
positive = over-predicted):

| analysis | window | bias base -> news | dispersion base -> news |
| --- | --- | --- | --- |
| combined_exploratory | 14_to_8_days | -1.345 -> +5.155 | 3.172 -> 3.152 |
| combined_exploratory | 180_to_91_days | -1.345 -> -5.962 | 3.172 -> 3.209 |
| combined_exploratory | 30_to_15_days | -1.345 -> -1.822 | 3.172 -> 3.189 |
| combined_exploratory | 7_to_4_days | -1.345 -> -1.296 | 3.172 -> 3.158 |
| combined_exploratory | 90_to_31_days | -1.345 -> -3.164 | 3.172 -> 3.196 |
| combined_exploratory | final_72_hours | -1.345 -> -4.755 | 3.172 -> 3.121 |
| national_exploratory | 14_to_8_days | -1.345 -> -1.346 | 3.172 -> 3.173 |
| national_exploratory | 180_to_91_days | -1.345 -> -6.044 | 3.172 -> 3.211 |
| national_exploratory | 30_to_15_days | -1.345 -> -1.961 | 3.172 -> 3.322 |
| national_exploratory | 7_to_4_days | -1.345 -> -1.329 | 3.172 -> 3.167 |
| national_exploratory | 90_to_31_days | -1.345 -> -3.095 | 3.172 -> 3.212 |
| national_exploratory | final_72_hours | -1.345 -> -1.263 | 3.172 -> 3.149 |

All parties in the headline 90-31-day window (change from the baseline; negative = the news model reduced that error component):

| party | combined d-abs-bias | combined d-dispersion | national d-abs-bias | national d-dispersion |
| --- | ---: | ---: | ---: | ---: |
| conservative | -1.739 | +0.013 | -1.768 | +0.013 |
| green | +1.103 | +0.009 | +1.212 | +0.018 |
| labour | -0.501 | +0.024 | -0.781 | +0.055 |
| liberal_democrat | -2.756 | +0.026 | -2.651 | +0.050 |
| reform_uk | +1.820 | +0.024 | +1.751 | +0.040 |

In the combined 90-31-day specification, 5 of 5 parties saw their level error move by more than 0.05 points while 0 saw their ward-level dispersion move by that much - the tide-gauge reading predicts the first number to be the larger one.
