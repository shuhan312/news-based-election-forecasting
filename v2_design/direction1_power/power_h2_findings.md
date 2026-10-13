# Direction 1, stage 4: H2 power gate (findings)

**2026-10-13.** Criteria committed before the run (e531b8d); amendment A1
fixes the test-council count. Produced by `PYTHONPATH=.:src python -m
forecast.power_h2 run`, with results in `power_h2_results.json`. No 2025
result was read, and no news was collected. Cost: zero.

## Verdict: H2 is not run. It is underpowered, by the pre-registered gate.

| | value |
|---|---|
| 2025 councils that held a whole-council election (K) | 23 |
| Reform cold-start rows in validation (2019→2023) | 401, in 149 councils |
| no-news reference M0 (Leave-scaled uniform swing), validation MAE | 2.69 pp |

Power to detect a news gain, by the strength ρ of a council-level news
signal's correlation with M0's council errors (400 simulations each):

| ρ | 0.1 | 0.3 | 0.5 | 0.7 | 0.8 | **0.9** |
|---|---:|---:|---:|---:|---:|---:|
| mean gain (pp) | −0.01 | 0.02 | 0.06 | 0.16 | 0.25 | **0.39** |
| power | 3% | 8% | 8% | 21% | 29% | **53%** |

**No signal strength reaches 80% power, so MDE80 does not exist.** That
includes ρ = 0.9, a news feature almost perfectly aligned with what the
model gets wrong. At 2025 scale (errors × 4.49), power at ρ = 0.9 is 51%,
the same verdict. With K = 32 (the pre-fix count), it was 56%.

This is an optimistic bound. H2 compares content with volume, not news
with no news, so its real power is lower still.

## Why

1. **Few independent units.** News is measured per council, and 23
   councils is a small sample for a small effect.
2. **Little room left, because the no-news model is already good.** After
   stage 3b, M0's mean Reform prediction is within 0.05 points of the
   truth. Most of its remaining error lies between wards **within** a
   council (one ward 15%, the next 3%), which a council-level news signal
   cannot touch. Even a near-perfect council signal recovers under 0.4 pp.
3. **Thin cells.** Validation has fewer than 3 Reform cold-start rows per
   council on average, so council-level errors are themselves noisy.

## What this does and does not mean

- It does **not** show that news is useless.
- It **does** show that at England's scale, after a strong no-news model
  of where Reform's voters are, any council-level news effect on Reform's
  cold start is too small to confirm. A news signal close to perfect would
  be worth under 0.4 pp of MAE.
- V1's question ("does news add value beyond history and party?") now has a
  quantified answer for its most promising case. No money was spent on news
  to obtain it.

## Next

Stage 5 (news collection) is skipped. Stage 6 freezes the H1 model and runs
the single 2025 test, for H1 only. H2 is reported as underpowered, with this
file as the evidence.

---

## Amendment A2: structure-matched simulation (2026-10-13)

The first simulation resampled 2023's thin cells (2.7 Reform cold-start
rows per council). A2, found after the first verdict and committed before
being run (3657494), simulates 2025's real structure instead: 23 councils
with 21–98 wards each. Results: `power_h2_results_A2.json`.

**Verdict unchanged: H2 is not run.** The reason is now sharper:

| error decomposition of M0 on validation Reform cold starts | value |
|---|---|
| between-council variance τ² (what council-level news could fix) | **0.00** |
| within-council variance σ² (what it cannot fix) | 23.33 |
| share of error at council level (ICC) | **0%** |

With τ² = 0 there is nothing for a council-level signal to correct. Power
stays at the false-positive rate (≤ 2%) for every ρ, at validation scale,
at 2025 scale and at 70% coverage.

**How sure is the zero?** Validation cells are thin, so τ² is imprecise.
A council bootstrap puts its 95th percentile at 1.31 (τ ≈ 1.1 pp). At that
optimistic upper bound, a near-perfect signal (ρ = 0.9) reaches 70% power
for a mean gain of **0.08 pp**. That is still below 80% power, and an
effect far too small to matter. The verdict holds even at the edge of
what the data allow.

**Why the council component is so small:** even plain uniform swing
(without the Leave rule) shows τ² = 0 on 2019→2023 Reform cold starts.
Once the national level is set, Reform's local results varied ward by ward
(candidate, campaign, local issues), not council by council. A council-wide
news measure is the wrong resolution for that variation. Any news effect
would have to work at **ward** level, for example candidate-specific events
such as councillors defecting to Reform.

**Caveat:** this decomposition comes from a year when Reform polled about
6%. At its 2025 level, council-level differences may be larger than 2023
can show. That is the one way this conclusion could be wrong, and it cannot
be checked without 2025 data.
