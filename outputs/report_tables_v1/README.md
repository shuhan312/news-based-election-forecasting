# Report table pack v1

Every table is read from committed artefacts; `manifest.json` holds the sha256 of each input. Confirmatory numbers are the register's; everything exploratory is labelled by its source section.

**Two baselines appear and differ by design**: 4.514 is the untouched baseline over all 832 candidate rows (t01); 4.441 is the same baseline over the supported-party rows every news comparison is scored on (t04/t05). Use 4.441 when comparing against news models, 4.514 when describing the baseline alone - mixing them misstates the deltas.

## Untouched baseline on the 2026 principal election

*Source: unblinding_results.json + holdout_predictions.csv (register section 16 and its annex)*

| metric | value | n |
| --- | --- | --- |
| overall MAE (share points) | 4.514 | 832 |
| seat-call accuracy | 0.7188 | 832 |
| wards with both seats exactly right | 18 | 81 |
| deciding-margin MAE (share points) | 4.31 | 81 |
| Reform UK MAE (share points) | 3.232 | 162 |
| Reform UK seat-call accuracy (all-lose call) | 0.9136 | 162 |
| Reform UK mean predicted share (%) | 9.3 | 162 |
| Reform UK mean observed share (%) | 10.7 | 162 |
| Reform UK predicted top-two contests | 0 | 162 |
| Reform UK observed top-two contests | 14 | 162 |

## Baseline per-party MAE, 2026 principal election

*Source: holdout_predictions.csv (register annex)*

| party | candidates | baseline_mae |
| --- | --- | --- |
| Reform UK | 162 | 3.23 |
| Liberal Democrats | 161 | 7.54 |
| Conservative | 158 | 4.74 |
| The Green Party | 146 | 2.55 |
| Labour | 113 | 3.64 |
| Independent | 31 | 4.56 |
| Labour and Co-operative | 13 | 5.62 |
| Residents Associations of Epsom and Ewell | 10 | 5.54 |
| Farnham Residents | 6 | 3.89 |
| Local Conservatives | 4 | 8.99 |
| Heritage Party | 4 | 7.76 |
| Trade Unionist and Socialist Coalition | 3 | 5.15 |
| Ashtead Independent, working with Ashtead Residents | 2 | 6.61 |
| Social Democratic Party | 2 | 8.48 |
| Hinchley Wood Residents - Weston, Long Ditton | 2 | 2.33 |
| Nork and Tattenhams Residents' Associations | 2 | 10.64 |
| The Molesey Residents Association | 2 | 1.98 |
| The Walton Society | 2 | 8.98 |
| Runnymede Independent Residents' Group | 2 | 1.0 |
| Residents for Guildford and Villages | 2 | 2.27 |
| Independent Network | 1 | 2.49 |
| Thames Ditton Residents' Association | 1 | 2.33 |
| Weybridge Independents | 1 | 6.49 |
| The Peace Party - Non-violence, Justice, Environment | 1 | 7.97 |
| Official Monster Raving Loony Party | 1 | 4.95 |

## Baseline seat totals, predicted vs actual (162 seats)

*Source: holdout_predictions.csv (register annex; figure 2)*

| party | predicted_seats | actual_seats |
| --- | --- | --- |
| Liberal Democrats | 6 | 96 |
| Conservative | 118 | 30 |
| Reform UK | 0 | 14 |
| The Green Party | 0 | 8 |
| Independent | 0 | 3 |
| Ashtead Independent, working with Ashtead Residents | 2 | 2 |
| Farnham Residents | 6 | 2 |
| Nork and Tattenhams Residents' Associations | 2 | 2 |
| Residents Associations of Epsom and Ewell | 10 | 2 |
| Residents for Guildford and Villages | 2 | 1 |
| Runnymede Independent Residents' Group | 2 | 1 |
| The Molesey Residents Association | 2 | 1 |
| Hinchley Wood Residents - Weston, Long Ditton | 2 | 0 |
| Labour | 2 | 0 |
| Local Conservatives | 4 | 0 |
| Thames Ditton Residents' Association | 1 | 0 |
| The Walton Society | 2 | 0 |
| Weybridge Independents | 1 | 0 |

## Confirmatory comparisons, v1 (before enrichment): 0 of 12 improve

*Source: unblinding_results.json (register section 16)*

| arm | window | baseline_mae | recalibrated_mae | news_mae | news_vs_recalibrated | ci_lower | ci_upper | reform_news_mae | reform_vs_recalibrated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combined | 180-91 days | 4.441 | 4.441 | 4.753 | -0.311 | -0.485 | -0.144 | 3.928 | -0.446 |
| combined | 90-31 days | 4.441 | 4.441 | 4.84 | -0.399 | -0.59 | -0.218 | 3.975 | -0.494 |
| combined | 30-15 days | 4.441 | 4.441 | 5.357 | -0.915 | -1.203 | -0.638 | 4.754 | -1.272 |
| combined | 14-8 days | 4.441 | 4.441 | 4.978 | -0.536 | -0.779 | -0.27 | 4.988 | -1.507 |
| combined | 7-4 days | 4.441 | 4.441 | 6.635 | -2.194 | -2.487 | -1.896 | 5.665 | -2.184 |
| combined | final 72h | 4.441 | 4.441 | 4.956 | -0.515 | -1.137 | 0.092 | 6.565 | -3.084 |
| national | 180-91 days | 4.441 | 4.441 | 4.735 | -0.294 | -0.477 | -0.126 | 4.026 | -0.545 |
| national | 90-31 days | 4.441 | 4.441 | 4.87 | -0.429 | -0.642 | -0.23 | 4.205 | -0.724 |
| national | 30-15 days | 4.441 | 4.441 | 5.576 | -1.135 | -1.625 | -0.669 | 5.086 | -1.605 |
| national | 14-8 days | 4.441 | 4.441 | 7.04 | -2.598 | -2.909 | -2.284 | 6.202 | -2.721 |
| national | 7-4 days | 4.441 | 4.441 | 4.441 | 0.0 | 0.0 | 0.0 | 3.481 | 0.0 |
| national | final 72h | 4.441 | 4.441 | 4.459 | -0.018 | -0.031 | -0.003 | 3.516 | -0.034 |

## Confirmatory comparisons, v2 (after enrichment): 5 of 12 improve, 4 intervals above zero

*Source: unblinding_results.json (register section 16)*

| arm | window | baseline_mae | recalibrated_mae | news_mae | news_vs_recalibrated | ci_lower | ci_upper | reform_news_mae | reform_vs_recalibrated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combined | 180-91 days | 4.441 | 4.445 | 5.021 | -0.575 | -0.934 | -0.245 | 6.027 | -2.805 |
| combined | 90-31 days | 4.441 | 4.445 | 4.205 | 0.24 | 0.078 | 0.387 | 3.91 | -0.688 |
| combined | 30-15 days | 4.441 | 4.445 | 4.312 | 0.134 | 0.095 | 0.169 | 3.37 | -0.148 |
| combined | 14-8 days | 4.441 | 4.445 | 4.771 | -0.325 | -0.569 | -0.058 | 5.495 | -2.273 |
| combined | 7-4 days | 4.441 | 4.445 | 4.455 | -0.01 | -0.018 | -0.002 | 3.202 | 0.02 |
| combined | final 72h | 4.441 | 4.445 | 4.257 | 0.188 | -0.23 | 0.584 | 4.944 | -1.721 |
| national | 180-91 days | 4.441 | 4.445 | 5.035 | -0.59 | -0.947 | -0.263 | 6.104 | -2.882 |
| national | 90-31 days | 4.441 | 4.445 | 4.177 | 0.268 | 0.109 | 0.411 | 3.887 | -0.665 |
| national | 30-15 days | 4.441 | 4.445 | 4.461 | -0.016 | -0.124 | 0.099 | 3.574 | -0.352 |
| national | 14-8 days | 4.441 | 4.445 | 4.441 | 0.005 | 0.001 | 0.009 | 3.233 | -0.011 |
| national | 7-4 days | 4.441 | 4.445 | 4.445 | 0.0 | 0.0 | 0.0 | 3.222 | 0.0 |
| national | final 72h | 4.441 | 4.445 | 4.469 | -0.023 | -0.039 | -0.008 | 3.186 | 0.036 |

## Sensitivity families (non-promotable), summarised

*Source: unblinding_results.json (register section 16)*

| version | specification_group | comparisons | improved | best_delta | worst_delta |
| --- | --- | --- | --- | --- | --- |
| v1 | combined_exploratory | 18 | 3 | 0.639 | -4.66 |
| v1 | local_sensitivity | 24 | 1 | 0.32 | -4.66 |
| v1 | national_exploratory | 18 | 0 | 0.0 | -6.27 |
| v2 | combined_exploratory | 6 | 5 | 0.61 | -0.391 |
| v2 | local_sensitivity | 12 | 8 | 0.508 | -0.833 |
| v2 | national_exploratory | 6 | 1 | 0.081 | -1.739 |

## Seat-call accuracy per specification (secondary outcome)

*Source: unblinding_results.json (register section 16 addendum)*

| version | arm | window | news_seat_accuracy | baseline_seat_accuracy |
| --- | --- | --- | --- | --- |
| v1 | combined | 180-91 days | 0.7308 | 0.7188 |
| v1 | combined | 90-31 days | 0.7404 | 0.7188 |
| v1 | combined | 30-15 days | 0.8077 | 0.7188 |
| v1 | combined | 14-8 days | 0.6827 | 0.7188 |
| v1 | combined | 7-4 days | 0.7188 | 0.7188 |
| v1 | combined | final 72h | 0.8413 | 0.7188 |
| v1 | national | 180-91 days | 0.7356 | 0.7188 |
| v1 | national | 90-31 days | 0.7548 | 0.7188 |
| v1 | national | 30-15 days | 0.8413 | 0.7188 |
| v1 | national | 14-8 days | 0.7188 | 0.7188 |
| v1 | national | 7-4 days | 0.7212 | 0.7188 |
| v1 | national | final 72h | 0.7212 | 0.7188 |
| v2 | combined | 180-91 days | 0.8317 | 0.7188 |
| v2 | combined | 90-31 days | 0.7909 | 0.7188 |
| v2 | combined | 30-15 days | 0.7212 | 0.7188 |
| v2 | combined | 14-8 days | 0.6827 | 0.7188 |
| v2 | combined | 7-4 days | 0.7188 | 0.7188 |
| v2 | combined | final 72h | 0.8558 | 0.7188 |
| v2 | national | 180-91 days | 0.8317 | 0.7188 |
| v2 | national | 90-31 days | 0.7909 | 0.7188 |
| v2 | national | 30-15 days | 0.7212 | 0.7188 |
| v2 | national | 14-8 days | 0.7188 | 0.7188 |
| v2 | national | 7-4 days | 0.7188 | 0.7188 |
| v2 | national | final 72h | 0.7188 | 0.7188 |

## Reform seat calls per v2 specification (actual: 14 of 162 won)

*Source: blinded_predictions.csv v2 + observed outcomes (register Reform seat-call addendum)*

| arm | window | predicted_seats | hits_of_14 | row_accuracy |
| --- | --- | --- | --- | --- |
| baseline | - | 0 | 0 | 0.9136 |
| combined | 180-91 days | 0 | 0 | 0.9136 |
| combined | 90-31 days | 0 | 0 | 0.9136 |
| combined | 30-15 days | 0 | 0 | 0.9136 |
| combined | 14-8 days | 105 | 8 | 0.3642 |
| combined | 7-4 days | 0 | 0 | 0.9136 |
| combined | final 72h | 0 | 0 | 0.9136 |
| national | 180-91 days | 0 | 0 | 0.9136 |
| national | 90-31 days | 0 | 0 | 0.9136 |
| national | 30-15 days | 0 | 0 | 0.9136 |
| national | 14-8 days | 0 | 0 | 0.9136 |
| national | 7-4 days | 0 | 0 | 0.9136 |
| national | final 72h | 0 | 0 | 0.9136 |

## Attribution: v2 deltas with vs without the 7 Reform cells (3 improvements survive, 2 collapse)

*Source: decomposition_results.json (register section 18)*

| arm | window | full_fit_delta | no_reform_delta | verdict |
| --- | --- | --- | --- | --- |
| combined | 180-91 days | -0.5751 | -1.2684 | no full-fit improvement to attribute |
| combined | 90-31 days | 0.2404 | 0.0773 | improvement survives without Reform cells |
| combined | 30-15 days | 0.1339 | 0.0333 | improvement survives without Reform cells |
| combined | 14-8 days | -0.3252 | -0.8817 | no full-fit improvement to attribute |
| combined | 7-4 days | -0.0097 | -0.001 | no full-fit improvement to attribute |
| combined | final 72h | 0.1882 | -1.1328 | improvement collapses without Reform cells |
| national | 180-91 days | -0.5896 | -1.2782 | no full-fit improvement to attribute |
| national | 90-31 days | 0.2682 | -0.0015 | improvement collapses without Reform cells |
| national | 30-15 days | -0.0156 | -2.6482 | no full-fit improvement to attribute |
| national | 14-8 days | 0.0048 | 0.0029 | improvement survives without Reform cells |
| national | 7-4 days | 0.0 | 0.0 | no full-fit improvement to attribute |
| national | final 72h | -0.0231 | -0.005 | no full-fit improvement to attribute |

## Mechanism (pooled): dispersion falls exactly in the improving windows

*Source: decomposition_results.json (register section 18)*

| arm | window | baseline_dispersion | news_dispersion | dispersion_change |
| --- | --- | --- | --- | --- |
| combined | 180-91 days | 4.4861 | 5.046 | 0.5599 |
| combined | 90-31 days | 4.4861 | 4.258 | -0.2281 |
| combined | 30-15 days | 4.4861 | 4.3613 | -0.1248 |
| combined | 14-8 days | 4.4861 | 4.8245 | 0.3384 |
| combined | 7-4 days | 4.4861 | 4.4984 | 0.0123 |
| combined | final 72h | 4.4861 | 4.271 | -0.2151 |
| national | 180-91 days | 4.4861 | 5.0609 | 0.5748 |
| national | 90-31 days | 4.4861 | 4.2386 | -0.2475 |
| national | 30-15 days | 4.4861 | 4.5276 | 0.0415 |
| national | 14-8 days | 4.4861 | 4.4858 | -0.0003 |
| national | 7-4 days | 4.4861 | 4.49 | 0.0039 |
| national | final 72h | 4.4861 | 4.5072 | 0.0211 |

## Per-party mechanism, Reform UK: news moves the level the wrong way; dispersion never moves

*Source: decomposition_results.json (register section 18)*

| arm | window | baseline_signed_bias | news_signed_bias | baseline_dispersion | news_dispersion |
| --- | --- | --- | --- | --- | --- |
| combined | 180-91 days | -1.3445 | -5.9616 | 3.1725 | 3.2089 |
| combined | 90-31 days | -1.3445 | -3.1645 | 3.1725 | 3.1962 |
| combined | 30-15 days | -1.3445 | -1.8221 | 3.1725 | 3.189 |
| combined | 14-8 days | -1.3445 | 5.1555 | 3.1725 | 3.1519 |
| combined | 7-4 days | -1.3445 | -1.2962 | 3.1725 | 3.1582 |
| combined | final 72h | -1.3445 | -4.7545 | 3.1725 | 3.1211 |
| national | 180-91 days | -1.3445 | -6.0444 | 3.1725 | 3.2107 |
| national | 90-31 days | -1.3445 | -3.0955 | 3.1725 | 3.2121 |
| national | 30-15 days | -1.3445 | -1.9614 | 3.1725 | 3.3218 |
| national | 14-8 days | -1.3445 | -1.3459 | 3.1725 | 3.1729 |
| national | 7-4 days | -1.3445 | -1.3288 | 3.1725 | 3.1675 |
| national | final 72h | -1.3445 | -1.2632 | 3.1725 | 3.1491 |

## Per-party mechanism at 90-31 days: every level moves, no dispersion does

*Source: decomposition_results.json (register section 18)*

| party | combined_abs_bias_change | combined_dispersion_change | national_abs_bias_change | national_dispersion_change |
| --- | --- | --- | --- | --- |
| conservative | -1.7392 | 0.013 | -1.7677 | 0.0134 |
| green | 1.1029 | 0.0094 | 1.2117 | 0.018 |
| labour | -0.5009 | 0.024 | -0.7812 | 0.0549 |
| liberal_democrat | -2.7559 | 0.0262 | -2.6506 | 0.0502 |
| reform_uk | 1.82 | 0.0237 | 1.751 | 0.0396 |

## Residual (A) vs joint stacked (B): A lower in 16 of 18

*Source: approach_comparison.json (register section 18)*

| specification_group | window | residual_A_mae | joint_B_mae | baseline_only_mae | lower |
| --- | --- | --- | --- | --- | --- |
| combined_exploratory | 180-91 days | 7.4223 | 7.3914 | 7.7719 | B |
| combined_exploratory | 90-31 days | 8.1127 | 8.2551 | 7.7719 | A |
| combined_exploratory | 30-15 days | 8.1581 | 8.3169 | 7.7719 | A |
| combined_exploratory | 14-8 days | 7.6787 | 7.8751 | 7.7719 | A |
| combined_exploratory | 7-4 days | 8.5199 | 8.7353 | 7.7719 | A |
| combined_exploratory | final 72h | 9.1019 | 9.239 | 7.7719 | A |
| national_exploratory | 180-91 days | 7.4164 | 7.3817 | 7.7719 | B |
| national_exploratory | 90-31 days | 8.1149 | 8.2571 | 7.7719 | A |
| national_exploratory | 30-15 days | 8.1723 | 8.3447 | 7.7719 | A |
| national_exploratory | 14-8 days | 7.653 | 7.8191 | 7.7719 | A |
| national_exploratory | 7-4 days | 7.8066 | 8.0294 | 7.7719 | A |
| national_exploratory | final 72h | 8.8848 | 9.0187 | 7.7719 | A |
| local_sensitivity | 180-91 days | 7.5983 | 7.8202 | 7.7719 | A |
| local_sensitivity | 90-31 days | 8.0357 | 8.3003 | 7.7719 | A |
| local_sensitivity | 30-15 days | 7.7666 | 8.0001 | 7.7719 | A |
| local_sensitivity | 14-8 days | 8.1676 | 8.417 | 7.7719 | A |
| local_sensitivity | 7-4 days | 8.5199 | 8.7353 | 7.7719 | A |
| local_sensitivity | final 72h | 7.8128 | 8.0189 | 7.7719 | A |

## Haslemere probe: frozen v2 specifications on the 7 July contest (3 of 12 beat control; window pattern replicates)

*Source: probe_result.json (register Haslemere addenda)*

| arm | window | news_mae | recalibrated_mae | baseline_mae | news_reform_signed_error | winner_correct |
| --- | --- | --- | --- | --- | --- | --- |
| combined | 180-91 days | 8.4175 | 4.4911 | 4.4738 | 8.812 | True |
| combined | 90-31 days | 4.2899 | 4.4911 | 4.4738 | 8.58 | True |
| combined | 30-15 days | 4.5959 | 4.4911 | 4.4738 | 9.192 | True |
| combined | 14-8 days | 4.4373 | 4.4911 | 4.4738 | 8.875 | True |
| combined | 7-4 days | 4.5273 | 4.4911 | 4.4738 | 9.055 | True |
| combined | final 72h | 4.5639 | 4.4911 | 4.4738 | 9.128 | True |
| national | 180-91 days | 4.5574 | 4.4911 | 4.4738 | 9.115 | True |
| national | 90-31 days | 4.5801 | 4.4911 | 4.4738 | 9.16 | True |
| national | 30-15 days | 4.6029 | 4.4911 | 4.4738 | 9.206 | True |
| national | 14-8 days | 4.4724 | 4.4911 | 4.4738 | 8.945 | True |
| national | 7-4 days | 4.4911 | 4.4911 | 4.4738 | 8.982 | True |
| national | final 72h | 4.565 | 4.4911 | 4.4738 | 9.13 | True |

## Haslemere probe: baseline references and corpus facts

*Source: probe_result.json + Stage 1 metrics.json*

| item | value |
| --- | --- |
| before-May baseline contest MAE | 4.4738 |
| after-May baseline contest MAE | 7.3169 |
| Reform signed error, before-May baseline | 8.948 |
| Reform signed error, after-May baseline | 14.634 |
| probe corpus articles | 20 |
| articles naming any study party | 3 |
| all articles local-arm | True |

## Non-news digital trail of the Haslemere campaign, by channel

*Source: nonnews_trail_catalogue.json (register catalogue addendum)*

| channel | records |
| --- | --- |
| candidate_or_party_social_media | 34 |
| council_or_government_page | 7 |
| civic_database | 6 |
| campaign_leaflet_archive | 2 |
| namesake_false_positive | 2 |
| press_topic_index_page | 1 |
| party_site | 1 |
| public_notice_portal | 1 |
| tactical_voting_site | 1 |
| discussion_forum | 1 |
| editorial press articles (the finding) | 0 |

## Canonical v2 corpus per confirmed window

*Source: canonical_corpus_release_v2.json (register section 15; figure 3)*

| window | articles |
| --- | --- |
| 180-91 days | 1840 |
| 90-31 days | 314 |
| 30-15 days | 41 |
| 14-8 days | 36 |
| 7-4 days | 11 |
| final 72h | 17 |
| total (local / national) | 2259 (188 / 2071) |

## Synthetic news scenarios on the frozen v2 model (associational; register section 17)

*Source: scenario_results.json (register section 17)*

| preset | party | tone | arm | articles | window | cell_articles_before | target_party_delta | seat_flips |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tone: same Reform story, favourable vs unfavourable (30-15d, | reform_uk | favourable | combined | 10 | 30-15 days | 7 | 1.003 | 2 |
| tone: same Reform story, favourable vs unfavourable (30-15d, | reform_uk | unfavourable | combined | 10 | 30-15 days | 7 | -2.0029 | 2 |
| timing: unfavourable Reform story, a month out vs the final  | reform_uk | unfavourable | combined | 10 | 30-15 days | 7 | -2.0029 | 2 |
| timing: unfavourable Reform story, a month out vs the final  | reform_uk | unfavourable | combined | 10 | final 72h | 4 | -0.8153 | 8 |
| target: the same unfavourable story about Reform vs the Cons | reform_uk | unfavourable | combined | 10 | 90-31 days | 57 | -0.2725 | 0 |
| target: the same unfavourable story about Reform vs the Cons | conservative | unfavourable | combined | 10 | 90-31 days | 57 | -0.1601 | 22 |
| arm: one favourable Reform story via national vs local colle | reform_uk | favourable | national | 10 | 90-31 days | 45 | 2.1198 | 0 |
| arm: one favourable Reform story via national vs local colle | reform_uk | favourable | local | 10 | 90-31 days | 12 | 7.352 | 264 |

## Exploratory local re-run on v3 (4 of 6 windows improve; sign inversion at 180-91 days)

*Source: rerun_results.json (register local-rerun addendum)*

| window | local_v3_delta | ci_lower | ci_upper | local_v2_sensitivity | combined_confirmatory | national_confirmatory | seat_accuracy |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 180-91 days | 0.325 | 0.25 | 0.403 | 0.289 | -0.575 | -0.59 | 0.7188 |
| 90-31 days | 0.267 | 0.084 | 0.432 | 0.188 | 0.24 | 0.268 | 0.8101 |
| 30-15 days | -0.659 | -0.814 | -0.503 | -0.561 | 0.134 | -0.016 | 0.7115 |
| 14-8 days | 0.015 | -0.063 | 0.094 | 0.018 | -0.325 | 0.005 | 0.7188 |
| 7-4 days | -0.01 | -0.018 | -0.002 | -0.01 | -0.01 | 0.0 | 0.7188 |
| final 72h | 0.259 | 0.084 | 0.417 | -0.833 | 0.188 | -0.023 | 0.8173 |

## Woking South pre-registered blind test: the pick (local, 180-91d) worst of 18; transfer refuted

*Source: unseal_results.json + protocol.json (register Woking South addenda)*

| window | arm | combination_pick | news_mae | baseline_mae | news_vs_baseline | reform_signed_error | winner_correct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 180-91 days | combined | False | 9.3658 | 10.0849 | 0.7191 | -8.2642 | True |
| 180-91 days | local | True | 13.8886 | 10.0849 | -3.8037 | -14.3806 | True |
| 180-91 days | national | False | 9.2116 | 10.0849 | 0.8733 | -8.1771 | True |
| 90-31 days | combined | False | 10.3095 | 10.0849 | -0.2246 | -6.4796 | True |
| 90-31 days | local | False | 9.9168 | 10.0849 | 0.1681 | -6.9059 | True |
| 90-31 days | national | True | 10.3368 | 10.0849 | -0.2519 | -6.4499 | True |
| 30-15 days | combined | True | 10.3739 | 10.0849 | -0.289 | -6.4097 | True |
| 30-15 days | local | False | 9.7695 | 10.0849 | 0.3154 | -7.0657 | True |
| 30-15 days | national | False | 10.3904 | 10.0849 | -0.3055 | -6.3917 | True |
| 14-8 days | combined | False | 9.9975 | 10.0849 | 0.0874 | -6.8182 | True |
| 14-8 days | local | True | 10.0115 | 10.0849 | 0.0734 | -6.803 | True |
| 14-8 days | national | False | 10.0815 | 10.0849 | 0.0034 | -6.7271 | True |
| 7-4 days | combined | False | 10.2121 | 10.0849 | -0.1272 | -6.5853 | True |
| 7-4 days | local | False | 10.2121 | 10.0849 | -0.1272 | -6.5853 | True |
| 7-4 days | national | True | 10.126 | 10.0849 | -0.0411 | -6.6788 | True |
| final 72h | combined | False | 10.2985 | 10.0849 | -0.2136 | -6.4915 | True |
| final 72h | local | True | 10.0124 | 10.0849 | 0.0725 | -6.8022 | True |
| final 72h | national | False | 10.3011 | 10.0849 | -0.2162 | -6.4887 | True |

## Woking South autopsy: the news adjustment worsened all five parties (LD landslide 64.0 encoded nowhere)

*Source: blind_predictions.csv + out_of_fold_predictions.csv (register autopsy addendum)*

| party | observed_share | baseline_prediction | news_prediction | baseline_abs_error | news_abs_error | mae_contribution |
| --- | --- | --- | --- | --- | --- | --- |
| Reform UK | 19.0 | 12.2766 | 4.6194 | 6.72 | 14.38 | 1.531 |
| Conservative | 10.0 | 24.2009 | 29.6292 | 14.2 | 19.63 | 1.086 |
| Labour | 3.0 | 8.5035 | 11.8284 | 5.5 | 8.83 | 0.665 |
| Liberal Democrats | 64.0 | 45.5113 | 43.6591 | 18.49 | 20.34 | 0.37 |
| The Green Party | 4.0 | 9.5078 | 10.2639 | 5.51 | 6.26 | 0.151 |

## Reform-minus-fitted-group level contrast with paired 95% intervals: negative through 2021, positive through 2026 (the sign flip)

*Source: per_party_bootstrap_results.json (register bootstrap-annex addendum)*

| island | arm | window | reform_level_change | fitted_group_change | contrast | ci_lower | ci_upper | excludes_zero |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026 holdout (v2) | combined | 180-91 days | 4.633 | -0.756 | 5.388 | 4.79 | 6.045 | yes |
| 2026 holdout (v2) | combined | 90-31 days | 1.836 | -0.987 | 2.822 | 2.788 | 3.188 | yes |
| 2026 holdout (v2) | combined | 30-15 days | 0.493 | -0.313 | 0.806 | 0.785 | 0.881 | yes |
| 2026 holdout (v2) | combined | 14-8 days | 3.827 | -0.046 | 3.873 | 2.211 | 5.466 | yes |
| 2026 holdout (v2) | combined | 7-4 days | -0.033 | 0.027 | -0.06 | -0.071 | 0.0 |  |
| 2026 holdout (v2) | combined | final 72h | 3.426 | -1.402 | 4.828 | 3.822 | 5.861 | yes |
| 2026 holdout (v2) | national | 180-91 days | 4.716 | -0.775 | 5.491 | 4.909 | 6.123 | yes |
| 2026 holdout (v2) | national | 90-31 days | 1.767 | -1.01 | 2.777 | 2.734 | 3.115 | yes |
| 2026 holdout (v2) | national | 30-15 days | 0.633 | 0.248 | 0.385 | 0.162 | 0.799 | yes |
| 2026 holdout (v2) | national | 14-8 days | 0.017 | -0.014 | 0.032 | -0.001 | 0.037 |  |
| 2026 holdout (v2) | national | 7-4 days | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |  |
| 2026 holdout (v2) | national | final 72h | -0.066 | 0.055 | -0.12 | -0.143 | -0.003 | yes |
| 2021 validation | combined | 180-91 days | -10.257 | 2.715 | -12.972 | -16.794 | -8.052 | yes |
| 2021 validation | combined | 90-31 days | -9.142 | 2.243 | -11.385 | -12.287 | -10.25 | yes |
| 2021 validation | combined | 30-15 days | -9.375 | 5.766 | -15.141 | -18.442 | -11.06 | yes |
| 2021 validation | combined | 14-8 days | -9.375 | 3.154 | -12.53 | -15.899 | -8.518 | yes |
| 2021 validation | combined | 7-4 days | 18.566 | 8.29 | 10.275 | 9.205 | 11.464 | yes |
| 2021 validation | combined | final 72h | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |  |
| 2021 validation | local | 180-91 days | -9.464 | 1.15 | -10.615 | -11.347 | -9.539 | yes |
| 2021 validation | local | 90-31 days | -7.64 | 1.494 | -9.133 | -10.337 | -7.936 | yes |
| 2021 validation | local | 30-15 days | -9.375 | 3.771 | -13.146 | -16.657 | -8.819 | yes |
| 2021 validation | local | 14-8 days | -9.375 | 9.235 | -18.61 | -22.377 | -13.713 | yes |
| 2021 validation | local | 7-4 days | 18.566 | 8.29 | 10.275 | 9.185 | 11.452 | yes |
| 2021 validation | local | final 72h | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |  |
| 2021 validation | national | 180-91 days | -10.639 | 2.56 | -13.199 | -17.143 | -7.892 | yes |
| 2021 validation | national | 90-31 days | -9.476 | 3.282 | -12.758 | -13.648 | -11.536 | yes |
| 2021 validation | national | 30-15 days | -8.736 | 1.548 | -10.284 | -11.433 | -8.972 | yes |
| 2021 validation | national | 14-8 days | -10.413 | 2.797 | -13.21 | -14.495 | -10.438 | yes |
| 2021 validation | national | 7-4 days | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |  |
| 2021 validation | national | final 72h | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |  |

## Design resolution: 80%-power minimal detectable effects (share points) - 2021 resolves ~1pt overall / ~2.6pt Reform-specific; 2026 v2 resolves ~0.2pt

*Source: mde_results.json (register design-resolution addendum)*

| island | scope | comparisons | estimable | median_mde80 | min_mde80 | max_mde80 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026 holdout (v1) | overall MAE delta | 12 | 11 | 0.364 | 0.02 | 0.878 |
| 2026 holdout (v2) | overall MAE delta | 12 | 11 | 0.216 | 0.006 | 0.581 |
| 2026 holdout (v2) | Reform level change | 12 | 11 | 0.045 | 0.006 | 2.226 |
| 2026 holdout (v2) | Reform-vs-group contrast | 12 | 11 | 0.286 | 0.027 | 2.326 |
| 2021 validation | overall MAE delta | 18 | 14 | 0.962 | 0.585 | 2.625 |
| 2021 validation | Reform level change | 18 | 14 | 1.626 | 0.341 | 6.19 |
| 2021 validation | Reform MAE delta | 18 | 14 | 2.601 | 0.809 | 5.273 |
| 2021 validation | Reform-vs-group contrast | 18 | 14 | 2.329 | 1.292 | 6.612 |
