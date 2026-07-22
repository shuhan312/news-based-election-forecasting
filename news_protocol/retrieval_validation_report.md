# News Retrieval Framework — Validation Report

**Stage:** News Retrieval Framework Validation (Task 5).
**Date:** 2026-07-22.
**Verdict:** The framework is **ready for the Raw News Collection stage**, subject to the recommendations in §6 and the protocol revision proposals in §7. No large-scale collection was performed; 15 articles were retrieved in total, purely as validation specimens.

**Evidence produced by this stage**

| Artefact | Contents |
|---|---|
| `news_protocol/evidence/coverage_verification_2026-07-22.json` | Raw probe results behind every coverage-audit update (~50 read-only requests: robots.txt, site search, Wayback CDX counts, Guardian API, archive reachability) |
| `news_protocol/evidence/pilot_records.json` | 15 pilot `RawArticle` records + per-record schema/date validation summary |
| `src/verify_news_coverage_audit.py` | Reproducible audit probe script (Task 1) |
| `src/pilot_news_retrieval.py` | Reproducible pilot script (Task 4) |
| `historical_coverage_audit.csv` | All 52 rows now `verified` or `blocked`; zero `pending` |

## 1. Coverage audit outcome (Task 1)

All 52 source × election rows are resolved. Highlights, each backed by the evidence JSON:

* **Guardian API — verified, full, all four windows.** 584 / 509 / 358 / 307 results for a "Surrey" probe query in the 2013 / 2017 / 2021 / 2026 windows respectively; server-side date filtering honoured. The national arm has a complete, subscription-independent route.
* **NewsAPI — blocked, all four windows** (2026-07-14 test, unchanged): current tier's floor is 2026-06-12. The adapter design keeps NewsAPI dormant behind a healthcheck; nothing else depends on it.
* **Wayback density is strong where it matters and its gaps are now quantified**: SurreyLive and Surrey Comet ≥2000 distinct in-window pages in *every* window; Guildford Dragon 396 (2013) rising to ≥2000; BBC Surrey 261–832 article captures per window; but Woking News & Mail has effectively **no 2013 web presence** (3 pages) and Epsom & Ewell Times has **zero pre-2022 existence** (0 captures in 2013/2017/2021) — both prior assumptions, now test-confirmed.
* **robots.txt finding (new):** SurreyLive, BBC and Surrey Comet all *permit* article-page crawling but **disallow their `/search` paths**. Automated discovery for these three must therefore use Wayback CDX and the manual Google route; the four smaller publishers permit search. This drives protocol revision proposal P1.
* **Google route — verified as manual-only**: a manual-equivalent spot check surfaced live 2013-era and 2026 getsurrey.co.uk election articles; automated Google querying stays prohibited (ToS).
* **BNA and Surrey History Centre — blocked for remote verification** (subscription wall / physical visit). SHC remains the designated gap-filler for Woking 2013; a visit is only warranted after division sampling confirms a Woking-area division is in the sample.

## 2. Adapter framework (Task 2) and raw schema (Task 3)

Designed and documented in `source_adapter_framework.md` (five adapters behind one interface; runner owns logging/pacing/budgets; adapters never judge eligibility) and `raw_news_schema.md` + `raw_news_schema.json` (draft-07 JSON Schema; provenance, date-evidence preservation, hash-before-cleaning). Both were exercised for real by the pilot rather than reviewed on paper: every pilot record was produced through the designed route separation and validated against the schema mechanically.

## 3. Pilot results (Task 4)

Four sources — one vertical slice per automated adapter class, deliberately including the hardest audited cases. ≤4 candidate fetches per source per window; 15 records retrieved.

| Check | Result |
|---|---|
| Schema conformance (`jsonschema`) | **15 / 15 valid** |
| Full text recovered | 15 / 15 (one is a letters page with text but no machine date) |
| Publication date recovered | 13 / 15 (12 `Confirmed`, 1 `Uncertain`, 2 `Missing`) |
| Date confirmed inside the 180-day window | 11 / 15 |
| Routes exercised | API (4), live page (4), Wayback capture (7) |

Per source:

* **guardian_api — PASS, 4/4.** In-window, full-text, `Confirmed`-dated articles for every election including 2013. Metadata arrives machine-readable end to end. No issues.
* **surreylive — PASS with notes, 3/4 in-window.** 2017, 2021 and 2026 slices returned exactly the kind of material the project needs (e.g. *"East Surrey Local Elections: Every candidate standing in Reigate…"*, published 2026-05-05, two days before polls, recovered from a Wayback capture with a `Confirmed` date). The 2013 slice retrieved a genuine in-window *Surrey Advertiser* letters page whose date is print-style prose rather than machine-readable (`Missing` grade) — retrievable, but needing the manual date-confirmation path.
* **bbc_surrey — PASS with a high-value finding, 2/4 in-window.** The 2013 slice retrieved the BBC's Surrey results article: its JSON-LD claims 2013-04-30 (pre-poll) while its visible dateline says 2013-05-03 (results day). The framework **preserved both dates and graded the record `Uncertain`**, exactly as designed — a naive single-date extractor would have accepted a results article into the pre-election corpus on the strength of a wrong machine-readable date. This validates the `date_evidence` design and the `Probable`-or-better eligibility gate (rules E1/E4) against a real, not hypothetical, leakage hazard.
* **guildford_dragon — PARTIAL, 2/4 in-window.** 2017 and 2021 slices returned dated in-window local-politics articles. The 2013 slice landed on a homepage capture (candidate URLs redirect within the archive), and the 2026 slice found no in-window candidates matching the site's historic `/YYYY/MM/` URL pattern — suggesting a post-2021 permalink change to investigate at collection time (the site itself is live, robots-permitting, and searchable).

Duplicate-risk observation: the BBC slice returned the *same* article for two different windows; the records share an identical `text_sha256`, confirming the hash-based exact-duplicate key works across windows as intended.

## 4. Metadata quality

JSON-LD was the most reliable date source across all three CMS families encountered (Reach plc, BBC, WordPress), with OpenGraph and `<time datetime>` as corroborators; conflicts occur in the wild (BBC case above) and the conflict-preserving design is therefore necessary, not defensive over-engineering. Bylines were recoverable where present; headlines always. Body-text extraction via the `<article>`-paragraph heuristic produced usable full text on every route, including 2008-era pre-rebrand pages served through Wayback.

## 5. Known limitations

1. **CDX discovery is capture-based, not publication-based.** Old articles re-crawled inside a window dominate naive CDX slices. The pilot's mitigation (URL-pattern priors + date-verified acceptance) lifted in-window precision from 5/15 to 11/15 under a 4-fetch budget; production needs proper CDX paging and per-source query planning (see R2).
2. **CDX endpoint is slow and rate-limits aggressively** (multiple timeouts at 1.5 s pacing; stable at 6 s with retries). Collection-stage budgets must assume ~6–10 s per CDX call.
3. **Four sources were probe-verified but not pilot-fetched** (Woking News & Mail, Farnham Herald, Epsom & Ewell Times, Surrey Comet). Their search interfaces answered HTTP 200 and robots permits (except Comet's `/search`), but article-page parsing and Farnham's paywall behaviour are untested (see R3).
4. **Undated historic pages exist** (letters pages, early-2010s templates). These fall to the manual date-confirmation path by design; they are a workload estimate issue, not a correctness issue.
5. **Wayback in-archive redirects** can substitute a homepage capture for a dead article URL; production fetch must verify that the returned capture's URL matches the requested article, not just HTTP 200.

## 6. Recommendations before full-scale collection (R-series)

* **R1 — Query planning per source.** Replace the pilot's single generic CDX filter with per-source URL-pattern libraries (Reach article-ID ranges per era; BBC `uk-england-surrey-<id>` ranges; WordPress date permalinks) so discovery starts near the window rather than filtering toward it.
* **R2 — Page the CDX properly.** Use `showNumPages`/pagination instead of `limit`, with the 6-10 s pacing budget and capture-URL verification from L5.
* **R3 — Smoke-test the four unpiloted publishers** as the first act of collection (one article each, healthcheck + parse), before their search logs open.
* **R4 — Route Guildford Dragon 2026 through its own site search** (robots-permitting) rather than CDX, and confirm its current permalink structure.
* **R5 — Manual review queue capacity.** Expect a material minority of historic local articles to need manual date confirmation; the collection plan should schedule reviewer time for this rather than treating it as exceptional.

## 7. Proposed protocol revisions (for supervisor review — protocol NOT modified)

Per the change-control rule (protocol §9), nothing in `news_research_protocol.md`, the registry, or the eligibility rules has been edited beyond the audit's designed pending→verified updates. Two revisions are proposed:

* **P1 — Registry retrieval-method correction.** `news_source_registry.csv` lists `site_search` as the primary retrieval method for SurreyLive, BBC Surrey and Surrey Comet. Verified robots.txt disallows automated use of their search paths. Proposal: change their primary method to `wayback_cdx` with the manual Google route as discovery supplement, leaving article-page fetching unchanged (robots permits it). Justification: legal/ethical compliance verified 2026-07-22; no loss of coverage (audit shows ≥2000 in-window Wayback pages for SurreyLive/Comet and healthy BBC article-capture counts).
* **P2 — Protocol §5.2 ladder annotation.** Add to the retrieval ladder that rung 2 (publisher site search) is conditional on a per-source robots check recorded in the registry, and that rung 4 (Wayback) requires date-verified acceptance (publication date recovered from page content, never capture time — operationalising existing rule E7 at the discovery step).

Both proposals should be tabled at the Friday supervision meeting alongside the NewsAPI subscription decision (which this validation shows is now *optional* rather than blocking: every window has at least one verified route without it).
