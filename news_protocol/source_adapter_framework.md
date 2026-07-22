# Source Adapter Framework — Design

**Stage:** News Retrieval Framework Validation (Task 2). Design only; source-specific retrieval logic is *not* implemented at this stage.
**Depends on:** `news_research_protocol.md` v1.0 (retrieval ladder §5.2, search logging §5.3), `article_eligibility_rules.md`, `raw_news_schema.md`.
**Version:** 1.0 (2026-07-22)

## 1. Problem

The verified coverage audit shows that no single retrieval mechanism covers all sources and all election windows: the Guardian is API-accessed; NewsAPI is tier-limited; SurreyLive, BBC and Surrey Comet forbid automated use of their on-site search (robots.txt `/search` disallow, verified 2026-07-22) while permitting article-page fetches; small weeklies are searchable directly; 2013-era content often exists only as Wayback captures; and some material is reachable only by manual routes (Google discovery, microfilm transcription). The collection stage therefore needs one uniform interface with per-source implementations, so that search logging, politeness, provenance and schema conformance are enforced **once**, centrally, rather than re-implemented per source.

## 2. Design overview

Retrieval starts from a declared **collection plan** — a committed file stating, in advance, which election, which ward, which query templates and which 180-day window each search serves. The plan is executed by a single central component, the **RetrievalRunner**. The runner knows nothing about any individual news source; it owns only the cross-cutting concerns: request pacing and rate limits, retries, run budgets, and writing one search-log row (protocol §5.3) for every search executed — including searches that return nothing.

To reach the sources, the runner makes uniform calls into five **adapters**, each of which speaks one source family's idiom: the GuardianAdapter (Guardian Content API), the NewsApiAdapter (NewsAPI, dormant until the subscription decision), the SiteSearchAdapter (the four publishers whose robots.txt permits on-site search), the WaybackAdapter (CDX-based discovery and capture fetching — the only automated route for the three robots-restricted sites), and the ManualImportAdapter (which normalises human-gathered material, such as Google-discovered URLs or microfilm transcriptions, through the same pipeline).

Whatever the route, every retrieved article is emitted as one **RawArticle record** conforming to `raw_news_schema.json`; full text is written under `data/raw/news/` (gitignored) and each record is appended to an append-only JSONL index. In short: one planner-bookkeeper at the top, five source-specific hands in the middle, and a single standardised outlet at the bottom.

Two roles are deliberately separated:

* **Adapters** know *how* to talk to one source type. They are stateless translators: query in, standardised hits and articles out. They never decide *what* to search or whether an article is eligible.
* **The RetrievalRunner** owns everything cross-cutting: executing a collection plan, request pacing, retry/backoff, the search log, run budgets, and writing outputs. Eligibility (rules E1–E10) is applied *after* retrieval by a separate step; adapters retrieve, they do not judge.

This mirrors how the election side of the repository already separates fetching from validation, and it keeps every protocol guarantee (log every search including zero-result ones; respect robots; never bypass paywalls) in exactly one place.

## 3. The adapter interface

Every adapter implements the same three operations and one declaration:

### 3.1 `capabilities() -> AdapterCapabilities`

A static declaration the runner uses to plan and to refuse impossible requests:

| Field | Meaning |
|---|---|
| `date_filtering` | `server` (source filters by date: Guardian, NewsAPI, Wayback CDX) / `client` (adapter must over-fetch and filter locally) / `none` (manual routes) |
| `earliest_reachable` | Earliest publication date this source/method can reach, from the verified coverage audit |
| `full_text` | Whether the adapter can return body text lawfully (`yes` / `extract_only` / `no`) |
| `search` | `api` / `site_search` / `cdx` / `manual_only` |
| `robots_constraints` | Paths this adapter must never fetch (e.g. `/search` for SurreyLive, BBC, Surrey Comet) |
| `rate_limit` | Requests per minute the runner must not exceed for this source |

### 3.2 `search(query: SearchQuery) -> list[SearchHit]`

* **Input — `SearchQuery`:** election ID; ward/division ID or `county`/`national` scope; the exact query string from the protocol's query templates; window start/end dates; sort order; max results.
* **Output — `SearchHit`:** candidate article reference *without* content: URL (and archive URL if the hit is a capture), title as listed, date as listed (unverified), source_id, rank in results.
* **Responsibilities:** translate the query into the source's own idiom (API parameters, WordPress `?s=`, CDX regex filter); apply server-side date filtering when capable; return hits in a deterministic order. **Must not** fetch article bodies, must not deduplicate, must not drop zero-result outcomes (an empty list is a valid, logged result).

### 3.3 `fetch(hit: SearchHit) -> RawArticle`

* **Input:** one `SearchHit` (or a manually supplied URL wrapped as one).
* **Output:** one record conforming to `raw_news_schema.json`, with `retrieval_status` set (`ok` / `paywalled` / `blocked` / `gone` / `parse_failed`) — a failed fetch still returns a record, because failures are audit data.
* **Responsibilities:** honour robots and paywalls (record-and-stop, never bypass); extract headline, dateline, machine-readable dates (JSON-LD / OpenGraph), byline, body text where lawful; compute the text hash; stamp full provenance (adapter name+version, access route, retrieved-at timestamp, HTTP status, final URL after redirects). **Must not** assign eligibility, day_index or band — downstream steps do that from the recorded dates.

### 3.4 `healthcheck() -> HealthReport`

A cheap probe (one request) verifying the source still behaves as the coverage audit recorded: reachable, robots unchanged, auth valid. The runner executes healthchecks at the start of every collection run and refuses to proceed against a source whose robots have changed since the audit, forcing a protocol-revision review instead of silent drift.

## 4. Concrete adapters and their bindings

| Adapter | Sources bound | Search mechanism | Fetch mechanism | Notes from verified audit |
|---|---|---|---|---|
| `GuardianAdapter` | guardian_api | Content API `/search` with `from-date`/`to-date` | Same API, `show-fields=bodyText,byline,firstPublicationDate` | Server-side date filtering verified for all four windows |
| `NewsApiAdapter` | newsapi_org | `/v2/everything` | API extract only | Dormant until/unless tier upgrade; healthcheck re-runs the plan-floor test from `check_newsapi_coverage.py` |
| `SiteSearchAdapter` | woking_news_mail, farnham_herald, guildford_dragon, epsom_ewell_times | Publisher's own search (robots-permitting, verified), client-side date filtering | Polite article-page fetch + metadata extraction | One per-publisher config entry (search URL pattern, result selector), not one class per site |
| `WaybackAdapter` | surreylive, bbc_surrey, surrey_comet (discovery + fetch), any source (fetch-fallback) | CDX API with window bounds + URL-pattern filters | Capture fetch (`web.archive.org/web/<ts>/<url>`), preferring the live URL when it still resolves | The only automated discovery route for the three robots-restricted sites; capture timestamp is never used as publication date (rule E7) |
| `ManualImportAdapter` | google_dated_search, british_newspaper_archive, surrey_history_centre | none (`manual_only`) | Ingests a human-completed worksheet row (URL or transcription + citation) and normalises it into a `RawArticle` | Guarantees manually discovered material passes through the *same* schema, logging and provenance as automated material |

## 5. RetrievalRunner responsibilities

1. **Plan execution** — iterate a declared collection plan (election × ward × query template × source), never ad-hoc queries; the plan file is itself committed before collection (protocol §9 pre-registration).
2. **Search logging** — one row per `search()` call with the protocol §5.3 fields (election, ward, exact query, source, date range, executed-at, sort, returned / accepted / excluded counts). Zero-result and failed searches are logged identically. Append-only.
3. **Politeness** — global and per-source rate limits from `capabilities()`, exponential backoff on 429/5xx (the CDX rate-limiting observed during validation is the motivating case), descriptive User-Agent, robots re-checked via healthcheck.
4. **Budgets** — hard caps per run (requests, wall time) so a misbehaving source cannot silently consume API quotas; mirrors the run-budget pattern already used in `fetch_official_scc_results.py`.
5. **Output** — `RawArticle` JSON to `data/raw/news/<source_id>/` (gitignored, one file per article) plus an append-only JSONL index; schema-validate every record against `raw_news_schema.json` at write time and quarantine invalid records rather than dropping them.
6. **Idempotence** — re-running a plan skips already-fetched URLs by text-hash/URL key, so interrupted runs resume without duplicate fetches (duplicates *across sources* are kept — that is the dedup stage's job, not the runner's).

## 6. What is deliberately out of scope for adapters

* Eligibility decisions (E1–E10) — applied downstream so that a rule change never requires re-fetching.
* Deduplication — a corpus-level operation.
* Band/day_index assignment — computed from recorded dates downstream.
* LLM extraction and classification — separate stage.
* Any attempt to bypass paywalls, logins, robots, or anti-bot protections — prohibited everywhere, permanently.

## 7. Validation status of this design

The pilot (`src/pilot_news_retrieval.py`, Task 4) exercises one thin vertical slice of each *automated* adapter class — Guardian API search+fetch, site-search fetch, Wayback CDX discovery+capture fetch — writing genuine `RawArticle` records against the schema. That slice is validation scaffolding, not the production implementation; the production adapters are built in the Raw News Collection stage against this specification.
