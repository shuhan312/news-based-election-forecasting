# Context Aggregation - Error Analysis

Phase 7, Step 5. Companion to `context_aggregation_audit.md`:
where the aggregation scheme is under strain and how each strain is
contained.

## 1. Sparsity is the dominant risk, and it is structural

544 groups over 67 articles means most cells hold 1-2 articles;
proportions computed on denominators of 1-3 are formally valid but
statistically meaningless. Containment: the denominators ride
beside every proportion, so the modelling stage can (and should)
threshold on cov_n_articles / stance_denom rather than trust a
1-article 100% negativity rate. At full-corpus scale the same code
produces usable cells; nothing here needs redesign.

## 2. Cumulative windows invite a summation mistake

Cumulative rows overlap by construction (an article in the last 72
hours is also in all five larger windows). Summing cov_n_articles
across cumulative windows double-counts massively. Containment:
window_type is an explicit key, the dictionary carries a bold
warning, and the nesting-monotonicity test documents the intended
reading (each cumulative row is a self-contained snapshot).

## 3. The ward fan-out concentrates in one article

376 ward-level rows trace back overwhelmingly to the single 2026
candidate-guide article crossed with 43 validated wards and its
parties. Those cells genuinely have that article as their only
news, so the aggregates are correct - but any later "ward news
coverage" comparison must remember that ward cells are mostly
one-guide-article cells at pilot scale (the Step 1 audit's sparsity
finding, now visible in aggregate form).

## 4. Article-level attributes are multiplied by focal parties

Issue and frame membership are properties of the ARTICLE, but rows
are article x focal party, so an article naming three parties
contributes its issue and frame flags three times. Within a single
aggregate row this is correct (the row is one party's view of the
news reaching it), but summing `issue_*_n` or `frame_*_n` ACROSS
rows yields party-weighted totals, not article counts. Relative
ordering survives the weighting; absolute readings do not.
Containment: `cov_n_articles` is the only article-count column, and
the contributions file gives exact article IDs whenever a true
article count is needed.

## 5. Zero-denominator groups are informative, not broken

341 group-signals have stance_denom = 0 - mostly no-focal-party
rows (64 article-rows carry non-party context only) and
quarantined layers. Their proportions are None by rule. The next
step (missing-news representation) is the designed place to encode
"no news" formally; this layer only refuses to fake it as zero.

## 6. Known inherited limits

The sentiment baseline is the stance distribution (no independent
sentiment extraction exists) - documented, not hidden. The net
credit-minus-blame count is descriptive and may be negative; any
causal reading is forbidden by the dictionary. Result-flagged (D3)
articles remain inside aggregates with cov_n_result_flagged
recording their presence per group; the modelling-stage switch
excludes them from the main analysis with a sensitivity pair.
