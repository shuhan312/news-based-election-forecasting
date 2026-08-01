# Production news experiment: 2017 fitting, 2021 validation

**Status: exploratory pre-2026 result.** The Stage 1 holdout file was not read. Positive `news vs recalibrated` values mean lower MAE than a training-only mean-residual correction; negative values mean worse.

## Frozen design

- Fitting election: `surrey-county-council-2017`.
- Validation election: `surrey-county-council-2021`.
- Independent fitting rows: 5 parties (conservative, green, labour, liberal_democrat, ukip).
- Reform fitting rows: 0; Reform validation candidate rows: 6.
- Ridge penalty: 1.0, fixed before validation; no tuning on 2021.
- News features are fitted at party grain, then contest predictions are clipped at zero and renormalised to 100.
- Contest-bootstrap intervals condition on the fitted five-party model; they do not include uncertainty from having only one fitting election.

## Confirmed six-window results

| analysis | period | baseline MAE | recalibrated MAE | news MAE | news vs recalibrated | 95% contest-bootstrap CI | Reform news MAE | Reform vs recalibrated | parties outside training range |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| combined_exploratory | 180_to_91_days | 7.1585 | 7.5872 | 9.5148 | -1.9277 | [-2.5812, -1.2713] | 1.9517 | +10.2570 | 5 |
| combined_exploratory | 90_to_31_days | 7.1585 | 7.5872 | 9.6367 | -2.0495 | [-2.7262, -1.3447] | 3.6904 | +8.5183 | 4 |
| combined_exploratory | 30_to_15_days | 7.1585 | 7.5872 | 13.6516 | -6.0644 | [-7.1783, -4.9406] | 2.8333 | +9.3754 | 6 |
| combined_exploratory | 14_to_8_days | 7.1585 | 7.5872 | 11.1834 | -3.5963 | [-4.3442, -2.8605] | 2.8333 | +9.3754 | 5 |
| combined_exploratory | 7_to_4_days | 7.1585 | 7.5872 | 11.8079 | -4.2207 | [-4.8026, -3.6020] | 30.7744 | -18.5656 | 3 |
| combined_exploratory | final_72_hours | 7.1585 | 7.5872 | 7.5872 | +0.0000 | [+0.0000, +0.0000] | 12.2087 | +0.0000 | 6 |
| national_exploratory | 180_to_91_days | 7.1585 | 7.5872 | 9.3659 | -1.7787 | [-2.4221, -1.1342] | 2.0971 | +10.1117 | 5 |
| national_exploratory | 90_to_31_days | 7.1585 | 7.5872 | 10.3952 | -2.8080 | [-3.5619, -2.0235] | 3.5177 | +8.6910 | 4 |
| national_exploratory | 30_to_15_days | 7.1585 | 7.5872 | 8.8961 | -1.3089 | [-1.7352, -0.9003] | 4.6481 | +7.5606 | 4 |
| national_exploratory | 14_to_8_days | 7.1585 | 7.5872 | 9.3640 | -1.7768 | [-2.6956, -0.8079] | 3.0460 | +9.1627 | 1 |
| national_exploratory | 7_to_4_days | 7.1585 | 7.5872 | 7.5872 | +0.0000 | [+0.0000, +0.0000] | 12.2087 | +0.0000 | 0 |
| national_exploratory | final_72_hours | 7.1585 | 7.5872 | 7.5872 | +0.0000 | [+0.0000, +0.0000] | 12.2087 | +0.0000 | 6 |
| local_sensitivity | 180_to_91_days | 7.1585 | 7.5872 | 8.4559 | -0.8687 | [-1.2731, -0.4540] | 3.8618 | +8.3469 | 3 |
| local_sensitivity | 90_to_31_days | 7.1585 | 7.5872 | 9.3671 | -1.7799 | [-2.3425, -1.2077] | 4.8114 | +7.3973 | 1 |
| local_sensitivity | 30_to_15_days | 7.1585 | 7.5872 | 15.4315 | -7.8443 | [-9.1960, -6.5288] | 2.8333 | +9.3754 | 6 |
| local_sensitivity | 14_to_8_days | 7.1585 | 7.5872 | 20.5740 | -12.9868 | [-14.7821, -11.1099] | 2.8333 | +9.3754 | 6 |
| local_sensitivity | 7_to_4_days | 7.1585 | 7.5872 | 11.8079 | -4.2207 | [-4.8026, -3.6020] | 30.7744 | -18.5656 | 3 |
| local_sensitivity | final_72_hours | 7.1585 | 7.5872 | 7.5872 | +0.0000 | [+0.0000, +0.0000] | 12.2087 | +0.0000 | 5 |

## Cumulative-period sensitivity results

| analysis | period | baseline MAE | recalibrated MAE | news MAE | news vs recalibrated | 95% contest-bootstrap CI | Reform news MAE | Reform vs recalibrated | parties outside training range |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| combined_exploratory | previous_72_hours | 7.1585 | 7.5872 | 7.5872 | +0.0000 | [+0.0000, +0.0000] | 12.2087 | +0.0000 | 6 |
| combined_exploratory | previous_7_days | 7.1585 | 7.5872 | 14.0305 | -6.4433 | [-7.5040, -5.4417] | 52.4436 | -40.2349 | 4 |
| combined_exploratory | previous_14_days | 7.1585 | 7.5872 | 8.0135 | -0.4263 | [-0.9147, +0.0448] | 2.8333 | +9.3754 | 5 |
| combined_exploratory | previous_30_days | 7.1585 | 7.5872 | 10.3196 | -2.7324 | [-3.3034, -2.1511] | 2.8333 | +9.3754 | 5 |
| combined_exploratory | previous_90_days | 7.1585 | 7.5872 | 9.4609 | -1.8737 | [-2.5139, -1.2165] | 2.8333 | +9.3754 | 5 |
| combined_exploratory | previous_180_days | 7.1585 | 7.5872 | 9.2929 | -1.7057 | [-2.3299, -1.0706] | 2.5570 | +9.6517 | 3 |
| national_exploratory | previous_72_hours | 7.1585 | 7.5872 | 7.5872 | +0.0000 | [+0.0000, +0.0000] | 12.2087 | +0.0000 | 6 |
| national_exploratory | previous_7_days | 7.1585 | 7.5872 | 7.5872 | +0.0000 | [+0.0000, +0.0000] | 12.2087 | +0.0000 | 6 |
| national_exploratory | previous_14_days | 7.1585 | 7.5872 | 6.5887 | +0.9985 | [+0.4858, +1.4881] | 1.9052 | +10.3036 | 1 |
| national_exploratory | previous_30_days | 7.1585 | 7.5872 | 6.9334 | +0.6538 | [+0.3326, +0.9693] | 2.2331 | +9.9756 | 2 |
| national_exploratory | previous_90_days | 7.1585 | 7.5872 | 9.1608 | -1.5736 | [-2.1876, -0.9501] | 2.5038 | +9.7049 | 4 |
| national_exploratory | previous_180_days | 7.1585 | 7.5872 | 9.2014 | -1.6142 | [-2.2406, -0.9808] | 1.8672 | +10.3415 | 4 |
| local_sensitivity | previous_72_hours | 7.1585 | 7.5872 | 7.5872 | +0.0000 | [+0.0000, +0.0000] | 12.2087 | +0.0000 | 5 |
| local_sensitivity | previous_7_days | 7.1585 | 7.5872 | 16.1375 | -8.5504 | [-9.5670, -7.4816] | 47.3822 | -35.1735 | 6 |
| local_sensitivity | previous_14_days | 7.1585 | 7.5872 | 12.2000 | -4.6128 | [-5.2887, -3.9169] | 2.8333 | +9.3754 | 4 |
| local_sensitivity | previous_30_days | 7.1585 | 7.5872 | 17.1597 | -9.5725 | [-10.9568, -8.1251] | 2.8333 | +9.3754 | 6 |
| local_sensitivity | previous_90_days | 7.1585 | 7.5872 | 10.5942 | -3.0070 | [-3.5628, -2.4025] | 2.8333 | +9.3754 | 4 |
| local_sensitivity | previous_180_days | 7.1585 | 7.5872 | 9.4650 | -1.8778 | [-2.3063, -1.3830] | 2.7109 | +9.4978 | 4 |

## Findings that may be reported

- 0 of 18 confirmed-window arm comparisons improve overall MAE over the recalibrated control. The observed count is zero; non-zero confirmed-window differences worsen the score and zero differences reproduce the recalibrated control.
- The untouched Stage 1 baseline MAE on the 279 supported 2021 rows is 7.1585. The training-only recalibration MAE is 7.5872, so even the mean 2017 residual does not transfer cleanly to 2021.
- Reform-only changes are inconsistent across windows: several appear better, the 7-to-4-day window is markedly worse, and zero-signal periods are unchanged. With zero Reform fitting rows, these are party-generic extrapolations, not a learned Reform effect.
- 2 cumulative comparisons improve overall MAE. They are sensitivity results and cannot be promoted or selected because they looked better on 2021.
- Many validation party values fall outside their 2017 training ranges, and several specifications require negative raw shares to be clipped before contest normalisation. These are direct signs of unstable extrapolation from five party-level fitting rows.

## Conclusion

The confirmed-window experiment provides no evidence that these frozen news features improve overall 2021 prediction beyond a training-only recalibration. This is not evidence that news has no effect in general: the design has one fitting election, five party-level rows and no Reform training observation. Local remains sensitivity-only, no result is causal, and 2026 remains sealed.
