# Winning-margin derivation policy

## Purpose

The project supervisor requires a winning-margin field. The audited Surrey
official result pages provide candidates, vote totals and explicit outcomes,
but do not publish a dedicated winning-margin field in the extracted result
tables. This policy therefore creates a **separate derived metadata value**
only where a single, reproducible official-page calculation is possible.

The official `winning_margin` field remains `NULL` unless an official page
publishes that field directly. Derived metadata never overwrites it. A separate
`analysis_winning_margin` may additionally use already audited statutory Seats
evidence, with that supplementary provenance kept explicit. Its governed
definition is the **last-seat winning margin**: the lowest vote total among
officially elected candidates minus the highest officially non-elected total.
For one seat this is the ordinary winner/runner-up margin; for multiple seats
it is the cutoff gap for the final available seat.

## Eligibility rule

One result page can produce `derived_winning_margin` only when all of these
conditions hold on that **same official page**:

1. `Seats` is explicitly published as exactly `1`.
2. Exactly one candidate is explicitly marked `Elected`.
3. Every listed candidate has an official vote total and an outcome of exactly
   `Elected` or `Not elected`.
4. The elected candidate's official vote total is at least the highest total
   of the officially non-elected candidates.
5. The page has not published an official margin already.

The formula is:

`officially elected candidate votes − highest officially non-elected candidate votes`

The explicit outcome identifies the winner. Vote order is never used to choose
the winner. It only identifies the highest officially non-elected comparison
candidate after the official outcome has been checked.

## Exclusions

- Two-seat 2026 wards use the explicitly documented final-seat cutoff margin;
  this is not presented as the first-placed candidate's lead.
- The 28 Surrey 2021 divisions whose result pages omit `Seats` remain excluded
  from the same-page `derived_winning_margin`. They do receive a separate
  `analysis_winning_margin` because audited statutory evidence establishes
  that each contest had one seat; the calculation still uses only candidate
  outcomes and votes from the exact official result page.
- Missing votes, missing/other outcomes, or an outcome-vote contradiction
  prevent calculation.

## Current audited coverage

The current dataset creates 230 same-page derived-margin records: 81 for 2013,
81 for 2017, 53 for 2021 and 15 County Council by-elections. The analysis layer
adds the remaining 28 single-seat 2021 divisions using audited statutory Seats
evidence. It also applies the same last-seat formula to all 81 two-member 2026
wards. All 339 areas therefore have an analysis margin; the 2026 values mean
the final-seat cutoff gap, not the leading candidate's margin over second place.

This preserves the project's evidence layers: official source data, cited
supplementary evidence, transparent derived values, and genuinely missing
official values remain distinguishable.

## Related official guidance

The Electoral Commission's guidance describes declaration of candidates,
votes, elected candidate(s) and rejected ballot papers by the Returning
Officer. It does not establish a published winning-margin field; the project
therefore records the formula and its source page separately.

- [Declaration of the result](https://www.electoralcommission.org.uk/guidance-candidates-and-agents-local-authority-mayoral-elections-england/verification-and-count/declaration-result)
- [Guidance for Returning Officers](https://www.electoralcommission.org.uk/full-guidance/guidance-returning-officers-administering-local-government-elections-england)
