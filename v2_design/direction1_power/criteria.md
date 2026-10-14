# Direction 1, stage 4: H2 power gate (criteria, written before the run)

**Status: fixed 2026-10-12, before the simulation was run.** Code:
`src/forecast/power_h2.py`, committed with this file. Later changes go under
Amendments.

## Question

H2 asks whether news content improves Reform cold-start predictions in 2025
beyond its no-news reference M0 (the Leave-scaled uniform swing, design
amendment A2). News features are measured per **council**, so a council's
wards share one news value, and the independent units are councils, not
wards. With the councils 2025 offers, how large an improvement could H2
detect? The design's gate: if MDE80 > 1.0 pp, H2 is not run and no money is
spent on news.

## Inputs (no 2025 result is read)

- **Error structure:** M0's errors on Reform cold-start rows in the
  2019→2023 validation round (γ fitted on training rounds only).
- **Number of test councils K:** English councils with a scheduled
  whole-council election on 1 May 2025, counted from Democracy Club's
  election metadata (the list of ballot ids, which carries no results). A
  council counts if it has at least 10 scheduled (non-by-election) ballots.

## Method: simulate a news signal of known strength

The power of H2 depends on how strongly a news feature tracks what M0 gets
wrong. That is unknown before news exists, so it is varied:

1. For each validation council c, take M0's mean error on its Reform
   cold-start rows, r_c.
2. Build a synthetic council-level news signal s_c with correlation ρ to
   r_c: s_c = ρ·z(r_c) + √(1−ρ²)·ε, where ε ~ N(0, 1).
3. M2 = M0 + β·s_c on each Reform cold-start row, with β fitted by
   leave-one-council-out regression, so no council's own error is used to
   correct it.
4. Draw K councils with replacement from the validation councils, to mimic
   a 2025-sized test. Compute ΔMAE = MAE(M0) − MAE(M2) and its 95%
   council-bootstrap CI.
5. **Power(ρ)** is the share of 400 simulations whose CI lower bound is
   above 0, for ρ ∈ {0.1, 0.2, …, 0.9}.

**MDE80** is the mean ΔMAE at the smallest ρ with power ≥ 0.80. The
simulation compares M0 with M2. H2 itself compares M1 (volume) with M2
(content), whose incremental signal can only be weaker, so this is an
**optimistic** bound on H2's power.

## Scale

- **Primary:** errors at validation scale (Reform polled about 6% in 2023).
- **Sensitivity, reported but not used for the decision:** errors scaled by
  the ratio of Reform's national poll before the two elections (2025 / 2023),
  for the larger errors expected at Reform's 2025 level.

## Decision (from the design)

| MDE80 (primary) | verdict |
|---|---|
| ≤ 1.0 pp | **run H2:** proceed to news collection (≤ US$20) |
| > 1.0 pp | **do not run H2:** report it as underpowered; no money is spent on news |

The required ρ is reported alongside. Even where MDE80 ≤ 1.0 pp, a required
ρ well above anything plausible for news is stated as a caution.

## Amendments

**A1 (2026-10-13). An implementation bug fixed; the criteria are
unchanged.** The first run counted K = 32, including nine county elections
that were postponed for local government reorganisation (Surrey, Essex,
Hampshire and others). Democracy Club keeps their ballot lists but marks
the elections cancelled. The criteria count councils that held a scheduled
election, so cancelled elections are now skipped, giving K = 23. Network
retries and caching were added after two reruns failed on dropped
connections. The verdict is "do not run H2" in both runs; the first run's
output is kept as `power_h2_results_before_A1.json`.

**A2 (2026-10-13). A method flaw, found after the verdict; corrected
simulation fixed before it is run.**

- *When:* after the A1 run returned "do not run H2" (committed in d18dad1).
  It is recorded as found after the result, not before.
- *What:* step 4 of the method resampled validation councils directly. In
  2019→2023, Reform's cold-start rows average **2.7 per council** (401 rows
  in 149 councils), so each council's mean error is mostly ward-level
  noise. In 2025, Reform stood in almost every ward of 23 councils, so a
  council holds about **60–80** rows and that noise averages out.
  Resampling 2023's thin cells therefore understates how visible a
  council-level news signal would be in 2025. The simulated test did not
  have the structure of the real test.
- *Why it is a correction, not a re-specification:* the flaw is a mismatch
  between the simulated and the real data structure, and it would be fixed
  whichever way it biased the answer. The gate, the decision rule, the
  primary scale and ρ grid are unchanged.
- *New method (`src/forecast/power_h2_structural.py`):* estimate M0's error
  components on validation Reform cold-start rows with a one-way
  random-effects decomposition: τ² between councils (the part a council
  news signal can correct) and σ² within councils (the part it cannot).
  Simulate the 2025 structure: K = 23 councils, each with n_c wards equal to
  its scheduled 2025 ballots (Democracy Club metadata; Reform assumed to
  stand in every ward), errors u_c + e_ic, a news signal with correlation ρ
  to u_c, a leave-one-council-out correction, and a council bootstrap.
  400 simulations per ρ.
- *Decision:* as before, on the primary (validation-scale) curve: run H2
  only if MDE80 ≤ 1.0 pp.
- *Reported, not used for the decision:* the 2025-scale curve (errors ×
  the REF poll ratio) and a 70%-coverage curve (Reform standing in 70% of
  wards).
- *Reporting:* both the original and the corrected result are reported. If
  the verdicts differ, the report states that the change of verdict came
  from a post-result method correction.

**A3 (2026-10-14). The council-level error is re-estimated at a large
share; the verdict changes to "run H2". Found after the ward-coverage
strand stopped, on training data only; no 2025 result has been read.**

- *What was wrong:* A2 estimated tau² from Reform's 2019→2023 cold-start
  errors and found 0. Reform then averaged 6.8% where it stood. A party on
  a few per cent everywhere cannot differ much between councils, so this
  says little about 2025, when Reform polled about 30%. A2's "2025 scale"
  sensitivity multiplied errors by the poll ratio (×4.49), which leaves a
  zero at zero, so it could not catch the problem. A2's findings called
  this "the one way this conclusion could be wrong" and said it could not
  be checked without 2025 data. That was mistaken: it can be checked on
  training data with the parties that already have large shares.
- *Check (`forecast.power_h2_scale`, `power_h2_results_A3.json`):* the same
  M0 and the same decomposition, for every party and round, each round
  predicted with the prior and γ fitted on the other two. Every party with
  a mean share of 13% or more has clear council-level error: tau 2.6–9.4
  pp, ICC 9–43%. Reform at 6.8% is the only zero.
- *Corrected input:* tau and sigma are the medians over those large-share
  party-rounds (tau 5.16, sigma 10.40 pp). The simulation, K = 23, the gate
  and the decision rule are unchanged.
- *Result:* MDE80 = 0.72 pp, reached at ρ = 0.9 (ρ = 0.8: 0.58 pp, power
  0.795; ρ = 0.7: power 0.47). **MDE80 ≤ 1.0 pp, so by the rule H2 is run.**
  At the smallest large-share tau (2.59), MDE80 = 0.24 pp, also at ρ = 0.9.
- *Caution, as the criteria require:* power reaches 80% only if the news
  signal correlates with M0's council errors at about 0.8–0.9. That is
  high for news. A non-significant H2 is the likely outcome unless local
  coverage tracks Reform's council-level over-performance closely. H2 is
  run because it is now a fair test, not because it is expected to pass.
- *Reporting:* A1, A2 and A3 verdicts are all reported; the change of
  verdict is stated as coming from a post-result correction of a method
  flaw. The H2 specification is in `direction1_design.md`, A4.
