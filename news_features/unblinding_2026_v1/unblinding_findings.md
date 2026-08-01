# The 2026 unblinding

**One-time confirmatory comparison, performed on the frozen,
hash-verified prediction files. Every specification is reported;
nothing was selected after outcomes were seen.**

## The untouched baseline on 2026

- Overall MAE 4.5140 across 832 candidate rows in 81 two-member wards; seat-call accuracy 0.7188.
- Reform UK: MAE 3.2318 over 162 rows; seat-call accuracy 0.9136.

## Confirmatory family - v1 primary (pooled 2017+2021)

| analysis | window | baseline MAE | recalibrated MAE | news MAE | news vs recalibrated | 95% CI | Reform news MAE | Reform vs recalibrated |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| combined_exploratory | 14_to_8_days | 4.4410 | 4.4414 | 4.9776 | -0.5362 | [-0.7785, -0.2697] | 4.9883 | -1.5070 |
| combined_exploratory | 180_to_91_days | 4.4410 | 4.4414 | 4.7527 | -0.3113 | [-0.4852, -0.1443] | 3.9278 | -0.4465 |
| combined_exploratory | 30_to_15_days | 4.4410 | 4.4414 | 5.3567 | -0.9154 | [-1.2033, -0.6375] | 4.7537 | -1.2724 |
| combined_exploratory | 7_to_4_days | 4.4410 | 4.4414 | 6.6352 | -2.1938 | [-2.4867, -1.8964] | 5.6650 | -2.1837 |
| combined_exploratory | 90_to_31_days | 4.4410 | 4.4414 | 4.8400 | -0.3986 | [-0.5900, -0.2178] | 3.9754 | -0.4941 |
| combined_exploratory | final_72_hours | 4.4410 | 4.4414 | 4.9563 | -0.5149 | [-1.1367, +0.0916] | 6.5650 | -3.0837 |
| national_exploratory | 14_to_8_days | 4.4410 | 4.4414 | 7.0398 | -2.5985 | [-2.9094, -2.2838] | 6.2019 | -2.7206 |
| national_exploratory | 180_to_91_days | 4.4410 | 4.4414 | 4.7351 | -0.2938 | [-0.4771, -0.1260] | 4.0261 | -0.5448 |
| national_exploratory | 30_to_15_days | 4.4410 | 4.4414 | 5.5763 | -1.1350 | [-1.6255, -0.6692] | 5.0860 | -1.6047 |
| national_exploratory | 7_to_4_days | 4.4410 | 4.4414 | 4.4414 | +0.0000 | [+0.0000, +0.0000] | 3.4813 | +0.0000 |
| national_exploratory | 90_to_31_days | 4.4410 | 4.4414 | 4.8704 | -0.4290 | [-0.6424, -0.2303] | 4.2052 | -0.7239 |
| national_exploratory | final_72_hours | 4.4410 | 4.4414 | 4.4591 | -0.0177 | [-0.0311, -0.0034] | 3.5157 | -0.0343 |

- **0 of 12** confirmatory comparisons improve overall MAE over the recalibrated control; **0 of 12** over the untouched baseline.

## Confirmatory family - v2 enrichment (2017+2021+by-elections)

| analysis | window | baseline MAE | recalibrated MAE | news MAE | news vs recalibrated | 95% CI | Reform news MAE | Reform vs recalibrated |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| combined_exploratory | 14_to_8_days | 4.4410 | 4.4454 | 4.7707 | -0.3252 | [-0.5690, -0.0585] | 5.4950 | -2.2729 |
| combined_exploratory | 180_to_91_days | 4.4410 | 4.4454 | 5.0206 | -0.5751 | [-0.9339, -0.2446] | 6.0267 | -2.8046 |
| combined_exploratory | 30_to_15_days | 4.4410 | 4.4454 | 4.3116 | +0.1339 | [+0.0949, +0.1689] | 3.3696 | -0.1475 |
| combined_exploratory | 7_to_4_days | 4.4410 | 4.4454 | 4.4551 | -0.0097 | [-0.0177, -0.0019] | 3.2021 | +0.0200 |
| combined_exploratory | 90_to_31_days | 4.4410 | 4.4454 | 4.2051 | +0.2404 | [+0.0781, +0.3866] | 3.9099 | -0.6877 |
| combined_exploratory | final_72_hours | 4.4410 | 4.4454 | 4.2572 | +0.1882 | [-0.2298, +0.5838] | 4.9435 | -1.7214 |
| national_exploratory | 14_to_8_days | 4.4410 | 4.4454 | 4.4406 | +0.0048 | [+0.0008, +0.0090] | 3.2326 | -0.0105 |
| national_exploratory | 180_to_91_days | 4.4410 | 4.4454 | 5.0351 | -0.5896 | [-0.9472, -0.2625] | 6.1043 | -2.8822 |
| national_exploratory | 30_to_15_days | 4.4410 | 4.4454 | 4.4611 | -0.0156 | [-0.1237, +0.0991] | 3.5737 | -0.3515 |
| national_exploratory | 7_to_4_days | 4.4410 | 4.4454 | 4.4454 | +0.0000 | [+0.0000, +0.0000] | 3.2221 | +0.0000 |
| national_exploratory | 90_to_31_days | 4.4410 | 4.4454 | 4.1773 | +0.2682 | [+0.1088, +0.4110] | 3.8875 | -0.6654 |
| national_exploratory | final_72_hours | 4.4410 | 4.4454 | 4.4686 | -0.0231 | [-0.0386, -0.0080] | 3.1861 | +0.0360 |

- **5 of 12** confirmatory comparisons improve overall MAE over the recalibrated control; **5 of 12** over the untouched baseline.

## Sensitivity families

- v1: 4 of 60 sensitivity comparisons improve on their recalibrated control (full detail in unblinding_results.json; sensitivity results cannot be promoted).
- v2: 14 of 24 sensitivity comparisons improve on their recalibrated control (full detail in unblinding_results.json; sensitivity results cannot be promoted).

## Interpretation rule (pre-declared, reproduced verbatim in the
frozen protocols)

No specification, window, arm or variant may be selected or
promoted because of these numbers. The confirmatory counts above,
with their bootstrap intervals, are the project's answer to the
supervisor's central question.
