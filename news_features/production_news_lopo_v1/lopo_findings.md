# Leave-one-party-out robustness of the production news experiment

**This is a training-sensitivity audit, not model selection.** It uses 2017 fitting data and 2021 validation only; the 2026 holdout file was not read. Positive MAE differences mean news beats that omission's training-only recalibration.

## Design

- Omitted in turn: conservative, green, labour, liberal_democrat, ukip.
- Four party-level rows remain in each refit.
- The two frozen features, ridge penalty 1.0 and all six confirmed windows are unchanged.
- Cumulative periods are excluded because they are sensitivity analyses.
- Conditional contest bootstraps are not repeated: the uncertainty being tested here is removal of one independent training party.

## Summary by omitted party

| omitted party | comparisons | overall improvements | coefficient sign flips | minimum MAE difference | maximum MAE difference |
| --- | ---: | ---: | ---: | ---: | ---: |
| conservative | 18 | 6 | 3 | -10.8612 | +0.5350 |
| green | 18 | 0 | 4 | -13.0323 | +0.0000 |
| labour | 18 | 0 | 2 | -12.4428 | +0.0000 |
| liberal_democrat | 18 | 0 | 5 | -11.9926 | +0.0000 |
| ukip | 18 | 0 | 4 | -12.6086 | +0.0000 |

## Apparent improvements after omission

These rows are reported for completeness, not as candidate models. Positive values mean lower overall MAE than that omission's training-only recalibrated control.

| omitted | analysis | period | full-model difference | omission difference | Reform difference | sign flips |
| --- | --- | --- | ---: | ---: | ---: | --- |
| conservative | combined_exploratory | 180_to_91_days | -1.9277 | +0.3683 | +7.9633 | none |
| conservative | combined_exploratory | 90_to_31_days | -2.0495 | +0.3486 | +7.0768 | net_portrayal_share |
| conservative | national_exploratory | 180_to_91_days | -1.7787 | +0.5350 | +7.9633 | none |
| conservative | national_exploratory | 30_to_15_days | -1.3089 | +0.3901 | +5.2852 | none |
| conservative | national_exploratory | 14_to_8_days | -1.7768 | +0.0328 | +6.9530 | none |
| conservative | local_sensitivity | 180_to_91_days | -0.8687 | +0.1130 | +7.5200 | none |

## All 90 robustness comparisons

| omitted | analysis | period | full MAE difference | LOPO MAE difference | change from full | Reform MAE difference | sign flips |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| conservative | combined_exploratory | 180_to_91_days | -1.9277 | +0.3683 | +2.2959 | +7.9633 | none |
| conservative | combined_exploratory | 90_to_31_days | -2.0495 | +0.3486 | +2.3981 | +7.0768 | net_portrayal_share |
| conservative | combined_exploratory | 30_to_15_days | -6.0644 | -4.7498 | +1.3146 | +7.9633 | net_portrayal_share |
| conservative | combined_exploratory | 14_to_8_days | -3.5963 | -2.3924 | +1.2038 | +7.9633 | none |
| conservative | combined_exploratory | 7_to_4_days | -4.2207 | -1.7846 | +2.4361 | -14.2479 | none |
| conservative | combined_exploratory | final_72_hours | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| conservative | national_exploratory | 180_to_91_days | -1.7787 | +0.5350 | +2.3136 | +7.9633 | none |
| conservative | national_exploratory | 90_to_31_days | -2.8080 | -0.4618 | +2.3462 | +6.9701 | national_net_portrayal_share |
| conservative | national_exploratory | 30_to_15_days | -1.3089 | +0.3901 | +1.6990 | +5.2852 | none |
| conservative | national_exploratory | 14_to_8_days | -1.7768 | +0.0328 | +1.8095 | +6.9530 | none |
| conservative | national_exploratory | 7_to_4_days | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| conservative | national_exploratory | final_72_hours | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| conservative | local_sensitivity | 180_to_91_days | -0.8687 | +0.1130 | +0.9817 | +7.5200 | none |
| conservative | local_sensitivity | 90_to_31_days | -1.7799 | -0.8419 | +0.9380 | +2.3122 | none |
| conservative | local_sensitivity | 30_to_15_days | -7.8443 | -5.6367 | +2.2077 | +7.9633 | none |
| conservative | local_sensitivity | 14_to_8_days | -12.9868 | -10.8612 | +2.1256 | +7.9633 | none |
| conservative | local_sensitivity | 7_to_4_days | -4.2207 | -1.7846 | +2.4361 | -14.2479 | none |
| conservative | local_sensitivity | final_72_hours | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| green | combined_exploratory | 180_to_91_days | -1.9277 | -1.1005 | +0.8272 | +9.6897 | none |
| green | combined_exploratory | 90_to_31_days | -2.0495 | -1.6406 | +0.4089 | +8.1630 | net_portrayal_share |
| green | combined_exploratory | 30_to_15_days | -6.0644 | -2.2446 | +3.8198 | +10.1654 | net_portrayal_share |
| green | combined_exploratory | 14_to_8_days | -3.5963 | -3.4075 | +0.1887 | +10.1633 | none |
| green | combined_exploratory | 7_to_4_days | -4.2207 | -1.7827 | +2.4380 | -19.9808 | none |
| green | combined_exploratory | final_72_hours | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| green | national_exploratory | 180_to_91_days | -1.7787 | -0.6897 | +1.0890 | +8.2462 | none |
| green | national_exploratory | 90_to_31_days | -2.8080 | -2.1070 | +0.7011 | +8.1684 | national_net_portrayal_share |
| green | national_exploratory | 30_to_15_days | -1.3089 | -0.2840 | +1.0249 | +5.5641 | none |
| green | national_exploratory | 14_to_8_days | -1.7768 | -1.6663 | +0.1105 | +7.7525 | none |
| green | national_exploratory | 7_to_4_days | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| green | national_exploratory | final_72_hours | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| green | local_sensitivity | 180_to_91_days | -0.8687 | -0.7483 | +0.1204 | +5.1931 | none |
| green | local_sensitivity | 90_to_31_days | -1.7799 | -1.5737 | +0.2061 | +6.1348 | none |
| green | local_sensitivity | 30_to_15_days | -7.8443 | -3.7077 | +4.1366 | +9.5348 | local_net_portrayal_share |
| green | local_sensitivity | 14_to_8_days | -12.9868 | -13.0323 | -0.0455 | +10.1633 | none |
| green | local_sensitivity | 7_to_4_days | -4.2207 | -1.7827 | +2.4380 | -19.9808 | none |
| green | local_sensitivity | final_72_hours | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| labour | combined_exploratory | 180_to_91_days | -1.9277 | -3.2266 | -1.2990 | +9.2653 | none |
| labour | combined_exploratory | 90_to_31_days | -2.0495 | -2.3861 | -0.3366 | +9.6093 | net_portrayal_share |
| labour | combined_exploratory | 30_to_15_days | -6.0644 | -5.9234 | +0.1410 | +9.2653 | none |
| labour | combined_exploratory | 14_to_8_days | -3.5963 | -3.4834 | +0.1128 | +9.2653 | none |
| labour | combined_exploratory | 7_to_4_days | -4.2207 | -4.3684 | -0.1478 | -20.9427 | none |
| labour | combined_exploratory | final_72_hours | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| labour | national_exploratory | 180_to_91_days | -1.7787 | -3.1711 | -1.3925 | +9.2653 | none |
| labour | national_exploratory | 90_to_31_days | -2.8080 | -3.7587 | -0.9506 | +10.1144 | national_net_portrayal_share |
| labour | national_exploratory | 30_to_15_days | -1.3089 | -1.4152 | -0.1063 | +9.4078 | none |
| labour | national_exploratory | 14_to_8_days | -1.7768 | -1.9902 | -0.2134 | +9.8291 | none |
| labour | national_exploratory | 7_to_4_days | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| labour | national_exploratory | final_72_hours | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| labour | local_sensitivity | 180_to_91_days | -0.8687 | -0.7237 | +0.1450 | +8.0069 | none |
| labour | local_sensitivity | 90_to_31_days | -1.7799 | -1.4796 | +0.3002 | +6.9724 | none |
| labour | local_sensitivity | 30_to_15_days | -7.8443 | -7.0923 | +0.7520 | +9.2653 | none |
| labour | local_sensitivity | 14_to_8_days | -12.9868 | -12.4428 | +0.5440 | +9.2653 | none |
| labour | local_sensitivity | 7_to_4_days | -4.2207 | -4.3684 | -0.1478 | -20.9427 | none |
| labour | local_sensitivity | final_72_hours | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| liberal_democrat | combined_exploratory | 180_to_91_days | -1.9277 | -2.6237 | -0.6961 | +8.9453 | net_portrayal_share |
| liberal_democrat | combined_exploratory | 90_to_31_days | -2.0495 | -1.9697 | +0.0799 | +8.9895 | none |
| liberal_democrat | combined_exploratory | 30_to_15_days | -6.0644 | -6.4697 | -0.4053 | +8.5160 | none |
| liberal_democrat | combined_exploratory | 14_to_8_days | -3.5963 | -3.0104 | +0.5858 | +8.5160 | none |
| liberal_democrat | combined_exploratory | 7_to_4_days | -4.2207 | -8.0230 | -3.8023 | -15.4869 | none |
| liberal_democrat | combined_exploratory | final_72_hours | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| liberal_democrat | national_exploratory | 180_to_91_days | -1.7787 | -2.7014 | -0.9227 | +8.8163 | national_net_portrayal_share |
| liberal_democrat | national_exploratory | 90_to_31_days | -2.8080 | -3.0527 | -0.2446 | +9.0926 | none |
| liberal_democrat | national_exploratory | 30_to_15_days | -1.3089 | -5.2969 | -3.9880 | +9.1268 | national_net_portrayal_share |
| liberal_democrat | national_exploratory | 14_to_8_days | -1.7768 | -1.0041 | +0.7727 | +8.4145 | none |
| liberal_democrat | national_exploratory | 7_to_4_days | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| liberal_democrat | national_exploratory | final_72_hours | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| liberal_democrat | local_sensitivity | 180_to_91_days | -0.8687 | -1.1150 | -0.2463 | +8.9976 | local_net_portrayal_share |
| liberal_democrat | local_sensitivity | 90_to_31_days | -1.7799 | -2.0162 | -0.2363 | +8.7487 | local_net_portrayal_share |
| liberal_democrat | local_sensitivity | 30_to_15_days | -7.8443 | -7.5630 | +0.2813 | +8.5160 | none |
| liberal_democrat | local_sensitivity | 14_to_8_days | -12.9868 | -11.9926 | +0.9942 | +8.5160 | none |
| liberal_democrat | local_sensitivity | 7_to_4_days | -4.2207 | -8.0230 | -3.8023 | -15.4869 | none |
| liberal_democrat | local_sensitivity | final_72_hours | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| ukip | combined_exploratory | 180_to_91_days | -1.9277 | -1.6697 | +0.2580 | +6.1683 | net_portrayal_share |
| ukip | combined_exploratory | 90_to_31_days | -2.0495 | -2.0099 | +0.0396 | +1.0716 | none |
| ukip | combined_exploratory | 30_to_15_days | -6.0644 | -8.4236 | -2.3592 | +10.1995 | net_portrayal_share |
| ukip | combined_exploratory | 14_to_8_days | -3.5963 | -3.9655 | -0.3692 | +10.1995 | none |
| ukip | combined_exploratory | 7_to_4_days | -4.2207 | -3.2266 | +0.9941 | -11.7723 | none |
| ukip | combined_exploratory | final_72_hours | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| ukip | national_exploratory | 180_to_91_days | -1.7787 | -1.7057 | +0.0729 | +5.6432 | national_net_portrayal_share |
| ukip | national_exploratory | 90_to_31_days | -2.8080 | -2.4072 | +0.4009 | -1.2083 | none |
| ukip | national_exploratory | 30_to_15_days | -1.3089 | -1.1707 | +0.1382 | -1.7974 | national_net_portrayal_share |
| ukip | national_exploratory | 14_to_8_days | -1.7768 | -2.7735 | -0.9968 | +10.3444 | none |
| ukip | national_exploratory | 7_to_4_days | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| ukip | national_exploratory | final_72_hours | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |
| ukip | local_sensitivity | 180_to_91_days | -0.8687 | -1.3638 | -0.4950 | +9.1169 | none |
| ukip | local_sensitivity | 90_to_31_days | -1.7799 | -1.4860 | +0.2939 | +6.4291 | none |
| ukip | local_sensitivity | 30_to_15_days | -7.8443 | -11.4076 | -3.5633 | +10.1995 | none |
| ukip | local_sensitivity | 14_to_8_days | -12.9868 | -12.6086 | +0.3782 | +10.1995 | none |
| ukip | local_sensitivity | 7_to_4_days | -4.2207 | -3.2266 | +0.9941 | -11.7723 | none |
| ukip | local_sensitivity | final_72_hours | +0.0000 | +0.0000 | +0.0000 | +0.0000 | none |

## Verdict

`unstable_single_party_omissions_create_improvements`

Across 90 omission refits, 6 produce an overall improvement over their recalibrated control.

If this count is non-zero, the primary 0/18 finding is sensitive to which single party is present in the four-row fit. Such rows are not alternative models and must not be selected. If it is zero, the direction of the primary confirmed-window conclusion survives every single-party omission, although the one-election/four-row refits still cannot establish a general news effect or a Reform-specific effect.

The complete JSON also preserves clipping counts and parties outside the reduced training range for every comparison. Contest bootstraps are intentionally not repeated here: the primary experiment already records conditional 2021 contest-sampling intervals, while this audit isolates sensitivity to the independent training-party rows.
