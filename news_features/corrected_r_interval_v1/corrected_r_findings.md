# Attenuation-corrected correlation with bootstrap interval

**EXPLORATORY attenuation-corrected r with bootstrap interval, post-unblinding.**

Feature: `party_frame_incumbent_judgement_share`
Window: 90_to_31_days
Covered cells: 18
Pooled within-cell variance (sigma-squared): 96.238

## Point estimates

- Observed r: **+0.5013**
- Reliability: **0.5941**
- Corrected r = observed / sqrt(reliability): **+0.6504**

## Bootstrap intervals (10,000 resamples of cells)

| quantity | point estimate | 95% CI |
| --- | ---: | --- |
| observed r | +0.5013 | [-0.0427, +0.8173] |
| reliability | 0.5941 | [0.1989, 0.7552] |
| corrected r | +0.6504 | [-0.0647, +1.2671] |

The corrected r interval is wider than the observed r interval because dividing by sqrt(reliability) amplifies the uncertainty in both the numerator and the denominator.
