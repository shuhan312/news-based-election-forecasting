# Party identity, volume and within-party tone in one specification

**EXPLORATORY combined specification, post-unblinding. The final cell of the identity factorial: party identity, volume and within-party tone in one fit, on the 45 frozen fitting cells and the frozen prediction and scoring code. Promotes nothing.**

Delta is the change in election-wide MAE against the recalibrated control; positive is better. Every arm shares the 45 frozen fitting cells and the frozen prediction and scoring code; only `feature_columns` differs.

## Reproduction gates

The frozen specification reproduces its committed deltas to **0.0000**; the four nested comparator arms reproduce their committed identity-placebo deltas to a maximum drift of **0.0e+00**. The run aborts if either gate fails.

## The factorial, every window

| arm | 180-to-91-days | 90-to-31-days | 30-to-15-days | 14-to-8-days | 7-to-4-days | final-72-hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| frozen | -0.5751 | +0.2404 | +0.1339 | -0.3252 | -0.0097 | +0.1882 |
| placebo_party_dummies | +0.8342 | +0.8342 | +0.8342 | +0.8342 | +0.8342 | +0.8342 |
| party_dummies_plus_share | +0.8379 | +0.7611 | +0.6616 | +0.8783 | +0.8162 | +0.7143 |
| party_dummies_plus_tone_within | +0.7343 | +0.7118 | +0.6453 | -0.5782 | +0.8342 | +0.2746 |
| tone_within_party | -1.2548 | +0.3784 | +0.0628 | -1.4738 | -0.0084 | +0.4313 |
| party_dummies_plus_volume_and_tone_within | +0.7160 | +0.6382 | +0.3847 | -0.8416 | +0.8092 | +0.1840 |

## The headline window, 90_to_31_days

The full specification scores **+0.6382** [+0.2733, +1.0143] against the recalibrated control.

## What each ingredient adds, paired per window

Each contrast resamples the same 81 contests once per draw and scores both arms on that draw; positive means the full specification beats the nested one. `vs_party_dummies_plus_share` is the decisive contrast: what the tone deviation adds once identity and volume are both known.

| window | vs identity alone | vs identity+volume (tone's marginal) | vs identity+tone (volume's marginal) | vs volume+tone (identity's marginal) |
| --- | ---: | ---: | ---: | ---: |
| 180-to-91-days | -0.1182 [-0.3294, +0.0880] | -0.1218 [-0.3261, +0.0777] | -0.0182 [-0.0306, -0.0072] | +1.9708 [+1.6322, +2.3135] |
| 90-to-31-days | -0.1960 [-0.2741, -0.1203] | -0.1229 [-0.1595, -0.0879] | -0.0736 [-0.1041, -0.0456] | +0.2598 [-0.0784, +0.5898] |
| 30-to-15-days | -0.4496 [-0.6034, -0.3086] | -0.2770 [-0.4112, -0.1517] | -0.2607 [-0.3049, -0.2196] | +0.3219 [-0.0989, +0.7291] |
| 14-to-8-days | -1.6758 [-1.9385, -1.4015] | -1.7199 [-1.9521, -1.4655] | -0.2633 [-0.3188, -0.2080] | +0.6322 [+0.3566, +0.8907] |
| 7-to-4-days | -0.0250 [-0.0322, -0.0179] | -0.0070 [-0.0089, -0.0050] | -0.0250 [-0.0322, -0.0179] | +0.8176 [+0.5005, +1.1445] |
| final-72-hours | -0.6503 [-0.9425, -0.3645] | -0.5303 [-0.8180, -0.2595] | -0.0906 [-0.1073, -0.0738] | -0.2474 [-0.4211, -0.0563] |

## Coefficients of the full arm

| window | coefficients |
| --- | --- |
| 180_to_91_days | party_is_conservative -0.960, party_is_green -0.937, party_is_labour -1.248, party_is_liberal_democrat +3.277, party_is_reform_uk +1.783, party_is_ukip -2.570, party_article_share -0.209, net_portrayal_share_within +1.943 |
| 90_to_31_days | party_is_conservative -0.934, party_is_green -0.963, party_is_labour -1.216, party_is_liberal_democrat +3.270, party_is_reform_uk +1.773, party_is_ukip -2.597, party_article_share -0.374, net_portrayal_share_within +0.603 |
| 30_to_15_days | party_is_conservative -0.960, party_is_green -0.946, party_is_labour -1.201, party_is_liberal_democrat +3.237, party_is_reform_uk +1.798, party_is_ukip -2.592, party_article_share -0.582, net_portrayal_share_within -0.826 |
| 14_to_8_days | party_is_conservative -0.926, party_is_green -0.806, party_is_labour -1.405, party_is_liberal_democrat +3.254, party_is_reform_uk +1.806, party_is_ukip -2.551, party_article_share +0.855, net_portrayal_share_within +0.752 |
| 7_to_4_days | party_is_conservative -0.988, party_is_green -0.919, party_is_labour -1.289, party_is_liberal_democrat +3.293, party_is_reform_uk +1.832, party_is_ukip -2.580, party_article_share +0.260, net_portrayal_share_within +1.401 |
| final_72_hours | party_is_conservative -0.980, party_is_green -0.919, party_is_labour -1.254, party_is_liberal_democrat +3.275, party_is_reform_uk +1.779, party_is_ukip -2.550, party_article_share -0.341, net_portrayal_share_within +1.275 |
