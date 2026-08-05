"""Build news feature table v2 on the enrichment corpus.

    python3 -m src.news_features.build_feature_table_v2

Table v1 (288 rows, 4 elections) is left in place: it is the table every
pre-enrichment result was computed from. This wrapper re-runs the frozen
builder against canonical release v2, so every aggregation rule, share
definition, zero-cell policy, arm-reconciliation assertion and
training-variation verdict is byte-identical to v1's - only three module
globals change:

- the output paths (``news_feature_table_v2.*``);
- the corpus source (``canonical_corpus_release_v2.build_release``);
- the split-role map, which gains the eight pre-holdout by-elections.

All eight by-elections are labelled ``train``. That is the enrichment's
whole point - they exist to enlarge the pre-2026 fitting side - and it is
also the honest label under the supervisor's chronological rule: every
one of them polled before the 2026 holdout, and the five 2025
by-elections additionally sit *after* the 2021 validation election, which
matters only if 2021-based validation were re-run against them; the v2
model's protocol instead fits on everything pre-2026, as the v1 blinded
protocol already declared for its pooled variant.

The training-variation verdicts this build prints are the enrichment's
measure of success: columns that were `insufficient` at 2 training cells
should now clear the fit threshold, and the metadata records exactly
which did.
"""

from __future__ import annotations

from src.news_collection import canonical_corpus_release_v2 as release_v2
from src.news_features import build_feature_table as frozen

# Output paths: v2 files beside the v1 ones, never overwriting them.
frozen.OUT_CSV = frozen.OUT_CSV.with_name("news_feature_table_v2.csv")
frozen.OUT_META = frozen.OUT_META.with_name(
    "news_feature_table_v2_metadata.json")

# Corpus source: the frozen builder calls `build_release()` and writes the
# manifest it returns; both names are module globals, so rebinding them
# points the identical aggregation code at the v2 corpus.
frozen.build_release = release_v2.build_release
frozen.CANONICAL_MANIFEST = release_v2.OUTPUT

# The supervisor's chronological split, extended: the eight pre-holdout
# by-elections join the training side of the final pre-2026 fit.
frozen.SPLIT_ROLE.update({
    election_id: "train"
    for election_id in release_v2.BYELECTION_POLLING_DAYS
})

# The full v2 election grid, stated explicitly. Six of the eight by-elections
# ended the funnel with zero admitted national articles (their coverage was
# local-heavy and local E5 review was skipped); deriving the grid from
# article presence would silently drop those elections, turning "searched,
# nothing eligible" into "never searched". Zero-coverage rows carry count
# zeroes and blank shares, exactly as the frozen zero-cell policy specifies.
frozen.GRID_ELECTIONS = sorted(
    set(release_v2.BYELECTION_POLLING_DAYS)
    | {"SCC-2013-05", "SCC-2017-05", "SCC-2021-05", "ESWS-2026-05"}
)

# Three tranches were extracted AFTER this table was written and hold 321
# articles release v2 does not admit, which stops the build on the corpus
# assertion:
#
#     news_feature_table_v2.csv   2026-08-01 16:23
#     haslemere1                  2026-08-01 22:55    20 articles
#     e5local1                    2026-08-02 01:31    29 articles
#     wokingsouth1                2026-08-02 17:23   272 articles
#
# The first and third are single-contest case-study corpora with releases of
# their own; the second is the E5 local extension, whose triage failed
# validation at kappa 0.4762 against a 0.600 bar, so its articles were never
# admitted anywhere. None of them belongs to this lineage.
#
# Naming them restores the property a committed table is supposed to have:
# with this line the rebuild is byte-identical to the committed CSV, and
# without it the table cannot be rebuilt at all.
frozen.EXCLUDED_TRANCHES = {"haslemere1", "e5local1", "wokingsouth1"}


def main() -> None:
    frozen.main()


if __name__ == "__main__":
    main()
