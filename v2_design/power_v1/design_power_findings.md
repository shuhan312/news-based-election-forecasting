# V2 design power: how much data does the content question need?

**EXPLORATORY V2 design input, 2026-10-07.** Produced by
`PYTHONPATH=src python -m v2_design.design_power` →
`design_power_results.json`. Reads only pre-2026 Stage 1 out-of-fold rows
(10 fitting elections, 45 election-party cells, 660 candidates) and the
frozen feature table. No 2026 outcome and no new-county data is read.

## Question

V2's primary estimand is `delta_content = MAE(M2) − MAE(M3)`: what coverage
tone adds once party identity (M1) and coverage volume (M2) are already in the
model. How many independent units must V2 evaluate on before an effect of a
given size is detectable (two-sided 5%, 80% power)?

## Why the V1 MDE annex cannot answer it

`minimal_detectable_effect_v1` resamples the 81 holdout contests with the
fitted model held fixed. It sees test-set noise only. A party-level news
effect is one adjustment per election × party, so the dominant variance is
*which election you test on*, plus training noise from 45 cells. Neither is
in that annex. Its 0.22pp median MDE80 is therefore optimistic for this
estimand.

## Method

Run V2's own evaluation design on V1 fitting data: leave one election out,
refit M0–M3 (ridge, frozen penalty) on the other nine, score the held-out
election's candidates. The between-election spread of `delta_content` is then
projected forward on two bases: the SD of per-cell deltas with a design effect
for within-election correlation, and the election-cluster bootstrap SE scaled
by 1/√elections.

## Results, headline window (90–31 days)

Leave-one-election-out ladder (positive = the added block helps; 95% CI from
an election-cluster bootstrap):

| step | ΔMAE | 95% CI |
|---|---:|---|
| M1 party vs M0 intercept | −0.334 | [−1.61, +1.23] |
| M2 + volume vs M1 | −0.125 | [−0.18, −0.08] |
| **M3 + tone vs M2 (primary)** | **−0.541** | [−0.79, −0.09] |
| M3b + incumbent-judgement frame vs M2 | +0.305 | [−0.06, +0.55] |

Whole-council elections needed for MDE80 = target:

| target MDE80 (pp) | cluster-SE basis | cell-SD basis |
|---:|---:|---:|
| 0.05 | 233 | 2127 |
| 0.10 | 59 | 532 |
| 0.20 | 15 | 133 |
| 0.30 | 7 | 60 |

## Reading

1. **Surrey alone cannot answer the question, at any plausible effect size.**
   Surrey holds one whole-council election every four years. Even the
   optimistic basis needs ~15 whole-council elections to resolve 0.2pp.
   Expanding to multiple councils is a precondition for V2, not an
   enhancement.
2. **0.1pp is out of reach. V2 should pre-register a smallest effect of
   interest around 0.2–0.3pp** and size the data for it: roughly 15–130
   whole-council elections for 0.2pp, or 7–60 for 0.3pp. The two bases
   disagree by close to an order of magnitude because only ~2.2 effective
   election clusters exist (2017 and 2021 dominate the candidate weighting).
   The range is the honest statement.
3. **Party indicators do not transfer between pre-2026 elections** (M1 vs M0
   −0.33, CI spanning ±1.4). V1's +0.834 party-indicator gain on 2026 is
   therefore probably specific to 2026. Fixing Stage 1 with static party
   dummies would repeat the shortcut. A time-varying party signal (pre-election
   national polling or swing) is the candidate fix.
4. **Tone hurts out of sample here (−0.54, CI excludes 0); the
   incumbent-judgement frame leans positive (+0.31, CI touches 0).** This is
   a hypothesis for V2's richer content representations to pre-register. It
   is not a finding: it comes from ten folds, and this frame was chosen in V1
   for its raw association.
5. **Window choice dominates variance.** The same projection ranges from 1 to
   3000+ elections across the six windows (7–4 days and final 72 hours are
   unstable because tone is fitted on very few covered cells). V2 should fix
   one primary window in advance (90–31 days) and treat the others as
   exploratory, which also answers the examiner's multiplicity point.

## Caveats

- Ten folds, ~2.2 effective clusters: every SD here is itself very uncertain.
  The projections are orders of magnitude, not targets.
- Predictions are not clipped and renormalised per contest. All arms share
  this omission.
- Leave-one-out ignores chronology. That is acceptable for a variance
  estimate under exchangeability. V2's confirmatory evaluation forward-chains.
- Future councils' cell sizes and party systems differ from Surrey's. Re-run
  this projection on the first expanded councils before committing to the
  full collection.
