# Keyword prefilter: evaluation criteria (written before any measurement)

**Status: fixed 2026-10-07, before the prefilter was run on any article.** The
v0 keyword lists live in `src/v2_design/keyword_prefilter.py` and are
committed together with this file. Later changes go under Amendments, with
their reasons.

## Why

V2's outlet-first collection returns everything a local outlet published.
A cheap, deterministic filter that drops non-political content before any API
call would cut fetch and classification volume. It would also bring the
classifier's input back to the kind of data the frozen classifier was
validated on (`v2_design/local_relevance_v1/baseline_findings.md`). The
filter is useful only if it keeps the articles that matter.

## What "matters": V1's own feature articles

V1's party features (`party_article_count`, portrayal and so on) are built
from LLM stance judgements on named parties
(`src/news_features/build_feature_table.py`). The **1,945 V1 articles with at
least one stance judgement** are therefore exactly the articles that fed the
party features: 1,837 national-arm and 108 local-arm. Their texts are on
disk, so recall can be measured with no new labels.

## Measures

| id | measure | population | bar |
|---|---|---|---|
| **M1** | feature recall: share passing the filter | the 1,945 feature articles | **≥ 0.97** (primary) |
| M2 | relevance recall | human-include local articles (`local_relevance_v1/split.csv`) | ≥ 0.90 (secondary) |
| M3 | removal rate | human-exclude local articles | reported, no bar |

M2 is secondary because a relevant article that names no party and uses no
civic word cannot feed party-level features. Its loss is a cost to local
coverage breadth, not to the features V2 tests. M3 measures the benefit. Its
real-world value (the share of an unfiltered outlet dump removed) is
measured later on actual outlet lists. V1's labelled excludes were
pre-filtered by search, so M3 here understates what the filter removes in
practice.

## Splits and procedure

- The feature articles are split 50/50 by a salted hash of the article id.
  The labelled local articles use the existing split.
- Keyword lists may be revised on **dev only**, by reading the missed
  articles. Each revision gets a new version name (v1, v2, …) and is recorded
  below.
- The **final** version runs on test **once**. That test result is reported
  whatever it is, and the gate is read on its point estimates.

## Decision

- **Pass (M1 ≥ 0.97 and M2 ≥ 0.90):** the filter becomes stage 2 of V2's
  collection pipeline.
- **M1 passes, M2 fails:** adopt it for party features. Record the lost
  local-coverage breadth as a known limitation and report it separately.
- **M1 fails:** do not adopt it. Classify unfiltered output instead, and
  accept the cost.

## Amendments

**A1 (2026-10-07, dev only; test not yet run). v1 is declared the final
version.**

- *v0 on dev:* M1 0.999 (1 of 958 missed), M2 0.798, M3 0.044
  (`prefilter_v0_dev.json`).
- *The one M1 miss was an input defect, not a vocabulary gap.* A Guardian
  article named Labour only in its headline, and V1's stored text files
  hold the body alone. v1 reads headline + body
  (`keyword_prefilter.article_text`). The term lists are unchanged. v1 on dev:
  M1 1.000, M2 0.798, M3 0.044 (`prefilter_v1_dev.json`).
- *The M2 misses are not chased.* All 20 are human includes under L1/L3 that
  name a place and nothing political: 19 crime, accident, court or weather
  stories (e.g. "Motorcyclist dies following serious crash in Gomshall") and
  1 Network Rail level-crossing meeting. None names a party, so none can feed
  party features. Catching them would require place names, which would pass
  almost every local article and void the filter. Per the decision rule, the
  expected outcome is therefore "M1 passes, M2 fails": adopt the filter for
  party features and report the lost place-only coverage as a limitation.
- No further revision. v1 runs on test once, next.
