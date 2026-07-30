# What the news layer can and cannot measure

**Recorded 30 July 2026, after the corpus extraction completed.** Every figure
below is measured from the extracted corpus, not estimated. The modules that
produced them are named so each can be re-run.

**Corpus-scope correction (canonical release
`canonical-news-v1-59d113bb9c28`).** The main eligibility decision table has
1,452 includes (120 local, 1,332 national), but it is only one adjudication
stream. The terminal-decision union has 1,638 articles; six national records
have no usable text, leaving the production feature corpus at **1,632 articles
(188 local, 1,444 national)**. All tables below now use that production scope.
The 67-article article-level/ward-party chain is historical pilot evidence and
is explicitly labelled in `ARTIFACT_LINEAGE.md`.

The short version: the table now emits 47 candidate columns. **Twelve carry
enough training variation to be reportable**: six combined-arm party features
and their six national-only equivalents. The six local-only equivalents are
fittable but remain below the ten-cell reporting threshold. This is now the
specific reason local enrichment matters; it is not inferred from the old
120-article diagnostic.

---

## 1. Articles cannot be attributed to wards

`src/news_features/diagnose_article_area_attribution.py`

The baseline predicts election x area x party. A news feature that exists only
per election gives every area in that election the same value, so it can explain
differences between elections and between parties but nothing between areas —
and which area a party does well in is the prediction problem.

| route to an area | articles | share of 1,632 |
| --- | ---: | ---: |
| the search query named a ward | 46 | 2.8% |
| body text names exactly one area | 22 | 1.3% |
| body text names several areas | 26 | 1.6% |
| **no Surrey area anywhere** | **1,538** | **94.2%** |

Body-text matching was tried rather than assumed: 108 distinct published area
names, collapsed across the " Ward"/" Division" suffixes, matched longest-first
so "Camberley West" is not credited to "Camberley", with four names
(`Ash`, `Ewell`, `Horley`, `Hale`) excluded as too generic to match safely. It
raises unambiguous attribution from **2.8% to 4.2%**. That route remains too
sparse for a general ward-level feature.

**The two arms differ completely, and the difference is structural rather than a
defect.**

| arm | articles | single area | distinct areas named |
| --- | ---: | ---: | ---: |
| national | 1,444 | **4 (0.3%)** | 4 |
| local | 188 | **64 (34.0%)** | 88 |

National coverage naming no Surrey place is what national coverage is. Local
coverage is 34% attributable. So the supervisor's hypothesis divides along the
data's own grain:

> "Whether national Reform UK momentum identifies its general growth, while
> local coverage identifies the Surrey wards where that support is most likely
> to convert into votes or seats"

The first half needs election-level features and is testable. The second half
needs area-level ones and rests on 64 unambiguously attributable local
articles. Coverage is still too uneven to broadcast a defensible ward-level
signal across the 2026 holdout, and a missing value there is indistinguishable
from “no coverage existed”.

All 68 unambiguously attributable articles come from the four principal
elections and none
from by-elections, so the 2026-07-30 decision to scope by-elections out of the
news layer costs no area-level information.

---

## 2. Election-level features have two training cells

`src/news_features/diagnose_feature_grain.py`

Cells inside the supervisor's training period (2013 + 2017):

| grain | cells, all elections | cells in training | median articles per cell |
| --- | ---: | ---: | ---: |
| per election | 4 | **2** | 497 |
| per election x party | 22 | **10** | 172 |

Two points determine a line exactly. A coefficient fitted on two training values
reproduces them and generalises nothing, so every per-election feature —
the six issue features, both framing features, most of the volume block, and
`reform_share_of_coverage` — cannot be fitted, whatever its article count.

**Reform UK has zero training-period articles.** The party did not exist in 2013
or 2017. Measured per party per split role:

| party | train | validation | test |
| --- | ---: | ---: | ---: |
| labour | 507 | 169 | 247 |
| conservative | 504 | 178 | 175 |
| liberal_democrat | 281 | 48 | 95 |
| **ukip** | **325** | 41 | 13 |
| **reform_uk** | **0** | 15 | 175 |
| green | 80 | 16 | 65 |
| green | 76 | 14 | 51 |
| **reform_uk** | **0** | 9 | **115** |

So no Reform-specific news coefficient can be estimated. Any relationship must
be learned **party-generically** — from the five parties present in 2013 and
2017 — and applied to Reform in 2026. Whether a relationship estimated on
established parties transfers to an insurgent with no incumbency and no history
is the central extrapolation of this project. It cannot be validated on the
training data, only tested once on 2026.

UKIP is the closest structural analogue available: 308 training articles, a
right-populist challenger in the same position, and reduced to 7 test-period
articles as Reform took its place. The brief explicitly permits a UKIP-Reform
history field while keeping the parties separate, so this is a sanctioned route
rather than a workaround.

---

## 3. The by-election corpus exists, is unprocessed, and would change the table

**3,122 articles were collected for 10 by-elections and never entered the
eligibility pipeline.** Not excluded — never assessed.

| pipeline stage | by-election coverage |
| --- | --- |
| date resolution (`effective_dates_v2.csv`, 11,787 rows) | **0 rows** |
| mechanical eligibility (`eligibility_assessment_v2.csv`, 11,787 rows) | **0 rows** |
| review sheet, LLM judgement, decisions, extraction | dependent on the above |

All six stages are unrun for by-elections. The first pass at costing this route
counted only the last two and was withdrawn.

**What it would buy, measured on the text already on disk** using the same
deterministic party patterns the stance layer uses:

| by-election | articles with text | mention Reform UK | mention UKIP |
| --- | ---: | ---: | ---: |
| addlestone 2025-08-21 | 1,689 | **238 (14.1%)** | 31 (1.8%) |
| camberley-west 2025-10-16 | 742 | **175 (23.6%)** | 16 (2.2%) |
| the other eight | 442 | 12 (2.7%) | 1 (0.2%) |

**425 by-election articles mention Reform UK, all in the pre-holdout period.**
Discounted by the principal elections' own funnel — 61% eligibility, 82%
producing a valid stance record — that is roughly **213 usable Reform training
observations against the current zero**.

The by-election arm split is also the reverse of the principal elections':
2,129 local against 993 national, where the canonical principal-election
feature corpus has 188 local against 1,444 national. By-elections are
single-area events, so their articles attribute
to an area by construction.

Eight of the ten by-elections fall before the 2026 holdout, which would take the
per-election grain from 2 training cells to 10.

**The original objection stands but has a fix.** By-elections were scoped out
because search completeness ranges from under 12% to 100%, which contaminates
count-based features. It does not contaminate shares: search depth moves
numerator and denominator together. Every count in the feature table therefore
has a companion share, so this data would be usable through the share columns
whatever its completeness.

No cost is quoted here. The six unrun stages have to be walked through without
sending requests before a figure means anything, and the E5-local rule — the one
rule whose automated classifier failed validation — applies to 2,129 local-arm
articles.

---

## 4. The feature table, and what it admits

`src/news_features/build_feature_table.py` → `news_feature_table_v1.csv`

Grain **election x party x period**: 4 elections, 6 parties, 6 windows plus 6
cumulative snapshots, 270 rows after dropping empty cells. Windows are the six
the supervisor confirmed on 30 July and were not changed.

**Deduplication and its guard.** Tranche files overlap — far2's articles were
re-extracted in the full run while its stance and framing records stayed in
place, so concatenating the files double-counts **98 articles for framing and 66
for stance**, and raw framing rows exceeded the corpus at 1,730 against 1,632.
Records are deduplicated on `article_id` with the newest tranche winning, and the
build asserts unique articles never exceed corpus size. It reports **1,632 of
1,632**.

**Twelve columns carry usable training variation.** The six combined columns
below and their six `national_` equivalents all clear the reporting threshold:

| column | distinct training values within a period |
| --- | ---: |
| `party_article_count` | 11 |
| `party_article_share` | 11 |
| `unfavourable_count` | 11 |
| `favourable_count` | 11 |
| `net_portrayal` | 11 |
| `net_portrayal_share` | 10 |

All twelve are per-party. The six `local_` equivalents have 5–9 distinct
training values within a period: enough to fit, but not enough to report under
the pre-declared ten-cell rule. The remaining 29 columns are insufficient.

**A fault in the first version of that verdict, recorded because it would have
matters.** Variation was first counted across all 270 rows, which pools the 12
periods together. That gave `article_count` 14 distinct training values and
marked it usable — but a specification uses one window, and within any single
period it has **2**. Counting per period instead moved 29 columns from "usable"
to "insufficient". Uncorrected, the model would have been offered 29 features
that appear to vary and do not.

---

## 5. What the brief asks, and what can be answered

| the brief's question | answerable |
| --- | --- |
| Does news improve prediction of Reform vote share over election history alone? | **Yes** — through the six per-party columns |
| Does news help more at some windows than others? | **Yes** — all 12 periods are in the table |
| Do local Surrey news and UK national news have different predictive value? | **Partly** — national features are reportable; local party features are fittable but below the ten-cell reporting threshold |
| Does local coverage identify which wards convert support into seats? | **No** — 94.2% of articles carry no unambiguous area and coverage is highly uneven |
| Do particular issues (local crime, national immigration) predict Reform support? | **No** — per-election grain, 2 training values |
| Do narrative frames predict Reform support? | **No** — same grain |
| Can news identify an emerging party before it has a voting record? | **Partly** — no Reform training articles, so only a party-generic relationship extrapolated to Reform |

Four of the seven are blocked by one cause: the per-election grain has two
training cells. The by-election corpus in §3 is the only route that changes
that, and whether it is worth walking should be decided after the first
news-versus-baseline comparison shows whether the six usable columns carry any
signal at all. Spending on enrichment before knowing that is the wrong order.
