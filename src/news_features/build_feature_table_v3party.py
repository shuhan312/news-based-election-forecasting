"""Build the party-grain content table on the enrichment corpus.

    python3 -m src.news_features.build_feature_table_v3party

EXPLORATORY. The 2026 holdout was unsealed in section 16, so nothing built
here can become a confirmatory result. What it can do is turn an untested
assumption into a tested one.

## What this table exists to settle

The frozen specifications carry two features: `party_article_share` and
`net_portrayal_share` - volume and tone. Neither is a content feature. The
issue and framing layers never entered any specification, because both failed
the reporting gate at 4 distinct training values within a period against a bar
of 10.

That verdict was correct and its stated cause was not. The same columns carry
26 distinct values pooled ACROSS periods, which is what a per-election
aggregation looks like from the inside: all six parties of an election share
one value, so the only within-period variation left is between the four
elections. `actor_party_attribution` explains the fix; this wrapper runs it.

The consequence for the write-up is the reason this is worth a day. A placebo
that replaces the LLM features with a raw article count reproduces 93% of the
certified effect, which reads as "the LLM layers earn nothing" - but what was
actually tested is that volume plus tone does not beat volume, which is close
to circular. Whether what the news is ABOUT adds anything has not been asked.
Either answer is a result; neither is currently available.

## What changes from v2, and what does not

Tables v1 and v2 are left in place and must keep rebuilding byte-identically -
every committed result was computed from them. Only four module globals move,
exactly as in the v2 wrapper, plus the attribution switch:

- the output paths (``news_feature_table_v3party.*``);
- the corpus source (``canonical_corpus_release_v2.build_release``);
- the split-role map and election grid, which gain the eight by-elections;
- ``PARTY_CONTENT_ATTRIBUTION``, which adds the party-grain content columns.

Every aggregation rule, share definition, zero-cell policy, arm-reconciliation
assertion and gate threshold is the frozen builder's, untouched. The
per-election content columns are still emitted beside the new ones, so the
grain change can be read off a single file: inside any cell the election
column is identical across all six parties and the party column is not.

## What to check before trusting the output

The build prints the gate verdicts. On the training side the party-grain
columns are expected to clear the ten-value bar at 180-91 and 90-31 days and
to fail in the near windows, where the corpus thins to single digits. A
party-grain column that still shows 4 distinct values means the attribution
did not run; a column identical to its per-election twin means it ran and
found nothing to distinguish.

Neither the gate nor this build says the features are informative. That is a
question for a specification measured against the volume-only placebo, not
against zero - a raw count already beats zero.
"""

from __future__ import annotations

from src.news_collection import canonical_corpus_release_v2 as release_v2
from src.news_features import build_feature_table as frozen

# Output paths: v3party files beside the v1 and v2 ones, never overwriting.
frozen.OUT_CSV = frozen.OUT_CSV.with_name("news_feature_table_v3party.csv")
frozen.OUT_META = frozen.OUT_META.with_name(
    "news_feature_table_v3party_metadata.json")

# Corpus source. The frozen builder calls `build_release()` and writes the
# manifest it returns; both are module globals, so rebinding them points the
# identical aggregation code at the v2 corpus.
frozen.build_release = release_v2.build_release
frozen.CANONICAL_MANIFEST = release_v2.OUTPUT

# The chronological split, extended with the eight pre-holdout by-elections -
# the same labelling the v2 wrapper applies, for the same reason: every one of
# them polled before the 2026 holdout.
frozen.SPLIT_ROLE.update({
    election_id: "train"
    for election_id in release_v2.BYELECTION_POLLING_DAYS
})

# The full v2 election grid, stated explicitly rather than derived from
# article presence, so the six by-elections that ended the funnel with zero
# admitted articles stay in the table as observed zeroes instead of silently
# vanishing into "never searched".
frozen.GRID_ELECTIONS = sorted(
    set(release_v2.BYELECTION_POLLING_DAYS)
    | {"SCC-2013-05", "SCC-2017-05", "SCC-2021-05", "ESWS-2026-05"}
)

# The one substantive change: attribute issues and framing to the parties each
# article names, in addition to the per-election aggregation.
frozen.PARTY_CONTENT_ATTRIBUTION = True

# Build from the corpus v2 was built from. Three extraction tranches on disk
# hold articles that release v2 does not admit, and all three were extracted
# AFTER both feature tables were written:
#
#     news_feature_table_v1.csv   2026-08-01 12:26
#     news_feature_table_v2.csv   2026-08-01 16:23
#     haslemere1                  2026-08-01 22:55    20 articles outside v2
#     e5local1                    2026-08-02 01:31    29 articles outside v2
#     wokingsouth1                2026-08-02 17:23   272 articles outside v2
#
# They are case-study corpora, not main-table corpora: the Haslemere probe and
# the Woking South blind protocol each collected their own single-contest
# articles, and the E5 local extension's triage failed validation at kappa
# 0.4762 against a 0.600 bar, so its articles were never admitted anywhere.
# Loading them puts 292 unadmitted articles into the records, which is exactly
# what the builder's corpus assertion exists to stop.
#
# Worth stating plainly rather than leaving to be discovered: with these three
# tranches on disk and this global left empty, **v1 and v2 no longer rebuild**
# - both stop on that assertion, at 948 and 321 articles respectively. The
# committed tables predate the tranches. Nothing here changes that; this line
# only declares which corpus the v3party table is made of, so that its
# comparison against v2 is like for like.
frozen.EXCLUDED_TRANCHES = {"haslemere1", "e5local1", "wokingsouth1"}


def main() -> None:
    frozen.main()


if __name__ == "__main__":
    main()
