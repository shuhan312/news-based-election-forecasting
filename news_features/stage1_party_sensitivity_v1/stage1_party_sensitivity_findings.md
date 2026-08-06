# What does the Stage 1 re-run do to the headline?

**EXPLORATORY Stage 1 party-intercept sensitivity, post-unblinding. Simulates what happens to the news layer's headline when Stage 1 absorbs per-party mean residuals.**

## Per-party mean residual from the 45 fitting cells

| party | mean residual (pp) | adjusted in primary variant? |
| --- | ---: | --- |
| conservative | +2.8706 | yes |
| green | -5.0609 | yes |
| labour | +0.7264 | yes |
| liberal_democrat | +4.0472 | yes |
| reform_uk | -2.4010 | no (already has own indicator) |
| ukip | -12.6588 | no (already has own indicator) |

## Primary: Con/Lab/LibDem/Green offsets removed (Reform and UKIP unchanged)

| window | original | 95% CI | demeaned | 95% CI | survival |
| --- | ---: | --- | ---: | --- | ---: |
| 180_to_91_days | -0.5751 | [-0.9339, -0.2446] | +0.3921 | [+0.0196, +0.7566] | -68.2% |
| 90_to_31_days | +0.2404 | [+0.0781, +0.3866] | +0.3004 | [+0.0664, +0.5252] | 124.9% |
| 30_to_15_days | +0.1339 | [+0.0949, +0.1689] | +0.0919 | [+0.0329, +0.1469] | 68.6% |
| 14_to_8_days | -0.3252 | [-0.5690, -0.0585] | +0.0713 | [-0.1637, +0.3369] | -21.9% |
| 7_to_4_days | -0.0097 | [-0.0177, -0.0019] | +0.0255 | [+0.0191, +0.0317] | -263.5% |
| final_72_hours | +0.1882 | [-0.2298, +0.5838] | +0.2500 | [-0.1742, +0.6567] | 132.8% |

Headline (90-31 days): **+0.2404** -> **+0.3004**, survival **124.9%**.

## Sensitivity: all six parties' offsets removed

| window | original | 95% CI | demeaned | 95% CI | survival |
| --- | ---: | --- | ---: | --- | ---: |
| 180_to_91_days | -0.5751 | [-0.9339, -0.2446] | +0.3610 | [+0.1264, +0.5793] | -62.8% |
| 90_to_31_days | +0.2404 | [+0.0781, +0.3866] | +0.0428 | [-0.0661, +0.1461] | 17.8% |
| 30_to_15_days | +0.1339 | [+0.0949, +0.1689] | -0.2419 | [-0.3335, -0.1461] | -180.7% |
| 14_to_8_days | -0.3252 | [-0.5690, -0.0585] | +0.2624 | [+0.1332, +0.4031] | -80.7% |
| 7_to_4_days | -0.0097 | [-0.0177, -0.0019] | +0.0268 | [+0.0217, +0.0320] | -277.3% |
| final_72_hours | +0.1882 | [-0.2298, +0.5838] | +0.2358 | [-0.1089, +0.5580] | 125.3% |

Headline (90-31 days): **+0.2404** -> **+0.0428**, survival **17.8%**.

## Coefficient comparison at 90-31 days

| variant | party_article_share | net_portrayal_share |
| --- | ---: | ---: |
| original | +0.1753 | +1.6216 |
| established demeaned | -0.0957 | +1.9027 |
| all six demeaned | -1.5565 | +0.1761 |
