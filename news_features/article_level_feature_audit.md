# Article-level Feature Construction Audit

Phase 7, Step 4. Version `article-features-v1.0-2026-07-27`.

## Inputs used (all read-only)

Frozen Phase 6 context layer (sha256-verified against the freeze
manifest before building), Step 1 entity alignment, Step 2 time
window assignment, Step 3 scope classification, the Phase 5
canonical duplicate mapping layer, frozen issue taxonomy v1.3 and
the frozen 16-frame enum (read from the schema file, never
hand-copied).

## Output shape

**207 rows x 171 columns, 67 unique articles.** Unit: article x
election x geographic target x focal party. Rows per election:
SCC-2013 34, SCC-2017 40, SCC-2021 48, ESWS-2026 85. Targets: 68
ward-level rows (exclusively from the 49 validated Step 1 ward
links of 2 articles crossed with their focal parties), 139
election-wide rows. Focal parties: Conservative 41, Labour 41,
Liberal Democrats 22, UKIP 12, Reform UK 11, Green 6, Guildford
Greenbelt Group 5, Residents for Guildford and Villages 5, and 64
no-focal-party rows preserving non-party context. National
articles were not duplicated across wards: every national-scope
row sits at election level (tested).

## Duplicate handling

Only `use_as_canonical_input` articles from the Phase 5 mapping
layer contribute; the runner asserts (and a test re-checks) that
every row's article is canonical and equals its own canonical ID.
Exact/syndicated duplicates therefore cannot contribute twice - the
Phase 5 layer already collapsed them, and this layer refuses
anything it did not collapse.

## Missing and unresolved cases (states, not zeros)

| group | extracted | confirmed_absent | quarantined | not_applicable / no_focal_party |
|---|---|---|---|---|
| mentions | 129 | - | 14 | 64 |
| stance | 142 | 0 | 1 | 64 |
| attribution | 138 | - | 5 | 64 |
| consequence | 121 | 2 | 20 | 64 |
| reform | 8 | 0 | 3 | 196 |
| issues | 166 | - | 41 | - |
| framing | 196 | - | 11 | - |
| temporal (LLM half) | 168 | - | 39 | - |

Quarantined = the underlying frozen record failed its layer's
validation (extraction failure); values are None with the status
naming the reason. Two fields are honestly `not_extracted` rather
than fabricated: party-level mention counts (the frozen contract
counts candidate mentions only) and an election-prediction
indicator (never a frozen field). 21 rows (6 articles) carry
election_result_indicator = 1 per decision D3 - flagged, with the
main-analysis exclusion remaining a modelling-stage switch.

## Validation findings

All checks pass: unique row keys; valid foreign keys against the
official election/party/candidate tables; ward targets only from
validated links; multi-party articles keep separate focal rows and
two focal rows of the same article can disagree in stance (the
cross-party isolation the spec demands - verified positively);
binaries in {0,1}, scores in [0,1]; secondary-issue columns match
the frozen taxonomy exactly (no new vocabulary); not_applicable
and quarantined values stay None while valid absences stay 0;
days_before_polling > 0 everywhere; Reform UK and UKIP never share
a row. Rebuild is deterministic (CSV byte-identical; parquet
frame-identical). Phase 6 and earlier Phase 7 outputs unchanged by
hash.

## Test results

13 new tests in `tests/test_article_features.py` - 13 passed.
Full repository suite: **543 passed, 0 failed**.
