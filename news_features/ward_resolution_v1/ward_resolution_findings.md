# Does the news layer know which ward it is looking at?

**DIAGNOSTIC. Reads feature columns only; the target and baseline families are dropped before anything is counted, so this can be run before deciding to spend reviewer time and without touching any outcome.**

Grain: 6323 party-contest rows across 343 contests and 343 electoral areas. The frozen model was fitted on 45 election-by-party cells, so this table can show a distinction that one cannot.

## The number that decides whether news can ever beat a party name

A party indicator gives a party the same value in every contest it stands in. So the only variation it can never reproduce is variation *between wards inside one election*. The rate below is the share of covered (election, party) groups whose feature takes more than one value across that election's wards.

| arm | covered group-column pairs | varying across wards | ward resolution rate |
| --- | ---: | ---: | ---: |
| combined | 3524 | 49 | 1.4% |
| coverage | 1546 | 121 | 7.8% |
| local | 107 | 0 | 0.0% |
| local_context | 322 | 0 | 0.0% |
| national | 3531 | 0 | 0.0% |
| national_context | 5329 | 0 | 0.0% |
| weighted_local | 102 | 0 | 0.0% |
| weighted_local_context | 280 | 0 | 0.0% |
| weighted_national | 3365 | 0 | 0.0% |
| weighted_national_context | 4916 | 0 | 0.0% |

## Per arm and window

Cumulative snapshots are excluded; they are supersets of these six windows and would count the same article twice.

| arm / window | live columns | covered | varying | rate | median wards per group |
| --- | ---: | ---: | ---: | ---: | ---: |
| combined/180_to_91_days | 180 | 2076 | 0 | 0.0% | 45 |
| combined/30_to_15_days | 37 | 77 | 0 | 0.0% | 81 |
| combined/7_to_4_days | 9 | 36 | 0 | 0.0% | 81 |
| combined/90_to_31_days | 129 | 816 | 49 | 6.0% | 81 |
| combined/final_72_hours | 69 | 519 | 0 | 0.0% | 36 |
| coverage/14_to_8_days | 10 | 257 | 20 | 7.8% | 6 |
| coverage/180_to_91_days | 10 | 257 | 20 | 7.8% | 6 |
| coverage/30_to_15_days | 10 | 257 | 20 | 7.8% | 6 |
| coverage/7_to_4_days | 10 | 257 | 20 | 7.8% | 6 |
| coverage/90_to_31_days | 12 | 261 | 21 | 8.1% | 7 |
| coverage/final_72_hours | 10 | 257 | 20 | 7.8% | 6 |
| local/90_to_31_days | 23 | 107 | 0 | 0.0% | 5 |
| local_context/final_72_hours | 23 | 322 | 0 | 0.0% | 43 |
| national/180_to_91_days | 181 | 2099 | 0 | 0.0% | 45 |
| national/30_to_15_days | 38 | 80 | 0 | 0.0% | 81 |
| national/7_to_4_days | 10 | 40 | 0 | 0.0% | 81 |
| national/90_to_31_days | 128 | 781 | 0 | 0.0% | 81 |
| national/final_72_hours | 70 | 531 | 0 | 0.0% | 36 |
| national_context/14_to_8_days | 20 | 780 | 0 | 0.0% | 36 |
| national_context/180_to_91_days | 54 | 3173 | 0 | 0.0% | 45 |
| national_context/90_to_31_days | 32 | 1376 | 0 | 0.0% | 81 |
| weighted_local/90_to_31_days | 22 | 102 | 0 | 0.0% | 5 |
| weighted_local_context/final_72_hours | 20 | 280 | 0 | 0.0% | 43 |
| weighted_national/180_to_91_days | 178 | 2014 | 0 | 0.0% | 45 |
| weighted_national/30_to_15_days | 36 | 74 | 0 | 0.0% | 81 |
| weighted_national/7_to_4_days | 8 | 32 | 0 | 0.0% | 81 |
| weighted_national/90_to_31_days | 123 | 735 | 0 | 0.0% | 81 |
| weighted_national/final_72_hours | 66 | 510 | 0 | 0.0% | 36 |
| weighted_national_context/14_to_8_days | 18 | 702 | 0 | 0.0% | 36 |
| weighted_national_context/180_to_91_days | 52 | 2965 | 0 | 0.0% | 45 |
| weighted_national_context/90_to_31_days | 30 | 1249 | 0 | 0.0% | 81 |

## Why the rate is zero, and the most any review could change it

A zero rate has two explanations that lead to opposite decisions. Either the ward-tier articles exist and are waiting on the human E5 review, in which case reviewer time buys the axis; or they were never collected, in which case no amount of reviewing can produce them. The coverage ledger separates the two.

Ward-tier cells: **18138**

| coverage status | cells | keyed to a named ward | keyed election-wide |
| --- | ---: | ---: | ---: |
| not_applicable | 16116 | 16092 | 24 |
| observed_news | 18 | 0 | 18 |
| pending_external_stage | 756 | 0 | 756 |
| source_unavailable | 1248 | 1248 | 0 |

Cells that carry news or could still receive it: **774**, spread over 67 (election, party) groups.

**Wards per unlockable group: {'1': 67}** - the maximum is 1.

That last line is the one that decides it. Variation across wards inside an (election, party) group is arithmetically impossible when the group carries one ward, however many articles arrive. If every unlockable cell is keyed election-wide, judging them adds election-level news and leaves the between-ward axis exactly where it is now.

Re-run this after any change to the corpus. The number to watch is ``max_wards_in_any_unlockable_group``: until it exceeds one, the between-ward comparison cannot be run at all, and the news layer has no axis available to it that a party indicator does not already cover.
