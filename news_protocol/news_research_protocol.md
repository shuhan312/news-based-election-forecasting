# News Research Protocol

**Project:** Does pre-election news context improve predictions of Surrey local election outcomes beyond what previous election results already predict?
**Stage:** Planning and documentation only. This protocol defines how news data *will be* collected and evaluated. No articles are retrieved, classified, or modelled at this stage.
**Protocol version:** 1.0 (2026-07-22)
**Status:** Draft for supervisor review

---

## 1. Purpose and scope

This protocol fixes, in advance of any news collection, the rules governing:

1. which elections and time windows news is collected for;
2. which sources are searched, by which retrieval method, and in which order of preference;
3. which articles are eligible for inclusion and which must be excluded;
4. how every search and every eligibility decision is logged so that the collection is reproducible and auditable.

Fixing these rules before collection begins is a pre-registration measure: it prevents the article corpus from being shaped, consciously or not, by knowledge of the election results the corpus is later meant to predict. Any subsequent deviation from this protocol must be recorded in a dated deviations log (Section 9) rather than applied silently.

The protocol implements the supervisor's research requirements (email of record, reproduced in the project's requirement documentation) and takes those requirements as the governing standard wherever earlier working documents differ.

### 1.1 Companion documents

| File | Contents |
|---|---|
| `news_source_registry.csv` | One row per planned news source: type, geographic scope, retrieval method, archive availability, paywall status, known limitations. Column dictionary in Section 7.1. |
| `historical_coverage_audit.csv` | One row per source × election window: whether the source can plausibly cover that window, and the verification status of that claim. Column dictionary in Section 7.2. |
| `article_eligibility_rules.md` | The operational inclusion/exclusion rules applied to every candidate article, with worked edge cases. |

## 2. Elections covered

News collection is anchored to the polling days already established and validated in the election data layer of this repository:

| Election ID | Election | Polling day | 180-day window opens |
|---|---|---|---|
| SCC-2013-05 | Surrey County Council election 2013 | 2013-05-02 | 2012-11-03 |
| SCC-2017-05 | Surrey County Council election 2017 | 2017-05-04 | 2016-11-05 |
| SCC-2021-05 | Surrey County Council election 2021 | 2021-05-06 | 2020-11-07 |
| ES/WS-2026-05 | East Surrey Council and West Surrey Council elections 2026 | 2026-05-07 | 2025-11-08 |

By-elections extracted from the Surrey County Council archive are governed by the same rules, with all windows computed relative to each by-election's own polling day. Whether a given by-election receives news collection is determined by the division sampling step (supervisor's to-do item 7), not by this protocol.

The 2026 elections used new two-member wards on different boundaries from the historic single-member divisions. News collected for 2026 is linked to 2026 wards; news collected for 2013–2021 is linked to the historic divisions. Cross-boundary comparison relies on the existing division-to-ward crosswalk layer and is out of scope here.

## 3. Time windows

### 3.1 Reference clock and cut-off

* All times are interpreted in **Europe/London** (the timezone in which the elections took place and the local press publishes).
* The collection cut-off **C** for each election is **07:00 local time on polling day**, the statutory opening of polls for UK local elections.

**Rationale.** The supervisor's requirement is to "exclude articles published after voting began and articles reporting the result". Polls open at 07:00, so 07:00 — not the 22:00 close of poll used in an earlier working prompt — is the correct leakage boundary: an article published at 10:00 on polling day cannot have informed a vote cast at 08:00, but it *can* contain turnout reporting and same-day campaign coverage that leaks outcome-correlated information. The stricter boundary is adopted; the supervisor's email is the governing standard.

### 3.2 Day indexing

For an article with publication date *d* (Europe/London) and an election with polling date *p*:

```text
day_index = p − d          (in whole calendar days)
```

Example: for polling day 2021-05-06, an article dated 2021-05-05 has `day_index = 1`; an article dated 2020-11-07 has `day_index = 180`.

Windows are defined on `day_index` (calendar days) rather than on exact timestamps.

**Rationale.** A large share of historical local-press material — Wayback Machine captures, newspaper archive scans, and many CMS pages — carries a reliable publication *date* but no reliable publication *time*. Defining windows in calendar days means every article with a confirmed date can be assigned to exactly one band deterministically. The single case where a time is indispensable (polling day itself) is handled explicitly in Section 3.5.

### 3.3 Non-overlapping analysis bands

Every eligible article is assigned to exactly one of six bands, following the supervisor's specification:

| Band | Label | `day_index` range |
|---|---|---|
| B1 | 180 to 91 days before polling day | 91–180 |
| B2 | 90 to 31 days | 31–90 |
| B3 | 30 to 15 days | 15–30 |
| B4 | 14 to 8 days | 8–14 |
| B5 | 7 to 4 days | 4–7 |
| B6 | Final 72 hours | 1–3, plus polling day before 07:00 (Section 3.5) |

The "final 72 hours" band is operationalised as the three calendar days before polling day (plus the pre-poll hours of polling day itself). This is a deliberate approximation: a literal 72-hour clock window would require publication timestamps that most historical sources do not provide, and would split single calendar days across two bands. The calendar-day operationalisation is reproducible from dates alone and differs from the literal window by at most a few early-morning hours at the band boundary.

### 3.4 Cumulative windows

For modelling, six cumulative windows are also computed. Each is a union of complete bands, so no article is ever partially inside a window:

| Cumulative window | Bands included | `day_index` range |
|---|---|---|
| Previous 180 days | B1–B6 | 1–180 (+ polling-day pre-poll) |
| Previous 90 days | B2–B6 | 1–90 (+ …) |
| Previous 30 days | B3–B6 | 1–30 (+ …) |
| Previous 14 days | B4–B6 | 1–14 (+ …) |
| Previous 7 days | B5–B6 | 1–7 (+ …) |
| Previous 72 hours | B6 | 1–3 (+ …) |

Cumulative windows are derived at analysis time by aggregating bands; they are **not** collected separately. Collection targets the full 180-day window once per election, and everything narrower is a subset.

### 3.5 Polling-day articles

An article dated on polling day itself is included (in band B6) **only if** a publication timestamp earlier than 07:00 Europe/London is confirmed from page metadata or the publisher's site. A polling-day article with no confirmable time is **excluded** and logged in the Excluded Articles record with reason `polling-day, time unresolved`. Articles dated after polling day, and any article reporting results or exit information regardless of date, are always excluded (see `article_eligibility_rules.md`).

**Rationale.** Defaulting an untimed polling-day article into the corpus would risk including post-result reaction; defaulting it out costs at most a few articles and is the conservative choice for leakage control.

### 3.6 Boundary conventions

* `day_index = 180` (the earliest day) is **included**; `day_index = 181` is excluded. The window is "180 days before polling day", inclusive.
* Publication dates are the *original* publication dates. Where a page shows both an original and an updated date, the original governs band assignment and the update is recorded (see eligibility rules, rule E7).

## 4. The two collection arms: Local and National

The research design compares a local-news model, a national-news model, and their combination. Collection is therefore organised as two separately logged arms with different linkage rules. Every article is assigned to exactly one arm at collection time; finer five-way classification (ward-specific / Surrey-wide / regional / national / mixed) happens at the later classification stage and is out of scope here.

### 4.1 Local Surrey arm

* **Definition:** coverage whose subject matter is Surrey-specific — a ward/division, a town or village, a named candidate or councillor, a Surrey council, or a Surrey service or issue.
* **Sources:** the Surrey local press and broadcasters in the source registry (SurreyLive, BBC News Surrey, Woking News & Mail, Farnham Herald, The Guildford Dragon, Epsom & Ewell Times, Surrey Comet), reached via the retrieval ladder in Section 5, plus any Surrey-specific results returned by API searches.
* **Linkage:** each local article is linked to the specific ward(s)/division(s), town, candidate, or council issue concerned. One article may link to several wards; each link is a separate record.
* **Search unit:** the sampled division/ward (supervisor's item 7). Query templates follow the supervisor's method: ward name, town/village names, candidate names, councillor names, party AND location, "Surrey County Council" AND location, borough/district council AND location, and major local issues (planning, roads, council tax, …) AND location.

### 4.2 National UK arm

* **Definition:** UK-level political coverage collected for the same 180-day windows: party leadership, government and opposition performance, national scandals, polling and voter switching, cost of living, tax, immigration, NHS and public services, local government funding, and Reform UK's growth and its relationship with the Conservatives, Labour and the Liberal Democrats (UKIP for the relevant historic elections).
* **Sources:** API-accessible national outlets (Guardian Open Platform as the verified full-archive source; NewsAPI.org for windows its subscription tier reaches), supplemented per the registry.
* **Storage:** each national article is stored **once** and linked to the relevant party, election, and time band — never copied into every ward. This follows the supervisor's instruction and avoids double counting in ward-level aggregation.

### 4.3 Reform UK / new-party emergence

Both arms carry the project's new-party question. National-arm searches must include "Reform UK" (and "Reform" with manual disambiguation — eligibility rule E9) for 2026, and UKIP terms for 2013–2021 history. Local-arm searches include Reform UK AND \<location\> templates for 2026. Reform UK and UKIP are always recorded as separate parties, consistent with the party standardisation layer already in the repository.

## 5. Source strategy and retrieval ladder

Full per-source detail is in `news_source_registry.csv`. This section fixes the order of preference, which matters for reproducibility and for the coverage audit.

### 5.1 The verified constraint that shapes the strategy

A live test on 2026-07-14 (script `src/check_newsapi_coverage.py`; output preserved at `data/raw/newsapi/coverage_check.txt`) established that the project's current NewsAPI.org key permits queries **no earlier than 2026-06-12**. All four elections' 180-day windows — including 2026, whose window closed on polling day 2026-05-07 — are therefore **entirely unreachable** on the current tier. NewsAPI's own error messages, one per election, are preserved in the output file. The supervisor anticipated this ("NewsAPI.org may not contain all the historical coverage required… older local articles may need to be obtained from publisher and newspaper archives") and a subscription upgrade decision is with the supervisor.

Consequences, reflected in `historical_coverage_audit.csv`:

* **2013:** the window (2012-11 – 2013-05) predates NewsAPI's index on any tier. Archive-based routes are the only possible routes.
* **2017, 2021, 2026:** reachable *at most* on a paid NewsAPI tier; actual paid-tier depth must be re-verified with the same script if an upgrade is purchased. Guardian and archive routes do not depend on that decision.
* The protocol is deliberately written so that **no collection step is blocked by the subscription decision**: every window has at least one non-NewsAPI route.

### 5.2 Retrieval ladder (applied in order, per source × window)

1. **Documented API** (Guardian Open Platform; NewsAPI.org where the tier permits). Preferred: machine-readable, date-filtered, fully loggable.
2. **Publisher site search / section archive** on the live site, date-restricted where supported.
3. **Google date-restricted site search** (`site:` operator plus date range) to locate URLs the site's own search misses.
4. **Wayback Machine** (CDX index plus captured pages) for articles no longer live or altered since publication. This fallback is approved for the project where official pages are unavailable.
5. **Formal newspaper archives** (British Newspaper Archive, Surrey History Centre / Surrey Libraries newspaper back-issue collections) for pre-digital or de-indexed local coverage, principally 2013.

At every rung: paywalls, robots restrictions and login walls are respected — a blocked article is recorded as blocked (metadata only), never bypassed. Retrieval failures are data, not errors: the search is still logged with zero acceptances and the failure reason.

### 5.3 Search logging

Every search on either arm — **including searches returning zero results** — is logged with: election and ward; exact query string; source/domains searched; date range; date the search was executed; sorting method; number of results returned; number accepted; number excluded. API searches log to the NewsAPI Searches record and site/archive searches to the Local News Searches record, matching the master workbook's tab structure. A search that is re-run (e.g. after a subscription change) is logged as a new row, never edited in place.

## 6. Eligibility

Inclusion and exclusion criteria are specified operationally in `article_eligibility_rules.md`, which is part of this protocol. Summary of principles:

* eligibility is decided from **publication date, leakage status, geographic/political relevance, and retrievability** — never from article stance or from any information about the election result;
* every exclusion is logged with a controlled reason code (the Excluded Articles record);
* duplicates and syndicated copies are retained and grouped, not deleted;
* "Reform" mentions are disambiguated manually before Reform UK linkage.

## 7. Column dictionaries for the companion CSVs

CSV files cannot carry inline comments, so their schemas are documented here.

### 7.1 `news_source_registry.csv`

| Column | Meaning |
|---|---|
| `source_id` | Stable short identifier used by the coverage audit and, later, by search logs. |
| `source_name` | Human-readable name. |
| `source_type` | Controlled: `news_api` / `local_newspaper` / `regional_newspaper` / `national_newspaper` / `broadcaster` / `hyperlocal_news_site` / `web_archive` / `newspaper_archive` / `search_tool`. |
| `arm` | Which collection arm the source primarily serves: `local` / `national` / `both` / `support` (retrieval infrastructure, not a publisher). |
| `geographic_coverage` | Controlled: `ward-level` / `borough-district` / `surrey-county` / `regional` / `uk-national`. |
| `url` | Entry point used for retrieval. |
| `retrieval_method` | Controlled: `api` / `site_search` / `google_date_search` / `wayback_cdx` / `archive_subscription` / `physical_archive`. Primary method; the ladder in §5.2 governs fallbacks. |
| `available_years` | Years of coverage believed available through this source/method, as known at protocol time. |
| `archive_availability` | Whether historical (non-live) content is reachable: `full_api_archive` / `wayback_captures` / `paid_archive` / `physical_only` / `live_site_only` / `n/a`. |
| `paywall_status` | `none` / `metered` / `hard` / `subscription_service` / `n/a`. |
| `known_limitations` | Free-text, kept short; anything that could bias coverage (launch date after early elections, sparse Wayback capture, OCR quality, etc.). |
| `verification_status` | `verified` (tested in this repository, with pointer) / `reported` (stated by provider, untested) / `pending`. |

### 7.2 `historical_coverage_audit.csv`

One row per source × election. `window_start`/`window_end` are the 180-day window bounds from Section 2.

| Column | Meaning |
|---|---|
| `source_id` | Foreign key to the registry. |
| `election_id` | Foreign key to the election data layer (Section 2). |
| `polling_day`, `window_start`, `window_end` | The window being audited (dates, Europe/London). |
| `expected_coverage` | Controlled: `full` / `partial` / `none` / `unknown` — best current assessment of whether this source can supply articles for this window via its registered method. |
| `coverage_basis` | Why we believe it: `tested_in_repo` / `provider_documentation` / `source_launch_date` / `wayback_spot_check_pending` / `assumption`. |
| `verification_status` | `verified` / `pending` / `blocked`. `verified` requires evidence in the repository; `blocked` means tested and refused (e.g. NewsAPI tier limits). |
| `evidence` | Pointer to the evidence (file path or URL); empty only when status is `pending`. |
| `notes` | Short free text. |

The audit currently contains one *verified* set of rows (NewsAPI, all four elections, `blocked`, evidence `data/raw/newsapi/coverage_check.txt`) and one *verified-by-design* set (Guardian Open Platform archive depth, to be spot-checked as the first act of the collection stage). All other rows are `pending`: **completing this audit — turning every `pending` row into `verified` with evidence — is the first task of the collection stage and a precondition for querying that source.**

## 8. Ethical and legal constraints

* Respect robots directives, paywalls, and login requirements at every rung of the retrieval ladder; never use automation to defeat access controls.
* Store article full text only where lawfully and practically available; otherwise store metadata, the API-provided extract, and short supporting passages for classification evidence (fair-dealing scale quotation, not wholesale reproduction).
* Identify the crawler honestly (clear user agent) and apply polite request pacing — infrastructure for this already exists in the repository's official-results fetchers and is reused, not re-implemented.
* British Newspaper Archive and similar subscription archives are used under their licence terms; scans are consulted, and facts and short passages extracted, but page images are not redistributed in the repository.

## 9. Reproducibility and change control

* This protocol is version-numbered. Any change after collection begins is made by incrementing the version and adding a dated entry to the **Deviations log** below, stating what changed, why, and which already-collected data are affected.
* Every search is logged (Section 5.3); every exclusion carries a reason code; every coverage claim carries evidence. A third party holding this repository and the same API keys should be able to re-run the collection and reconstruct the same corpus up to source-side changes.
* The randomised or criteria-based selection of the 15–25 sampled divisions (supervisor item 7) will be documented *before* local-arm collection begins, in this directory, so that ward selection cannot chase news availability.

### Deviations log

| Date | Version | Change | Reason | Data affected |
|---|---|---|---|---|
| — | 1.0 | Initial protocol | — | none (pre-collection) |
| 2026-07-24 | 1.1 | Arm-split E5 gating provisionally adopted (eligibility_manual_review_methodology.md §9): E5-national taken from the frozen v2 corpus scan (validation kappa 0.674, n=69, primary bar); E5-local stays fully manual. Post-hoc subgroup analysis, adopted under the explore-first working arrangement; supervisor ratification due 2026-07-31. | E5 failed validation only on the local arm; the national arm passed the primary pre-registered bar. Reduces manual E5 from 2,370 to 334 rows. | E5 decisions for 2,036 remaining national-arm records (provenance-flagged, reversible) |
