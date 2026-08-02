# The local arm, re-run on the v3 lineage

**EXPLORATORY local re-run on the v3 lineage. The 2026 outcomes were unblinded before any v3 judgement existed; nothing here joins the confirmatory verdict.**

Frozen specification (local_party_article_share + local_net_portrayal_share), the same 45 fitting cells as the v2 freeze, frozen prediction and scoring code throughout; only the feature table is v3. Test-side 2026 local inputs are unchanged - this asks whether a better-trained local model transfers.

| window | local v3 delta | 95% CI | local v2 (sens) | combined (conf) | national (conf) | seat acc |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| 180_to_91_days | +0.325 | [+0.250, +0.403] | +0.289 | -0.575 | -0.590 | 0.7188 |
| 90_to_31_days | +0.267 | [+0.084, +0.432] | +0.188 | +0.240 | +0.268 | 0.8101 |
| 30_to_15_days | -0.659 | [-0.814, -0.503] | -0.561 | +0.134 | -0.016 | 0.7115 |
| 14_to_8_days | +0.015 | [-0.063, +0.094] | +0.018 | -0.325 | +0.005 | 0.7188 |
| 7_to_4_days | -0.010 | [-0.018, -0.002] | -0.010 | -0.010 | +0.000 | 0.7188 |
| final_72_hours | +0.259 | [+0.084, +0.417] | -0.833 | +0.188 | -0.023 | 0.8173 |

Local v3 beats its recalibrated control in **4 of 6** windows (v2-fit sensitivity: 3 of 6; the confirmatory arms: combined and national each 3 of 6 among these windows).
