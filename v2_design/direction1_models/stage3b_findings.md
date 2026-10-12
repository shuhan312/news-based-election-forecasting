# Direction 1, stage 3b: Reform's cold start, solved without news (findings)

**2026-10-12.** Design amendment A2. Same split as stage 3: train on
2017→2021 and 2018→2022, validate on 2019→2023. No 2025 row was loaded, and
no news was used. Cost: zero.

## The problem

Stage 3's best model over-predicted Reform: a mean of 9.9% against an actual
6.8% on 2019→2023. Reform had no local history of its own, so the model
borrowed the first-candidacy pattern of Greens, Liberal Democrats and
independents, who tend to stand where they are already strong.

## The fix: where a new party is strong, from evidence that predates it

1. **2016 EU-referendum Leave share, per council.** Reform, the Brexit Party
   and UKIP draw on the same voters. Electoral Commission results were
   resolved to all 308 councils (`direction1_data/council_leave.csv`):
   counties are summed over their districts, and councils reorganised after
   2016 use a manual district list. Spot checks: Boston 75.6% (the UK's
   highest), Lambeth 21.4%, Kent 58.4% (12 districts), Surrey 47.8% (11).
2. **Populist-right family history:** UKIP + Reform council-wide share at
   t−1.
3. **Party-specific cold-start terms**, so each party's first candidacies
   get their own correction.
4. **Leave-scaled rule:** national poll × (council Leave / 53.4)^γ. γ = 2.25,
   fitted on training rows only. Reform is markedly stronger where Leave
   was stronger.

## Result (validation, 2019→2023)

| model | MAE | cold start | Reform cold start | Reform mean prediction (actual 6.79) |
|---|---:|---:|---:|---:|
| stage 3 LightGBM | 8.06 | 7.10 | 4.47 | 9.87 |
| LightGBM + new features | 8.10 | 7.03 | 4.15 | — |
| **hybrid: LightGBM + Leave rule** | **8.07** | **6.80** | **2.84** | **7.30** |
| uniform swing | 9.42 | 9.52 | 2.75 | 5.54 |
| **Leave-scaled uniform swing** | 9.41 | 9.51 | **2.69** | **6.74** |

- **The over-prediction is gone.** The Leave rule's mean Reform prediction
  (6.74) is within 0.05 points of the truth. The hybrid, which is the H1
  model, is within 0.5 points.
- New features alone do not fix it: LightGBM still borrows from other
  parties, at 4.15. Routing Reform's cold start to the Leave rule does fix
  it.
- Other parties are unaffected: overall MAE is essentially unchanged
  (8.07 vs 8.06), and cold-start MAE improves (6.80 vs 7.10).

## Updated freeze (`selected_config.json`)

- **H1:** proportional swing vs the **hybrid LightGBM** (7 leaves, 2000
  rounds, Leave rule for Reform/UKIP cold starts). Validation gain 1.32 pp,
  council-bootstrap CI [1.03, 1.64].
- **H2 M0:** **Leave-scaled uniform swing** (Reform cold-start MAE 2.69).
  News must now beat a no-news model that already knows where Reform's
  voters are, which is the hardest fair opponent available.

## Limits, stated plainly

- **The surge is outside validation.** Reform polled about 6% in 2023 and
  26% in 2025. Validation cannot show how the Leave rule behaves at four
  times the level; γ is fitted on small-Reform years. 2025 is the first real
  test of it.
- The selected hybrid sits at a grid corner (fewest leaves, most rounds).
  The top three hybrids are within 0.03 pp, so the grid was not widened
  again, to avoid tuning further on validation noise.
- The Leave–Reform correlation at ward level is moderate (0.26 in
  validation). Leave tells where Reform is relatively stronger, not by how
  much in each ward.
