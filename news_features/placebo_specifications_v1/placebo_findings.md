# Does the LLM layer beat counting articles?

**EXPLORATORY placebo comparison, post-unblinding. Every arm shares the frozen fitting cells, prediction code and scoring code; only `feature_columns` differs. Promotes nothing.**

Delta is the change in election-wide MAE against the recalibrated control; positive is better. Every arm shares the 45 frozen fitting cells and the frozen prediction and scoring code, so the only thing that differs between rows is which columns the model was given.

## Reproduction gate

The frozen specification reproduces its committed deltas to a maximum absolute difference of **0.0000**. The run aborts if it does not, because a harness that cannot land on a known answer cannot be trusted with an unknown one.

## Every arm, every window

A dash means the content feature did not clear the 10-value reporting bar in that window's training rows and was not fitted. Only the two long windows carry enough coverage for any content feature at all.

| arm | 180-to-91 | 90-to-31 | 30-to-15 | 14-to-8 | 7-to-4 | final-72-hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| frozen | -0.5751 | +0.2404 | +0.1339 | -0.3252 | -0.0097 | +0.1882 |
| placebo_volume | +0.1684 | +0.2247 | +0.1259 | -0.0043 | -0.0148 | +0.0221 |
| placebo_volume_tone | +0.1892 | +0.3413 | -0.0261 | +0.0742 | -0.0149 | +0.2781 |
| content_party_issue_immigration_share | +0.0958 | +0.3202 | - | - | - | - |
| content_party_issue_national_politics_share | -0.5763 | +0.2050 | - | - | - | - |
| content_party_issue_issue_other_share | -0.5767 | +0.3446 | - | - | - | - |
| content_party_frame_incumbent_judgement_share | -0.6094 | +0.5718 | - | - | - | - |
| content_party_frame_challenger_emergence_share | -0.5047 | +0.3167 | - | - | - | - |
| content_party_frame_voter_discontent_share | -0.5758 | +0.1761 | - | - | - | - |
| content_party_frame_local_impact_share | -0.6554 | +0.2903 | - | - | - | - |
| content_all_eligible | -0.1071 | -0.6635 | - | - | - | - |

## How much of the result is just volume

- **90_to_31_days**: frozen +0.2404, a raw article count alone +0.2247 - **93%** of the frozen result, with no content judgement of any kind.
- **30_to_15_days**: frozen +0.1339, a raw article count alone +0.1259 - **94%** of the frozen result, with no content judgement of any kind.
- The count also avoids the frozen specification's largest harm, turning 180-91 days from -0.5751 into +0.1684.

## Content features against the bar, 90_to_31_days

The bar is **placebo_volume_tone = +0.3413**, the best arm carrying no content judgement at all. Beating the frozen pair while losing to a counter would settle nothing, so that is the number to clear.

| content feature | delta | 95% CI | beats the bar |
| --- | ---: | --- | --- |
| party_frame_incumbent_judgement_share | +0.5718 | [+0.3864, +0.7533] | yes, interval clear of it |
| party_issue_issue_other_share | +0.3446 | [+0.1856, +0.4857] | yes, but within noise |
| party_issue_immigration_share | +0.3202 | [+0.1083, +0.5119] | no |
| party_frame_challenger_emergence_share | +0.3167 | [+0.1192, +0.5022] | no |
| party_frame_local_impact_share | +0.2903 | [+0.1326, +0.4374] | no |
| party_issue_national_politics_share | +0.2050 | [+0.0687, +0.3275] | no |
| party_frame_voter_discontent_share | +0.1761 | [+0.0095, +0.3331] | no |

**2 of 7** content features beat the bar; **1** does so with its whole interval above it - party_frame_incumbent_judgement_share.

Read this narrowly. Seven features were tried and reported, so one clearing a bar is a multiple-comparison result before it is anything else, and the fit has 45 cells. It is a reason to look harder at that feature, not a certified effect - the holdout that could have certified one is spent.

All eligible content features at once give **-0.6635** [-0.8436, -0.4841], worse than doing nothing and worse than every single-feature arm. Nine features on 45 cells is the overfitting this design expected to find, and finding it is the check working.

