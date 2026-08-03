# Per-party tide-gauge changes with contest-bootstrap intervals

**EXPLORATORY, both islands. Uncertainty annex to the pre-declared per-party decomposition (register section 18); reads frozen prediction files only, refits nothing, promotes nothing.**

Resamples 2000, seed 20260728, contests resampled with replacement inside every specification; draws are paired across parties, the group mean and the Reform contrast. The 2026 point estimates were asserted against the committed decomposition results (240 cells checked). Negative change = the news model reduced that error component relative to the control.

Controls: `recalibrated` is the confirmatory comparator; `baseline` is the untouched Stage 1 prediction that findings section 2b tabulated. Group mean = unweighted party-level mean over non-Reform supported parties; contrast = Reform minus that mean, computed inside each draw.

## validation_2021

Frozen 2021 validation predictions (fit: five aggregated 2017 party rows, zero Reform rows). 18 specifications: three arms x six confirmed windows.

Per-party |bias| change versus the recalibrated control, 90-31-day window (bracketed 95% interval; * = interval excludes zero):

| arm | party | rows | d|bias| [95% CI] | d dispersion [95% CI] |
| --- | --- | ---: | --- | --- |
| combined_exploratory | conservative | 81 | +3.925 [+3.095, +4.734]* | -0.020 [-0.779, +0.767] |
| combined_exploratory | green | 36 | +4.705 [+3.747, +5.717]* | +1.268 [+0.134, +2.368]* |
| combined_exploratory | labour | 79 | +1.054 [-1.855, +3.733] | +0.306 [-0.032, +0.701] |
| combined_exploratory | liberal_democrat | 72 | +6.244 [+4.105, +6.944]* | +0.909 [+0.264, +1.524]* |
| combined_exploratory | reform_uk | 6 | -9.142 [-9.607, -8.700]* | -0.410 [-0.619, +0.000] |
| combined_exploratory | ukip | 5 | -4.713 [-5.232, -3.267]* | -0.415 [-0.614, +0.000] |
| local_sensitivity | conservative | 81 | +4.387 [+3.792, +4.963]* | +0.334 [-0.218, +0.913] |
| local_sensitivity | green | 36 | +4.359 [+3.610, +5.150]* | +0.938 [+0.097, +1.711]* |
| local_sensitivity | labour | 79 | +2.639 [+2.500, +2.804]* | +0.065 [-0.135, +0.283] |
| local_sensitivity | liberal_democrat | 72 | +1.438 [-3.345, +4.466] | +0.521 [+0.002, +0.949]* |
| local_sensitivity | reform_uk | 6 | -7.640 [-7.908, -7.432]* | -0.171 [-0.328, +0.005] |
| local_sensitivity | ukip | 5 | -5.354 [-7.126, -1.264]* | -0.377 [-0.683, +0.000] |
| national_exploratory | conservative | 81 | +5.379 [+4.547, +6.163]* | -0.224 [-0.986, +0.589] |
| national_exploratory | green | 36 | +4.790 [+3.727, +5.954]* | +1.396 [+0.153, +2.768]* |
| national_exploratory | labour | 79 | +1.666 [-1.275, +4.361] | +0.336 [-0.034, +0.710] |
| national_exploratory | liberal_democrat | 72 | +9.074 [+7.284, +9.689]* | +0.774 [+0.125, +1.301]* |
| national_exploratory | reform_uk | 6 | -9.476 [-9.856, -9.007]* | -0.320 [-0.482, -0.000] |
| national_exploratory | ukip | 5 | -4.501 [-4.899, -3.247]* | -0.337 [-0.532, +0.041] |

Reform minus non-Reform group mean, |bias| change versus recalibrated (positive = Reform's level handled worse than the fitted/legacy parties'):

| arm | window | contrast [95% CI] | share of draws with contrast > 0 |
| --- | --- | --- | ---: |
| combined_exploratory | 14_to_8_days | -12.530 [-15.899, -8.518]* | 0.0 |
| combined_exploratory | 180_to_91_days | -12.972 [-16.794, -8.052]* | 0.0 |
| combined_exploratory | 30_to_15_days | -15.141 [-18.442, -11.060]* | 0.0 |
| combined_exploratory | 7_to_4_days | +10.275 [+9.205, +11.464]* | 1.0 |
| combined_exploratory | 90_to_31_days | -11.385 [-12.287, -10.250]* | 0.0 |
| combined_exploratory | final_72_hours | +0.000 [+0.000, +0.000] | 0.0 |
| local_sensitivity | 14_to_8_days | -18.610 [-22.377, -13.713]* | 0.0 |
| local_sensitivity | 180_to_91_days | -10.615 [-11.347, -9.539]* | 0.0 |
| local_sensitivity | 30_to_15_days | -13.146 [-16.657, -8.819]* | 0.0 |
| local_sensitivity | 7_to_4_days | +10.275 [+9.185, +11.452]* | 1.0 |
| local_sensitivity | 90_to_31_days | -9.133 [-10.337, -7.936]* | 0.0 |
| local_sensitivity | final_72_hours | +0.000 [+0.000, +0.000] | 0.0 |
| national_exploratory | 14_to_8_days | -13.210 [-14.495, -10.438]* | 0.0 |
| national_exploratory | 180_to_91_days | -13.199 [-17.143, -7.892]* | 0.0 |
| national_exploratory | 30_to_15_days | -10.284 [-11.433, -8.972]* | 0.0 |
| national_exploratory | 7_to_4_days | +0.000 [+0.000, +0.000] | 0.0 |
| national_exploratory | 90_to_31_days | -12.758 [-13.648, -11.536]* | 0.0 |
| national_exploratory | final_72_hours | +0.000 [+0.000, +0.000] | 0.0 |

Census over all 108 party x specification |bias|-change intervals versus recalibrated: **24 exclude zero on the improving side, 50 on the worsening side**, 34 straddle zero.

Footnotes the tables force:

- Contrast direction census: 2 interval(s) exclude zero on the positive side (Reform's level handled worse than the group), 12 on the negative side - combined_exploratory 14_to_8_days (-12.530); combined_exploratory 180_to_91_days (-12.972); combined_exploratory 30_to_15_days (-15.141); combined_exploratory 90_to_31_days (-11.385); local_sensitivity 14_to_8_days (-18.610); local_sensitivity 180_to_91_days (-10.615); local_sensitivity 30_to_15_days (-13.146); local_sensitivity 90_to_31_days (-9.133); national_exploratory 14_to_8_days (-13.210); national_exploratory 180_to_91_days (-13.199); national_exploratory 30_to_15_days (-10.284); national_exploratory 90_to_31_days (-12.758).
- Reform's combined 90-31-day level change keeps its sign under both controls: -9.142 [-9.607, -8.700] versus recalibrated, -9.769 [-10.129, -9.454] versus baseline - not a recalibration artefact.
- Dispersion: largest point change 20.819; 26 of 108 party x specification dispersion intervals exclude zero (conservative combined_exploratory 14_to_8_days (+4.77); green combined_exploratory 180_to_91_days (+0.87); labour combined_exploratory 180_to_91_days (+0.30); conservative combined_exploratory 30_to_15_days (+6.87); conservative combined_exploratory 7_to_4_days (+1.74); liberal_democrat combined_exploratory 7_to_4_days (+1.19); green combined_exploratory 90_to_31_days (+1.27); liberal_democrat combined_exploratory 90_to_31_days (+0.91); conservative local_sensitivity 14_to_8_days (+20.82); green local_sensitivity 14_to_8_days (+2.31); labour local_sensitivity 14_to_8_days (+1.20); liberal_democrat local_sensitivity 14_to_8_days (+4.62); green local_sensitivity 180_to_91_days (+0.88); labour local_sensitivity 180_to_91_days (+0.11); conservative local_sensitivity 30_to_15_days (+13.64); labour local_sensitivity 30_to_15_days (+1.44); liberal_democrat local_sensitivity 30_to_15_days (+3.82); conservative local_sensitivity 7_to_4_days (+1.74); liberal_democrat local_sensitivity 7_to_4_days (+1.19); green local_sensitivity 90_to_31_days (+0.94); liberal_democrat local_sensitivity 90_to_31_days (+0.52); green national_exploratory 180_to_91_days (+0.86); labour national_exploratory 180_to_91_days (+0.28); liberal_democrat national_exploratory 180_to_91_days (-0.21); green national_exploratory 90_to_31_days (+1.40); liberal_democrat national_exploratory 90_to_31_days (+0.77)). A constant per-party shift cannot move dispersion at all, so every non-zero cell here measures the clip-and-renormalise step - the prediction arithmetic's only ward-dependent operation - not news content reaching geography.
- Reform's starred level improvements on this island are section 11's extrapolation artefact restated with intervals: six candidate rows, ZERO Reform fitting rows, so the adjustment is borrowed entirely from the five fitted parties' mapping. A narrow interval says the borrowed shift is stable under contest resampling within 2021; it is not evidence of a learned Reform effect.

## holdout_2026_v2

Frozen v2 blinded predictions scored at the recorded unblinding (fit: 45 election x party cells, seven of them Reform-era). 12 confirmatory specifications: two arms x six confirmed windows.

Per-party |bias| change versus the recalibrated control, 90-31-day window (bracketed 95% interval; * = interval excludes zero):

| arm | party | rows | d|bias| [95% CI] | d dispersion [95% CI] |
| --- | --- | ---: | --- | --- |
| combined_exploratory | conservative | 158 | -1.696 [-1.735, -1.641]* | +0.010 [-0.027, +0.058] |
| combined_exploratory | green | 146 | +1.051 [-0.433, +1.068] | +0.012 [-0.009, +0.034] |
| combined_exploratory | labour | 126 | -0.549 [-0.569, -0.526]* | +0.034 [+0.015, +0.061]* |
| combined_exploratory | liberal_democrat | 161 | -2.752 [-2.791, -2.715]* | +0.032 [-0.007, +0.073] |
| combined_exploratory | reform_uk | 162 | +1.836 [+1.812, +1.859]* | +0.029 [+0.005, +0.050]* |
| national_exploratory | conservative | 158 | -1.725 [-1.785, -1.651]* | +0.010 [-0.047, +0.072] |
| national_exploratory | green | 146 | +1.160 [-0.235, +1.183] | +0.021 [-0.013, +0.051] |
| national_exploratory | labour | 126 | -0.829 [-0.863, -0.790]* | +0.065 [+0.035, +0.109]* |
| national_exploratory | liberal_democrat | 161 | -2.647 [-2.704, -2.592]* | +0.056 [-0.001, +0.113] |
| national_exploratory | reform_uk | 162 | +1.767 [+1.736, +1.800]* | +0.045 [+0.010, +0.075]* |

Reform minus non-Reform group mean, |bias| change versus recalibrated (positive = Reform's level handled worse than the fitted/legacy parties'):

| arm | window | contrast [95% CI] | share of draws with contrast > 0 |
| --- | --- | --- | ---: |
| combined_exploratory | 14_to_8_days | +3.873 [+2.211, +5.466]* | 1.0 |
| combined_exploratory | 180_to_91_days | +5.388 [+4.790, +6.045]* | 1.0 |
| combined_exploratory | 30_to_15_days | +0.806 [+0.785, +0.881]* | 1.0 |
| combined_exploratory | 7_to_4_days | -0.060 [-0.071, +0.000] | 0.0295 |
| combined_exploratory | 90_to_31_days | +2.822 [+2.788, +3.188]* | 1.0 |
| combined_exploratory | final_72_hours | +4.828 [+3.822, +5.861]* | 1.0 |
| national_exploratory | 14_to_8_days | +0.032 [-0.001, +0.037] | 0.965 |
| national_exploratory | 180_to_91_days | +5.491 [+4.909, +6.123]* | 1.0 |
| national_exploratory | 30_to_15_days | +0.385 [+0.162, +0.799]* | 1.0 |
| national_exploratory | 7_to_4_days | +0.000 [+0.000, +0.000] | 0.0 |
| national_exploratory | 90_to_31_days | +2.777 [+2.734, +3.115]* | 1.0 |
| national_exploratory | final_72_hours | -0.120 [-0.143, -0.003]* | 0.017 |

Census over all 60 party x specification |bias|-change intervals versus recalibrated: **23 exclude zero on the improving side, 16 on the worsening side**, 21 straddle zero.

Footnotes the tables force:

- Contrast direction census: 8 interval(s) exclude zero on the positive side (Reform's level handled worse than the group), 1 on the negative side - national_exploratory final_72_hours (-0.120).
- Reform's combined 90-31-day level change keeps its sign under both controls: +1.836 [+1.812, +1.859] versus recalibrated, +1.820 [+1.798, +1.841] versus baseline - not a recalibration artefact.
- Dispersion: largest point change 0.336; 21 of 60 party x specification dispersion intervals exclude zero (labour combined_exploratory 14_to_8_days (+0.04); liberal_democrat combined_exploratory 14_to_8_days (+0.05); labour combined_exploratory 30_to_15_days (+0.04); liberal_democrat combined_exploratory 30_to_15_days (+0.03); reform_uk combined_exploratory 30_to_15_days (+0.02); labour combined_exploratory 7_to_4_days (-0.02); reform_uk combined_exploratory 7_to_4_days (-0.01); labour combined_exploratory 90_to_31_days (+0.03); reform_uk combined_exploratory 90_to_31_days (+0.03); labour combined_exploratory final_72_hours (-0.10); reform_uk combined_exploratory final_72_hours (-0.05); labour national_exploratory 14_to_8_days (+0.01); reform_uk national_exploratory 14_to_8_days (+0.01); reform_uk national_exploratory 180_to_91_days (+0.04); labour national_exploratory 30_to_15_days (+0.34); liberal_democrat national_exploratory 30_to_15_days (+0.21); reform_uk national_exploratory 30_to_15_days (+0.15); labour national_exploratory 90_to_31_days (+0.06); reform_uk national_exploratory 90_to_31_days (+0.04); labour national_exploratory final_72_hours (-0.04); reform_uk national_exploratory final_72_hours (-0.02)). A constant per-party shift cannot move dispersion at all, so every non-zero cell here measures the clip-and-renormalise step - the prediction arithmetic's only ward-dependent operation - not news content reaching geography.

## Reading

These are exploratory intervals over frozen predictions. A starred cell is a level shift the contest resampling cannot explain away; an unstarred cell is indistinguishable from noise at this contest count - the same standard the register applies to every other exploratory reading. Nothing here selects a window, an arm or a model.

The cross-island reading is the headline: the Reform-minus-group contrast is negative through most 2021 windows and positive through most 2026 ones, so the direction of the news layer's Reform level correction does not survive the change of island. A narrow interval is a statement about resampling noise WITHIN one election only; the instability that matters lives between islands, and no within-island interval can certify it away. This is the transfer failure Haslemere and Woking South recorded, stated a third time in resampling form.
