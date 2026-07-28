# Recency Weighting Method

Phase 7, Step 6. Version `recency-weighting-v1.0-2026-07-27`.
Companion layer to - never a replacement for - the Step 5
unweighted aggregates.

## Formula

For each contributing article:

```
weight = exp(-lambda * days_before_polling)
lambda = ln(2) / half_life_days
```

`days_before_polling` is the frozen deterministic value from Phase 6
Step 9 / Phase 7 Step 2 (validated effective publication date minus
polling date). Weighted counts are `sum(weight)` over articles whose
flag is 1; weighted proportions divide by a **weighted denominator**
(the summed weights of the eligible articles for that feature
group), so a proportion stays interpretable as "share of recency-
adjusted coverage".

Weights lie strictly in (0, 1] and decrease monotonically with age
(tested). Post-polling articles cannot enter: Step 2 excludes them
and `days_before_polling > 0` is re-checked here.

## Lambda: expressed as a half-life, and never tuned on outcomes

Lambda is reported through its half-life because `0.0231` is
unreadable while "30-day half-life" is a claim that can be argued
with: an article published 30 days before the poll counts half as
much as one published on the eve.

**Primary value: half-life = 30 days (lambda = 0.023105).**
Justification, entirely outcome-free: UK local-election campaigning
concentrates in the final month - nominations close roughly 19
working days before polling and the "short campaign" is the
conventional reference period - so a 30-day half-life keeps the
final month dominant while leaving older coverage a small but
non-zero voice (weight 0.016 at 180 days) rather than deleting it.

**Pre-registered grid (all computed blind, shipped in one file):**

| half-life | lambda | weight at 7d | at 30d | at 90d | at 180d |
|---|---|---|---|---|---|
| 7 days | 0.099021 | 0.500 | 0.050 | 0.000 | 0.000 |
| 14 days | 0.049510 | 0.707 | 0.224 | 0.011 | 0.000 |
| **30 days (primary)** | **0.023105** | **0.851** | **0.500** | **0.125** | **0.016** |
| 60 days | 0.011552 | 0.922 | 0.707 | 0.354 | 0.125 |
| 90 days | 0.007702 | 0.948 | 0.794 | 0.500 | 0.250 |

The grid exists so that a later sensitivity analysis needs no
re-run and no fresh contact with the data. **Lambda was not and
must not be selected against election outcomes.** If a modelling
stage chooses among these half-lives, the choice must be made
inside training folds only, and the report must state which value
was used.

## Worked examples (primary half-life)

| article published | days before polling | weight |
|---|---|---|
| polling eve | 2 | 0.955 |
| final week | 5 | 0.891 |
| two weeks out | 11 | 0.774 |
| one month out | 30 | 0.500 |
| three months out | 90 | 0.125 |
| six months out | 177 | 0.017 |

Mean weight per individual window in the pilot corpus:
final_72_hours 0.955, 7_to_4_days 0.884, 14_to_8_days 0.776,
30_to_15_days 0.660, 90_to_31_days 0.149, 180_to_91_days 0.033.

Effect on a real statistic: across the 203 pilot groups with a
positive stance denominator, the weighted negative-stance
proportion differs from the unweighted one in 36 groups, by 0.019
on average and up to 0.36 in the largest case - i.e. weighting is
not cosmetic where coverage is spread over time, and is a no-op
where a group's articles share a publication date.

## Limitations

1. **Pilot composition amplifies the decay.** 103 of the pilot's
   article-rows sit in the 91-180 day window with a mean weight of
   0.033, so under the primary half-life the weighted aggregates
   are dominated by the 48 final-72-hour rows. This is the
   weighting working as designed, but it means pilot-scale weighted
   features rest on very few articles; the comparison becomes
   informative at full-corpus scale.
2. **Exponential decay is an assumption, not a finding.** It is
   monotone, memoryless and has one parameter - defensible as a
   default, but it cannot represent an article whose salience
   spikes later (a story that resurfaces). The frozen temporal
   layer's `persistence` and `expected_decay` fields remain
   available for a future alternative weighting; none is applied
   here.
3. **Date precision is day-level.** Publication timestamps resolve
   to dates, so all articles from the same day share a weight; no
   intra-day recency is modelled.
4. **Weighted counts are not article counts.** They are masses in
   (0, n]. `unweighted_article_count` travels beside every weighted
   count so no reader has to guess which is which.
5. **Undated articles are excluded, never imputed.** The pilot has
   none; the exclusion path is implemented, records a reason per
   article per half-life in `recency_weighting_exclusions.json`,
   and is tested on synthetic cases because the full corpus will
   contain them.
