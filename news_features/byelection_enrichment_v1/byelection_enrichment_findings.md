# By-election enrichment: the quantity-quality trade-off

**EXPLORATORY by-election enrichment analysis, post-unblinding. Documents the quantity-quality trade-off when adding single-contest by-election cells to the fitting set.**

Pooled within-cell variance (sigma-squared): 96.238

## What the enrichment did

- General election cells (2017 + 2021): **11**
- By-election cells (8 events): **34**
- Total: **45**

## Reliability and detection threshold by subset

| subset | cells | mean n/cell | single-contest | reliability | r critical | true r required |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all_45_cells | 45 | 14.7 | 34 | 0.2253 | 0.2940 | 0.6193 |
| general_elections_only | 11 | 56.9 | 0 | 0.9375 | 0.6021 | 0.6218 |
| by_elections_only | 34 | 1.0 | 34 | 0.0664 | 0.3388 | 1.3150 |
| covered_all | 19 | 33.4 | 8 | 0.6233 | 0.4555 | 0.5770 |
| covered_general_elections | 11 | 56.9 | 0 | 0.9375 | 0.6021 | 0.6218 |
| covered_by_elections | 8 | 1.0 | 8 | 0.4697 | 0.7067 | 1.0312 |

## The trade-off

Adding 34 by-election cells (8 events) quadrupled the sample from 11 to 45 cells.

- Reliability dropped from **0.9375** to **0.2253** — the single-contest cells carry enormous sampling noise (within-cell variance 96 on n=1).
- The critical r fell from 0.6021 to 0.2940 — more cells lower the significance threshold.

The net effect: the true-r-required moved from **0.6218** to **0.6193**. The two forces roughly cancel. The design is underpowered but not incapable.

## Lesson

Sample enrichment that adds low-precision cells can quadruple n while dividing measurement quality by four. The critical value falls but so does the signal-to-noise ratio. In this dataset the enrichment neither helped nor hurt detectability, but it made the reliability figure misleading when quoted without the subset breakdown.
