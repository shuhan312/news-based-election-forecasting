# Article Eligibility Rules

Companion to `news_research_protocol.md` (v1.0). These rules are applied to every candidate article at collection time, **before** any content classification, and always in the order given: date rules first, leakage rules second, relevance rules third, retrievability last. An article is excluded by the *first* rule it fails, and that rule's code is logged as the exclusion reason. No rule may consider the article's stance, tone, or anything known about the election result.

A candidate article enters this pipeline from a logged search (API, site search, Google date-restricted search, or archive lookup — see protocol §5). Articles that never matched any logged search do not enter the corpus by any other route; ad-hoc additions are prohibited.

---

## 1. Inclusion criteria (all must hold)

| # | Criterion |
|---|---|
| I1 | **Confirmed publication date** at `Confirmed` or `Probable` confidence (Section 3) falling within the election's 180-day window: `1 ≤ day_index ≤ 180`, or polling day with a confirmed pre-07:00 timestamp (protocol §3.5). |
| I2 | **Published before voting began**: nothing at or after 07:00 Europe/London on polling day. |
| I3 | **Relevant to the arm being collected**: satisfies the Local test (L-rules) or the National test (N-rules) below. |
| I4 | **Genuine editorial or published content**: a news report, analysis, opinion piece, editorial, letter, interview, profile, or published press release. |
| I5 | **English language.** |
| I6 | **Minimally retrievable**: at least headline, source, publication date, and either an extract or full text are lawfully obtainable. |

### Local arm test (any one suffices, for a sampled division/ward)

* **L1** — names the division/ward, or a town, village, or identifiable place within it.
* **L2** — names a candidate or sitting councillor for it (in a political or civic context, not e.g. an unrelated namesake — verify against the candidate standardisation table).
* **L3** — concerns a Surrey council decision, service, or issue that identifiably affects it (e.g. a road scheme, school, or development within the division).
* **L4** — Surrey-wide political coverage (county council control, county-wide campaign coverage). Linked at county scope, not duplicated per ward.

### National arm test (any one suffices)

* **N1** — UK national politics involving a party contesting the election: leadership, government/opposition performance, scandal, polling, voter switching.
* **N2** — a national policy issue on the supervisor's list: cost of living, tax, immigration, NHS and public services, local government funding.
* **N3** — Reform UK's national growth or its relationship with the Conservatives, Labour, or the Liberal Democrats (UKIP equivalents for 2013/2017 windows).

An article can qualify for both arms (e.g. a national outlet reporting on Surrey). It is stored once, flagged for both, and its arm-specific linkage follows protocol §4.

## 2. Exclusion criteria (checked in this order; first failure logged)

| Code | Rule |
|---|---|
| E1 | **Date unresolved** — no publication date recoverable at `Probable` or better confidence. |
| E2 | **Outside window** — `day_index > 180` or article postdates polling day. |
| E3 | **Voting under way** — published at/after 07:00 on polling day, or polling-day-dated with no confirmable time (protocol §3.5). |
| E4 | **Result leakage** — reports, previews *citing* results, or reacts to the election's outcome, exit information, or count, regardless of nominal date. A mis-dated results article must never survive on its date alone. |
| E5 | **Irrelevant** — fails every L-rule and every N-rule. Includes sport, entertainment, and commercial content that merely mentions a place name. |
| E6 | **"Reform" false positive** — matched only on the word "reform" used in its ordinary sense (planning reform, NHS reform, etc.) with no reference to the party. Manual disambiguation is mandatory for every "Reform" search hit (supervisor requirement). |
| E7 | **Untrustworthy dating** — the only available date is a crawl/capture/retrieval date (e.g. a Wayback capture timestamp) or a republication date, and the original publication date cannot be recovered. Where both an original and an updated date exist, the original governs and the update is recorded in the article's notes. |
| E8 | **Not editorial content** — adverts, listings, notices, category/index pages, tag pages, search-result pages. |
| E9 | **Non-English.** |
| E10 | **Irretrievable** — paywall, robots restriction, or login wall prevents lawful access to even an extract, and no archive route succeeds. Metadata is still logged; access controls are never bypassed. |

Every exclusion writes one row to the Excluded Articles record: article identifier (URL or archive citation), headline if known, source, nominal date, election, exclusion code, and a one-line note. Exclusions are auditable data, not discards.

## 3. Publication-date confidence

Timing is the design's backbone, so every included article carries a date-confidence grade:

| Grade | Requirement | Usable? |
|---|---|---|
| `Confirmed` | Machine-readable date from page/API metadata (JSON-LD, OpenGraph, API field) **consistent with** any visible dateline. | Yes |
| `Probable` | A single unambiguous visible dateline, or an archive citation (issue date of a print edition), with nothing contradicting it. | Yes |
| `Uncertain` | Conflicting candidate dates, or date inferred only from context (URL slug, surrounding links). | No — resolve manually or exclude under E1 |
| `Missing` | No date recoverable. | No — exclude under E1 |

Conflicting dates are never silently resolved: all candidates are logged and the conflict is settled manually with the evidence recorded, or the article is excluded.

## 4. Duplicates and syndication

* Exact duplicates (same text hash) and syndicated/near-duplicate copies are **retained, not deleted**: each copy keeps its own row, and all copies share a duplicate-group identifier with one copy designated canonical (earliest confirmed publication; ties broken by the more local outlet, since local placement is itself a signal this project studies).
* Eligibility is assessed per copy — a syndicated copy published *outside* the window is excluded even if its canonical twin is inside.
* How duplicate groups are counted in aggregated features is a modelling-stage decision and is out of scope here; the default recorded now is one canonical article per group.

## 5. Edge cases (worked rulings)

1. **Live blogs / rolling coverage** — eligible if the blog's last update predates 07:00 on polling day; the *first* publication timestamp governs band assignment; if updates straddle the cut-off, exclude under E3 unless a pre-cut-off snapshot (e.g. Wayback capture) is used, in which case the snapshot is the article of record and E7 dating rules apply to it.
2. **Print-only articles from microfilm** — issue date of the edition is the publication date at `Probable` confidence; weekly papers' issue dates stand as-is (no back-dating to events described).
3. **Opinion/letters pages** — eligible (I4 includes them); a letters page naming several wards may link to several divisions.
4. **Council or party press releases** — eligible only when *published* by a registry source or found as a published item on the issuing body's site within the window; the publisher is recorded as the issuing body, and the classification stage handles their partisan character.
5. **Paywalled article with a lawful archive copy** — eligible via the archive route (protocol §5.2 rung 4–5); the paywalled URL is recorded as canonical, the archive copy as the access route.
6. **Article about a *different* election** (e.g. 2015 general election coverage inside the 2017 window) — eligible if it meets an N-rule or L-rule for *this* project's parties/places; the classification stage will capture that its subject is another contest. National political context is expressly part of the design.
7. **Post-launch source, pre-launch window** (e.g. Epsom & Ewell Times for 2013) — any hit nominally dated inside a window that predates the source's existence is excluded under E7 (untrustworthy dating) and flagged in the coverage audit.

## 6. Consistency safeguards

* Rules are applied by scripted checks wherever the input is machine-readable (dates, windows, language, duplicates) and by a single documented human pass where judgement is required (E4 result-leakage, E6 Reform disambiguation, L/N relevance). Judgement calls record a one-line justification.
* A 5% random sample of all eligibility decisions (minimum 30 articles per election) is re-checked at the end of collection; disagreements are logged and the affected rule is clarified via the protocol's deviations log before analysis begins.
* No rule in this document may be changed after collection starts except through the deviations log in `news_research_protocol.md` §9.
