# Direction A, results-only power check: findings

**2026-10-09.** The criteria were committed before any result was fetched
(5741b34). Produced by `PYTHONPATH=.:src python -m v2_design.incumbent_power
analyse`, with the final numbers in `incumbent_power_results.json`. Cost:
zero (Democracy Club, no paid API). No election from 2024 onwards was
requested.

## Verdict: stop direction A (pre-registered rule)

| | value |
|---|---:|
| usable council-elections | 127 (2017→21: 14 · 2018→22: 34 · 2019→23: 79) |
| excluded | 284 not whole-council · 44 no overall control · 8 missing results |
| SD of controlling party's vote-share change | 5.37 pp |
| no-news baseline, cross-validated R² | 0.20 |
| residual σ | 4.80 pp |
| MDE80, pooled (N = 127) | 1.19 pp per SD |
| **MDE80, one round (N = 34)** | **2.31 pp per SD → "stop" (> 2.0)** |

The rule reads the one-round figure, because one round is the scale of V2's
reserved confirmatory test. Even pooling the two reserved rounds that will
exist by 2026 (2021→25 and 2022→26, roughly 48 units at these inclusion
rates) gives MDE80 ≈ 1.9 pp per SD. That is close to double the 1.0 pp effect
judged plausible for coverage alone.

## Why the verdict is safe

- **The baseline is optimistic.** It uses the same-day swing of other
  councils, which real forecasts must replace with pre-election polls. Polls
  explain less, so the true σ, and therefore the true MDE, are larger. A
  realistic check could only push further towards "stop".
- **The verdict does not depend on the data fixes.** Every run, before and
  after amendment A1, gives "stop":

| run | units | σ (pp) | CV R² | MDE80, one round |
|---|---:|---:|---:|---:|
| first run (bugs present) | 130 | 8.26 | −0.02 | 4.09 |
| + joint-label fix | 133 | 8.14 | −0.01 | 3.91 |
| + by-election fix (final) | 127 | 4.80 | 0.20 | 2.31 |

## What this means

An incumbent's council-wide vote-share change varies by about ±5 pp after
the national swing is removed. With a few dozen whole-council elections per
round, only a news effect of about 2 pp per SD of coverage could be
confirmed. Local performance coverage is very unlikely to move the vote that
much on its own, and if it did, polls and history would already absorb part
of it. **Direction A cannot deliver a confirmatory answer at the data scale
England offers.** Like the outlet pilot, this is a negative design result
obtained before money was spent on news collection.

## Engineering lessons

- Democracy Club data needs two cleaning rules before council-level use:
  normalise joint party labels, and separate same-day by-elections from
  scheduled elections.
- A baseline that explains nothing (R² ≈ 0) is a bug signal before it is a
  finding. Here it exposed both defects.
