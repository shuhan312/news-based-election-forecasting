# Entity stance / sentiment - error analysis (Phase 6 Step 4)

One validation error in 67 articles, plus one content-level
ambiguity class surfaced by manual review. Nothing reached usable
data unchecked.

## 1. Non-verbatim title quote - 1 record (T1)

One House-of-Lords row cited a paraphrased title ("Lords rebuffs
illegal bill"). Caught by string-matching and quarantined -
consistent with the ~2-5% residual verbatim-error rate seen in every
layer. No new mitigation needed beyond the existing hardened rule;
the record sits in the review pool.

## 2. Ambiguity class: bidirectional trajectory signals (not an error)

Manual review found a real case the single-value
`support_trajectory` field cannot fully carry: the Davey/Reform
article frames Reform BOTH as a rising threat (vote tactically or
wake up to a Reform council) AND as recently dented (its chances
"hurt" by positioning on Trump and Iran). Step 4 read "losing" from
the explicit claim, Step 2 had read "gaining" from the threat
framing - both grounded, both quoted. Handling for full scale:

- keep the field single-valued (a per-article dominant reading is
  what downstream aggregation needs);
- instruct the extractor to judge trajectory from the article's
  DOMINANT explicit claim and to lower confidence when signals
  conflict (low confidence then routes to review via T2);
- the human-review protocol notes this as a known adjudication
  class alongside the Step 3 adjacent-code rules.

## Non-errors worth recording

- Zero invented stance values, zero article-level sentiment
  attempts, zero duplicate entity rows (T3), zero switching claims
  without detail (T4) - the four structural disciplines held across
  all 263 rows;
- 12 honest empty stance sets passed correctly as partial-with-note;
- 5 low-confidence rows all landed in review-flagged records (T2);
- stance_origin was populated meaningfully throughout, including
  correctly attributing negative stances on Badenoch and Farage to
  quoted attack lines rather than journalist narration.
