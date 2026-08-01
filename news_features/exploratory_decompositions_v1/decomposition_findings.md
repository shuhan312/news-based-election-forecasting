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

Reading this table honestly requires one arithmetic fact: the pooled bias is pinned near zero by contest normalisation (every contest's shares sum to 100, so pooled over-predictions and under-predictions largely cancel). A party-level tide-gauge correction therefore does NOT appear in the pooled bias column - it appears as pooled dispersion, because shifting parties' relative levels re-arranges errors across candidates. The observed pattern - dispersion falls in exactly the mid-range windows where MAE improved (90-31 and 30-15 days) and rises where MAE worsened (180-91 days) - is consistent with the tide-gauge reading in that pooled form. The sharper test, a per-party bias decomposition, is not run here and would be the next refinement.
