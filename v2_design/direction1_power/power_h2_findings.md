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
