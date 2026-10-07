# Multi-council feasibility probe: criteria (written before any probe data)

**Status: fixed 2026-10-07, before any probe query was run.** The probe
results are read against these thresholds, and the thresholds are not moved
afterwards. Any later change is recorded below as an amendment, with its
reason.

## Why the probe exists

`v2_design/power_v1` shows that V2 needs tens of whole-council elections.
Surrey supplies one every four years. The probe asks one question: can a
single person obtain comparable data for other councils, automatically and
cheaply? It counts availability only. It never reads, prints or analyses
vote counts, winners or any other outcome.

## A finding from reading V1's collection code, which shapes the probe

V1's usable corpus is 2,259 articles: **2,071 national-arm and 188
local-arm** (`news_collection/canonical_corpus_release_v2.json`). National
coverage (Guardian API, dated Google search) is the same for every council
that votes on the same day. Adding councils at one election date therefore
adds **no** independent national-content signal. Only local coverage varies
by council. So the multi-council expansion is worth what its **local** news
is worth, and the probe measures local coverage.

V1 also could not automate local relevance screening: the frozen LLM
classifier failed validation on the local arm (rule E5), so local E5 stayed
fully manual (`news_protocol/news_research_protocol.md`, v1.1 amendment).
That is a known scaling blocker the probe cannot test. It is recorded as
criterion N3.

## Design

- **Target council:** Kent County Council. Like Surrey it is a two-tier
  county council, and it has whole-council elections in 2017, 2021 and 2025,
  which allows forward-chaining.
- **Calibration:** every news measurement is run identically on Surrey 2021.
  Kent is judged against Surrey under the same method, not against V1's
  manually curated corpus.
- **Window:** 90–31 days before polling day, V2's intended primary window.
- **Sources:** Democracy Club (results and divisions, free). Serper dated
  Google search, V1's main route, with link and snippet only and no article
  fetch. Wayback CDX for each council's main local outlets (free).

## Criteria

| id | measure | pass | partial | fail |
|---|---|---|---|---|
| R1 | Kent 2017/2021/2025: share of divisions with a candidate list in Democracy Club | ≥95% | 80–95% | <80% |
| R2 | Kent 2017/2021/2025: share of divisions whose result record exists (presence only, values not read) | ≥90% | 60–90% | <60% |
| R3 | Division boundaries changed between consecutive Kent cycles? | recorded, not graded: a change adds a notional-mapping engineering task | | |
| N1 | Kent's in-window local-domain unique URLs from identical Serper query templates, as a ratio to Surrey 2021 | ≥0.5 | 0.2–0.5 | <0.2 |
| N2 | Kent's main local outlets: in-window article-like Wayback captures, as a ratio to Surrey's outlets | ≥0.5 | 0.2–0.5 | <0.2 |
| N3 | Local relevance screening can be automated | not testable by this probe; known V1 blocker carried forward | | |
| C1 | Projected Serper cost per council-election at V1's query volume | ≤ £10 | £10–50 | > £50 |

## Decision rule

- **Go:** R1, R2, N1 and C1 pass. Proceed to a 3–5 council pilot. In parallel,
  make automated local relevance screening (N3) the first engineering task.
- **Partial:** any of N1 or N2 is partial. Proceed only with councils whose
  local press is comparable, and pre-register a 0.3pp smallest effect of
  interest.
- **No-go:** N1 fails, or R1/R2 fail. Do not scale local news collection.
  Fall back to the alternatives in `v2_design/power_v1/design_power_findings.md`:
  division-level content, or a prospective frozen forecast of a future
  election.

## Known limitation, stated in advance

The Kent 2025 outcome is public knowledge, so no 2025 council is blind in the
way V1's 2026 holdout was. V2's confirmatory claims must rest on
pre-registration plus forward-chained evaluation, or on a prospective
forecast. This probe does not change that.

## Amendments

**A1 (2026-10-07, after the probe ran). No threshold is moved. Two news
measures are declared invalid, and the reasons are recorded.**

- *N1 measured mostly non-news.* The exclusion-based "local news" class
  admitted job boards, map sites, academic repositories, local party
  websites and US government pages (e.g. Kent County, Michigan). Only 5–14
  of each election's 26–93 "local" URLs were news publishers. The
  pre-registered N1 ratios are reported in `probe_findings.md` but are not
  used for the decision. A supplementary N1′ counts news-publisher URLs only.
  Publisher status was judged once, on the pooled domain list for all four
  elections, by the rule "a UK news organisation publishing reported
  articles". Its denominator (Surrey 2021) is 5 URLs, so N1′ is too small to
  grade either.
- *N2 measured crawler behaviour, not publication volume.* 31,038 of
  Surrey's 38,710 captures come from `getsurrey.co.uk`, a domain retired
  before 2021. Capture counts track crawl frequency and redirects. N2 is
  reported but not used for the decision.
