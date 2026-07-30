"""Frozen row counts for the party-level extractor contract.

These numbers are deliberately hardcoded rather than derived from the
contract at run time: they are drift guards. A test that counts the rows
it just loaded and asserts they equal themselves proves nothing, whereas
a literal fails loudly the moment the extractor's output changes - which
is the point. Collecting them here means one edit per contract change
instead of nine, and gives that change a single place to be explained.

History of these numbers:

2026-07-20  1,592 index rows from 1,603 source rows. The figures the
            electoral-fundamentals release was frozen against.
2026-07-29  1,613 index rows from 1,624 source rows. The master election
            database was regenerated and brought in four by-elections
            that the 7-20 contract did not contain: Sunbury Common &
            Ashford Common (2022-11-30, 5 rows), Walton South & Oatlands
            (2023-05-04, 5), Nork & Tattenhams (2025-05-01, 6) and
            Woking South (2025-07-10, 5). Verified as pure addition -
            twenty-one new (election, area, party) keys, zero keys
            removed, zero values changed on any shared key.

Note for the modelling side, not for these tests: those four
by-elections all post-date the 2021 validation split, so they land in
the historical-training fold and train on events later than the fold
they are validated against. That is recorded as an open item in
`news_protocol/feature_selection_findings.md` and is a splitting
decision, not a contract error - the contract is correct to carry them.
"""

# One row per (election, area, standardised party) in the built index.
FUNDAMENTALS_INDEX_ROWS = 1_613

# Rows in the extractor's party-contest feature file before the index is
# built. Higher than the index count because the index drops contests
# that carry no usable party identity.
FUNDAMENTALS_SOURCE_ROWS = 1_624

# Reform UK rows in the release. 94 at the 7-20 freeze; the three extra
# come from three of the four newly-carried by-elections (Sunbury Common
# & Ashford Common, Nork & Tattenhams, Woking South - Reform did not
# contest Walton South & Oatlands). Guards the Reform/UKIP separation
# test: a merge of the two parties would move this number.
FUNDAMENTALS_REFORM_ROWS = 97

# Rows surviving the model-input eligibility filter. 1,235 at the 7-20
# freeze; the twenty-one added by-election rows all pass it, so the
# filter itself is unchanged.
FUNDAMENTALS_ELIGIBLE_ROWS = 1_256

# Reform rows that carry a non-null previous_ukip_vote_share_in_area.
# 83 at the 7-20 freeze; all three new Reform by-election rows land in
# areas with an approved UKIP history, so this moves with the count
# above. Guards that UKIP history reaches Reform rows only as its own
# named column and is never merged into Reform's own history.
FUNDAMENTALS_REFORM_ROWS_WITH_UKIP_HISTORY = 86
