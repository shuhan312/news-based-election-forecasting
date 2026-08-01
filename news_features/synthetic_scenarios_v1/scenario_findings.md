# Synthetic news scenarios (frozen v2 model)

**SYNTHETIC SIMULATION. These figures describe how the frozen model's predictions move when hypothetical, clearly-labelled news is injected into its inputs. They are simulations, not real-world claims, and no coefficient in the model is causal.**

## tone: same Reform story, favourable vs unfavourable (30-15d, combined)

- 10 favourable articles about `reform_uk` via the combined arm, window `30_to_15_days` (cell held 7 articles, 3 naming the party, before injection): Reform mean share moves +1.003 points, 2 seat call(s) change. Full per-party deltas in the JSON.
- 10 unfavourable articles about `reform_uk` via the combined arm, window `30_to_15_days` (cell held 7 articles, 3 naming the party, before injection): Reform mean share moves -2.003 points, 2 seat call(s) change. Full per-party deltas in the JSON.

## timing: unfavourable Reform story, a month out vs the final 72 hours

- 10 unfavourable articles about `reform_uk` via the combined arm, window `30_to_15_days` (cell held 7 articles, 3 naming the party, before injection): Reform mean share moves -2.003 points, 2 seat call(s) change. Full per-party deltas in the JSON.
- 10 unfavourable articles about `reform_uk` via the combined arm, window `final_72_hours` (cell held 4 articles, 3 naming the party, before injection): Reform mean share moves -0.815 points, 8 seat call(s) change. Full per-party deltas in the JSON.

## target: the same unfavourable story about Reform vs the Conservatives

- 10 unfavourable articles about `reform_uk` via the combined arm, window `90_to_31_days` (cell held 57 articles, 25 naming the party, before injection): Reform mean share moves -0.273 points, 0 seat call(s) change. Full per-party deltas in the JSON.
- 10 unfavourable articles about `conservative` via the combined arm, window `90_to_31_days` (cell held 57 articles, 28 naming the party, before injection): Reform mean share moves +0.015 points, 22 seat call(s) change. Full per-party deltas in the JSON.

## arm: one favourable Reform story via national vs local collection

- 10 favourable articles about `reform_uk` via the national arm, window `90_to_31_days` (cell held 45 articles, 21 naming the party, before injection): Reform mean share moves +2.120 points, 0 seat call(s) change. Full per-party deltas in the JSON.
- 10 favourable articles about `reform_uk` via the local arm, window `90_to_31_days` (cell held 12 articles, 4 naming the party, before injection): Reform mean share moves +7.352 points, 264 seat call(s) change. Full per-party deltas in the JSON.

## Reading the magnitudes

A delta is only meaningful against the cell size printed beside it: the same ten articles are a small perturbation of a well-covered window and a doubling of a thin one. The local-arm scenario in particular injects into a near-empty cell under a sensitivity-only specification, so its large response measures the fragility of thin local coverage, not the power of one story.

## Boundary

The issue axis (e.g. a crime-focused story) cannot flow through the frozen specifications: they carry volume and portrayal features only, because issue-level features never cleared the ten-cell reporting threshold. Recorded as a boundary, not approximated around.
