# Direction A, results-only power check: criteria (written before any result is read)

**Status: fixed 2026-10-08, before any vote count was fetched.** Code:
`src/v2_design/incumbent_power.py`, committed together with this file.
Later changes go under Amendments, with their reasons.

## Question

Direction A (`v2_design/design_decision_v1.md`) tests whether local coverage
of council performance predicts the **controlling party's** vote-share change,
beyond history and the national swing. Before any news is collected: with the
council-elections available, how large would that effect have to be to be
detectable at 80% power? If only an implausibly large effect would be
detectable, direction A stops here at zero cost.

## Units and data

- **Unit:** one council, one pair of consecutive whole-council elections
  (t−1 → t).
- **Rounds used:** 2017 → 2021 (county and unitary), 2018 → 2022 (London
  boroughs and others), 2019 → 2023 (districts and unitaries). Source:
  Democracy Club (EveryElection for the election list, the candidates API
  for results).
- **Reserved, never fetched:** every election from 2024 onwards. The rounds
  2021 → 2025, 2022 → 2026 and 2023 → 2027 stay untouched for V2's
  confirmatory evaluation.
- **Whole-council elections only:** control is derived from the t−1 election,
  so t−1 must elect the whole council. An election is treated as whole-council
  if the council is a county (CTY) or London borough (LBO), or if at least 30%
  of its ballots elect more than one member. That rule excludes councils
  elected by thirds. It also excludes some whole-council councils with only
  single-member wards, which costs sample size, not validity.
- **Controlling party:** the party winning more than half the seats at t−1.
  Councils with no overall control are excluded and counted.
- **Vote share:** per ballot, each party's best-placed candidate's votes,
  summed over the council's contested ballots, divided by the same sum over
  all parties. This is the standard top-candidate method for multi-member
  wards. Uncontested ballots contribute nothing.

## Outcome and baseline

- **Outcome y:** controlling party's council-wide vote share at t minus at
  t−1, in percentage points.
- **Baseline (no news), fitted with leave-one-council-out cross-validation:**
  1. *national swing*: the mean share change of the same party, in the same
     round, across all **other** councils;
  2. the controlling party's share at t−1 (regression to the mean).
- **Residual spread σ:** SD of the cross-validated baseline residuals.

The same-round swing of other councils is an **optimistic** baseline. It uses
results that a real forecast would replace with pre-election polls, so it
explains more than polls would and leaves a smaller σ. The resulting MDE is
therefore a **lower bound**. That makes a "stop" verdict safe: if even the
optimistic MDE is implausible, polls would only make it worse. A "proceed"
verdict must later be re-checked with polling.

## Power

For a standardised news feature (1 SD), MDE80 = (1.960 + 0.842) · σ / √N,
where N is the number of usable units. The figure is reported for all rounds
pooled, and for the size of one round (the scale of V2's reserved
confirmatory test).

## Decision

The smallest effect worth detecting is set at **1.0 pp of incumbent vote
share per SD of the news feature**. This is a judgement: local-performance
effects in the literature are small, and anything much larger would be
implausible for coverage alone.

| MDE80 per SD (one round) | verdict |
|---|---|
| ≤ 1.0 pp | **proceed:** build the attribution and performance-tone pipeline |
| 1.0 – 2.0 pp | **proceed with pooling only:** V2 must pool several rounds, and the confirmatory test is redesigned around that |
| > 2.0 pp | **stop direction A** before any news is collected |

## Reported, not graded

N per round, the number of councils excluded (no overall control, not
whole-council, missing results), σ, and the baseline's cross-validated R².

## Amendments

(none)
