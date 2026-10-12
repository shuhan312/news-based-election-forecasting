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

(none)
