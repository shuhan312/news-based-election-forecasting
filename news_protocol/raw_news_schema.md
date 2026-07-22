# Raw News Schema — Field Documentation

**Stage:** News Retrieval Framework Validation (Task 3).
**Machine-readable definition:** `raw_news_schema.json` (JSON Schema draft-07) — that file is authoritative; this one explains the design.
**Version:** 1.0 (2026-07-22)

## 1. Position in the pipeline

Every article retrieved by *any* route — Guardian API, publisher site, Wayback capture, or a human transcribing microfilm — is normalised into exactly one record of this schema **before** deduplication, eligibility screening, or LLM processing. One schema for all routes means every downstream stage (dedup, eligibility rules E1–E10, band assignment, classification) can be written once, and manually gathered material enjoys the same provenance guarantees as API material.

The record is metadata + provenance only. Full body text lives in `data/raw/news/` (gitignored, copyright-safe); the record carries its path, its SHA-256 hash and a ≤500-character extract. Committing hashes but not text keeps the corpus verifiable without redistributing publisher content.

## 2. Field groups and rationale

### `article_id`, `schema_version`
Deterministic ID (`NEWS-<source>-<hash12>` from the canonical reference), so re-retrieval cannot mint duplicate identities. `schema_version` is pinned per record so a future schema change never silently reinterprets old records.

### `arm`, `discovered_for_election`
Record *which search found the article* — the local/national arm and the election of the plan entry. This preserves the protocol §4 separation of arms at the moment of collection. They describe discovery, not final classification: an article found by a national search may later also be linked to wards; that linkage lives downstream and never overwrites these fields.

### `retrieval.*` — provenance
Who fetched it, how, when, from where, and with what outcome. Key decisions:

* `retrieval_status` makes **failure a first-class record** (`paywalled` / `blocked` / `gone` / `parse_failed`): the audit trail must show what could not be retrieved, not only what could (protocol §5.2 — "retrieval failures are data, not errors").
* `search_query_id` joins every article back to one row of the search log, closing the loop the protocol's reproducibility section requires: corpus ⇆ logged searches.
* `final_url` vs `requested_url` exposes redirects — consent walls, soft 404s and moved articles are visible instead of silent.
* `archive_url` is kept **separate from** `identity.canonical_url`: the publisher URL is the article's identity; the Wayback capture is merely the access route (eligibility rule E7 forbids confusing capture time with publication time).

### `identity.*`
The article as published: publisher, headline, byline (as printed, never inferred — the protocol's no-invention stance), canonical URL, or an `offline_citation` (title, edition date, page) for print material where no URL exists. `canonical_url` may be null only for manual transcriptions.

### `dates.*` — the design's backbone
Everything downstream (window membership, band assignment, leakage exclusion) hangs on the publication date, so the schema stores not just the chosen date but the **evidence for it**:

* `date_evidence[]` lists every candidate date found and where (`json_ld`, `opengraph`, `visible_dateline`, `api_field`, `url_slug`, `archive_citation`, `user_supplied`). Conflicts are preserved for manual resolution, satisfying the protocol's "conflicting dates are never silently resolved".
* `date_confidence` uses the four grades of `article_eligibility_rules.md` §3; records below `Probable` will fail eligibility later, but they are still stored — exclusion happens downstream, transparently.
* `published_time` is usually null for historic material; the calendar-day window design (protocol §3.2) was chosen precisely so that a null time is not fatal, except on polling day.

Deliberately **absent**: `day_index`, band, eligibility verdicts. They are *derived* values; storing them here would freeze protocol decisions into the raw data and force re-collection if a rule were ever revised. Raw records hold facts; derivations stay downstream.

### `content.*`
`text_sha256` (hash of normalised body text) is the exact-duplicate key the dedup stage will use; computing it at retrieval time, before any cleaning decisions, makes duplicate detection independent of later processing. `has_full_text` distinguishes full-body records from extract-only ones (e.g. any future NewsAPI material) so downstream feature counts can condition on text availability.

## 3. Validation

`src/pilot_news_retrieval.py` validates every pilot record against `raw_news_schema.json` with the `jsonschema` library and quarantines non-conforming records instead of dropping them. The production RetrievalRunner (see `source_adapter_framework.md` §5) must do the same at write time.
