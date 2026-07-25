"""Phase 5 - Duplicate and Version Resolution pipeline.

Operates on the frozen Phase 4 normalised text layer; never edits it.

    Step 1  exact_duplicates / build_exact_duplicates
            exact content duplicate detection - relationships only,
            no deletion, no merging, no canonical selection

Later steps (near-duplicates, syndication/versioning, canonical
resolution) append here. Data outputs stay flat under
news_collection/ versioned to match their Phase 4 input
(*_v1_provisional while the input layer is provisional).
"""
