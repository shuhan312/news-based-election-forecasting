# Residual (A) versus joint stacked (B): the design's comparison

**EXPLORATORY, post-unblinding. This comparison cannot join the confirmatory verdict and no approach may be promoted from it.**

Fitted on the 45 v2 election x party cells across 10 pre-2026 elections; leave-one-election-out; frozen features and penalty throughout.

| analysis | window | A residual | B joint | baseline only | lower |
| --- | --- | ---: | ---: | ---: | --- |
| combined_exploratory | 180_to_91_days | 7.422 | 7.391 | 7.772 | B |
| combined_exploratory | 90_to_31_days | 8.113 | 8.255 | 7.772 | A |
| combined_exploratory | 30_to_15_days | 8.158 | 8.317 | 7.772 | A |
| combined_exploratory | 14_to_8_days | 7.679 | 7.875 | 7.772 | A |
| combined_exploratory | 7_to_4_days | 8.520 | 8.735 | 7.772 | A |
| combined_exploratory | final_72_hours | 9.102 | 9.239 | 7.772 | A |
| national_exploratory | 180_to_91_days | 7.416 | 7.382 | 7.772 | B |
| national_exploratory | 90_to_31_days | 8.115 | 8.257 | 7.772 | A |
| national_exploratory | 30_to_15_days | 8.172 | 8.345 | 7.772 | A |
| national_exploratory | 14_to_8_days | 7.653 | 7.819 | 7.772 | A |
| national_exploratory | 7_to_4_days | 7.807 | 8.029 | 7.772 | A |
| national_exploratory | final_72_hours | 8.885 | 9.019 | 7.772 | A |
| local_sensitivity | 180_to_91_days | 7.598 | 7.820 | 7.772 | A |
| local_sensitivity | 90_to_31_days | 8.036 | 8.300 | 7.772 | A |
| local_sensitivity | 30_to_15_days | 7.767 | 8.000 | 7.772 | A |
| local_sensitivity | 14_to_8_days | 8.168 | 8.417 | 7.772 | A |
| local_sensitivity | 7_to_4_days | 8.520 | 8.735 | 7.772 | A |
| local_sensitivity | final_72_hours | 7.813 | 8.019 | 7.772 | A |

**A lower in 16 of 18 specifications; B lower in 2.**
