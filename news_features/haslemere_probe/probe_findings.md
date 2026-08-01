# The Haslemere probe: frozen v2 predictions on the 7 July contest

**EXPLORATORY, post-unblinding, pre-declared Haslemere case study: one contest, four candidates. Nothing here joins the confirmatory verdict.**

Reference: before-May baseline contest MAE 4.4738 (Reform signed error +8.95), after-May 7.3169 (Reform +14.63); both call the Liberal Democrat winner. Corpus: 20 articles, all local-arm, 3 naming any study party.

| analysis | window | news MAE | recal MAE | baseline MAE | news Reform error | news winner ok |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| combined_exploratory | 180_to_91_days | 8.418 | 4.491 | 4.474 | +8.81 | yes |
| combined_exploratory | 90_to_31_days | 4.290 | 4.491 | 4.474 | +8.58 | yes |
| combined_exploratory | 30_to_15_days | 4.596 | 4.491 | 4.474 | +9.19 | yes |
| combined_exploratory | 14_to_8_days | 4.437 | 4.491 | 4.474 | +8.88 | yes |
| combined_exploratory | 7_to_4_days | 4.527 | 4.491 | 4.474 | +9.05 | yes |
| combined_exploratory | final_72_hours | 4.564 | 4.491 | 4.474 | +9.13 | yes |
| national_exploratory | 180_to_91_days | 4.557 | 4.491 | 4.474 | +9.12 | yes |
| national_exploratory | 90_to_31_days | 4.580 | 4.491 | 4.474 | +9.16 | yes |
| national_exploratory | 30_to_15_days | 4.603 | 4.491 | 4.474 | +9.21 | yes |
| national_exploratory | 14_to_8_days | 4.472 | 4.491 | 4.474 | +8.95 | yes |
| national_exploratory | 7_to_4_days | 4.491 | 4.491 | 4.474 | +8.98 | yes |
| national_exploratory | final_72_hours | 4.565 | 4.491 | 4.474 | +9.13 | yes |

News beat its recalibrated control in **3 of 12** specifications; the news Reform error was smaller than the baseline's +8.95 in **4 of 12**.
