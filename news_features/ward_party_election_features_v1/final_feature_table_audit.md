# Ward-party-election feature table: build audit

**Feature version:** `ward_party_election_features_v1`  
**Built:** 2026-07-29  
**Stage 1 bundle unchanged during the build:** True

> ## Read this before using any figure from this table
>
> The news side rests on a **67-article pilot**. The alignment layer names its own dataset `context-cards-v1.0-pilot67-2026-07-27`, and every downstream stage - article features, context aggregation, recency weighting - was built from it.
>
> The corpus is not 67 articles. 17,248 records are on disk, 13,399 with full text, and 3,584 have passed eligibility and are waiting for extraction. They have never been through it, which is why this table carries coverage states almost everywhere and extracted content almost nowhere.
>
> The structure below is complete and checked. The contents are a pilot. Nothing here should be read as a measurement of what news does.

## What was built

- master table: **6323 rows x 24151 columns**
- observation unit: election x electoral area x party
- news feature columns carried: 225 unweighted, 216 recency-weighted
- rows by split: {'final_test_2026': 1262, 'historical_training': 3418, 'secondary_test_2026_07': 4, 'validation_2021': 1639}
- Reform UK rows 172, UKIP rows 250, kept under separate party ids throughout
- did-not-contest rows: 4710, each with an empty vote-share target rather than a zero

## Window assembly

The principal windows are assembled from the earlier six-window aggregates. Two assemblies are exact only because of how this corpus falls, so the assembly is verified against the article-level day counts on every build and refuses to proceed if it stops holding.

| window | assembled from | days that must be empty | exact |
| --- | --- | --- | :---: |
| `final_72_hours` | final_72_hours | none | yes |
| `7_to_4_days` | 7_to_4_days | none | yes |
| `14_to_8_days` | 14_to_8_days | none | yes |
| `30_to_15_days` | 30_to_15_days | none | yes |
| `90_to_31_days` | 90_to_31_days | none | yes |
| `180_to_91_days` | 180_to_91_days | none | yes |
| `information_available_at_3_days` | previous_72_hours | none | yes |
| `information_available_at_7_days` | previous_7_days | none | yes |
| `information_available_at_14_days` | previous_14_days | none | yes |
| `information_available_at_30_days` | previous_30_days | none | yes |
| `information_available_at_90_days` | previous_90_days | none | yes |
| `information_available_at_180_days` | previous_180_days | none | yes |

Articles assigned to a window: 67.

## Which feature blocks are empty

A column empty on every row means no article in that arm and window reached any row. Counted here rather than dropped silently, because an absent block and an empty one look identical once a table is written.

| block | columns | empty on every row |
| --- | ---: | ---: |
| `baseline` | 5 | 0 |
| `combined` | 2700 | 366 |
| `coverage` | 156 | 0 |
| `local` | 2712 | 2178 |
| `local_context` | 2712 | 1426 |
| `national` | 2712 | 366 |
| `national_context` | 2712 | 1426 |
| `target` | 5 | 0 |
| `weighted_local` | 2604 | 2082 |
| `weighted_local_context` | 2604 | 1346 |
| `weighted_national` | 2604 | 323 |
| `weighted_national_context` | 2604 | 1346 |

## Leakage audit

Every one of the 24151 columns carries a verdict. 24125 permitted, 5 targets, 0 excluded, 21 identifiers.

An unrecognised column is refused rather than allowed. A new column arriving from upstream stops the build instead of joining the predictor set by default.

## Validation

| check | result |
| --- | --- |
| unique row keys | 6323 of 6323 |
| duplicate row keys | 0 |
| contests split across more than one split | 0 |
| 7 May 2026 rows | 1262, 0 not held out |
| rows labelled both Reform UK and UKIP | 0 |
| did-not-contest rows with a zero target | 0 |

**All checks passed: True**

## What this layer does not do

- No model is trained. The estimator waits on the Stage 1 architecture decision, since the residual it would fit is defined against whichever baseline ships.
- No embeddings, no synthetic scenarios.
- Nothing under the Stage 1 bundle or the earlier Phase 7 outputs is opened for writing; the bundle is hashed before and after and the two are compared above.
