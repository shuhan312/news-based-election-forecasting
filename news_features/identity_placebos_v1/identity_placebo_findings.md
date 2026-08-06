# Is the news layer anything more than the party's name?

**EXPLORATORY identity placebo, post-unblinding. Every arm shares the 45 frozen fitting cells and the frozen prediction and scoring code; only `feature_columns` differs. Promotes nothing.**

Delta is the change in election-wide MAE against the recalibrated control; positive is better. Every arm shares the 45 frozen fitting cells and the frozen prediction and scoring code, so the only thing that differs between rows is which columns the model was given.

## Reproduction gate

The frozen specification reproduces its committed deltas to a maximum absolute difference of **0.0000**. The run aborts if it does not.

## Why this run exists

Variance of the two frozen features across the covered fitting cells, split into the part that separates parties from the part that separates elections within a party:

| window / column | covered cells | between parties | within a party |
| --- | ---: | ---: | ---: |
| 180_to_91_days/net_portrayal_share | 19 | 86.3% | 13.7% |
| 180_to_91_days/party_article_share | 19 | 71.5% | 28.5% |
| 90_to_31_days/net_portrayal_share | 19 | 64.3% | 35.7% |
| 90_to_31_days/party_article_share | 19 | 73.8% | 26.2% |

## Every arm, every window

| arm | 180-to-91-days | 90-to-31-days | 30-to-15-days | 14-to-8-days | 7-to-4-days | final-72-hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| frozen | -0.5751 | +0.2404 | +0.1339 | -0.3252 | -0.0097 | +0.1882 |
| placebo_party_dummies | +0.8342 | +0.8342 | +0.8342 | +0.8342 | +0.8342 | +0.8342 |
| placebo_reform_dummy | -0.0302 | -0.0302 | -0.0302 | -0.0302 | -0.0302 | -0.0302 |
| placebo_prior_vote_share | -0.0152 | -0.0152 | -0.0152 | -0.0152 | -0.0152 | -0.0152 |
| tone_within_party | -1.2548 | +0.3784 | +0.0628 | -1.4738 | -0.0084 | +0.4313 |
| tone_within_party_only | -0.9480 | +0.2291 | +0.0134 | -1.0594 | +0.0000 | +0.4863 |
| frozen_plus_party_dummies | +0.9580 | +0.8504 | +0.6120 | +0.6621 | +0.8278 | +0.1488 |
| party_dummies_plus_share | +0.8379 | +0.7611 | +0.6616 | +0.8783 | +0.8162 | +0.7143 |
| party_dummies_plus_tone_within | +0.7343 | +0.7118 | +0.6453 | -0.5782 | +0.8342 | +0.2746 |
| party_dummies_plus_incumbent_judgement | +0.7417 | +0.8734 | +0.8306 | +0.8786 | +0.8414 | +0.8636 |
| party_dummies_plus_immigration | +0.6948 | +0.8469 | +0.7556 | +0.8395 | +0.8342 | +0.8342 |
| tone_trajectory_only | -0.3193 | -0.3193 | -0.3193 | -0.3193 | -0.3193 | -0.3193 |
| party_dummies_plus_trajectory | +0.8204 | +0.8204 | +0.8204 | +0.8204 | +0.8204 | +0.8204 |
| party_dummies_plus_trajectory_and_level | +0.8864 | +0.8397 | +0.8838 | +0.8519 | +0.8032 | +0.2503 |

## The headline window, 90_to_31_days

The frozen specification scores **+0.2404** here. The question is how much of that survives an arm that never reads an article.

| arm | delta | 95% CI | share of the frozen result |
| --- | ---: | --- | ---: |
| frozen | +0.2404 | [+0.0781, +0.3866] | 100% |
| placebo_party_dummies | +0.8342 | [+0.5208, +1.1597] | 347% |
| placebo_reform_dummy | -0.0302 | [-0.2216, +0.1731] | -13% |
| placebo_prior_vote_share | -0.0152 | [-0.0788, +0.0485] | -6% |
| tone_within_party | +0.3784 | [+0.3024, +0.4503] | 157% |
| tone_within_party_only | +0.2291 | [+0.1669, +0.2876] | 95% |
| frozen_plus_party_dummies | +0.8504 | [+0.4572, +1.2504] | 354% |
| party_dummies_plus_share | +0.7611 | [+0.4202, +1.1124] | 317% |
| party_dummies_plus_tone_within | +0.7118 | [+0.3637, +1.0768] | 296% |
| party_dummies_plus_incumbent_judgement | +0.8734 | [+0.5838, +1.1643] | 363% |
| party_dummies_plus_immigration | +0.8469 | [+0.5389, +1.1663] | 352% |
| tone_trajectory_only | -0.3193 | [-0.4159, -0.2182] | -133% |
| party_dummies_plus_trajectory | +0.8204 | [+0.5068, +1.1448] | 341% |
| party_dummies_plus_trajectory_and_level | +0.8397 | [+0.4422, +1.2449] | 349% |

## Coefficients at the headline window

| arm | coefficients |
| --- | --- |
| frozen | party_article_share +0.175, net_portrayal_share +1.622 |
| placebo_party_dummies | party_is_conservative -0.980, party_is_green -0.904, party_is_labour -1.285, party_is_liberal_democrat +3.294, party_is_reform_uk +1.786, party_is_ukip -2.560 |
| placebo_reform_dummy | party_is_reform_uk +2.073 |
| placebo_prior_vote_share | prior_party_vote_share -0.636 |
| tone_within_party | party_article_share -0.689, net_portrayal_share_within +0.547 |
| tone_within_party_only | net_portrayal_share_within +0.670 |
| frozen_plus_party_dummies | party_article_share +0.322, net_portrayal_share +1.343, party_is_conservative -0.815, party_is_green -1.200, party_is_labour -1.383, party_is_liberal_democrat +3.106, party_is_reform_uk +2.023, party_is_ukip -2.299 |
| party_dummies_plus_share | party_is_conservative -0.919, party_is_green -0.981, party_is_labour -1.194, party_is_liberal_democrat +3.262, party_is_reform_uk +1.769, party_is_ukip -2.609, party_article_share -0.494 |
| party_dummies_plus_tone_within | party_is_conservative -0.980, party_is_green -0.904, party_is_labour -1.285, party_is_liberal_democrat +3.294, party_is_reform_uk +1.786, party_is_ukip -2.560, net_portrayal_share_within +0.670 |
| party_dummies_plus_incumbent_judgement | party_is_conservative -0.984, party_is_green -0.856, party_is_labour -1.295, party_is_liberal_democrat +3.243, party_is_reform_uk +1.800, party_is_ukip -2.547, party_frame_incumbent_judgement_share +0.835 |
| party_dummies_plus_immigration | party_is_conservative -0.953, party_is_green -0.901, party_is_labour -1.265, party_is_liberal_democrat +3.250, party_is_reform_uk +1.760, party_is_ukip -2.534, party_issue_immigration_share +0.241 |
| tone_trajectory_only | tone_trajectory -1.072 |
| party_dummies_plus_trajectory | party_is_conservative -0.988, party_is_green -0.901, party_is_labour -1.284, party_is_liberal_democrat +3.294, party_is_reform_uk +1.797, party_is_ukip -2.568, tone_trajectory +0.044 |
| party_dummies_plus_trajectory_and_level | party_is_conservative -0.778, party_is_green -1.211, party_is_labour -1.320, party_is_liberal_democrat +3.116, party_is_reform_uk +1.940, party_is_ukip -2.335, tone_trajectory -0.157, net_portrayal_share +1.154 |
