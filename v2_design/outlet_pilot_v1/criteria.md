# Outlet-first pilot: criteria (written before any article is fetched)

**Status: fixed 2026-10-07.** The URL sample (`sample.csv`,
`population.json`) was drawn before any article was fetched, and is committed
together with this file and the code (`src/v2_design/outlet_pilot.py`).
Nothing is changed after results are seen. Later changes go under
Amendments, with their reasons.

## Why

Each pipeline stage has been checked on its own: Wayback archives exist
(`feasibility_probe_v1`), keyword prefilter v1 keeps every V1 feature article
(`keyword_prefilter_v1`), and the frozen classifier meets V1's bar on
consistently labelled data (`local_relevance_v1`). They have never been run
together on real, unfiltered outlet output. This pilot does that, for Kent
2021 against Surrey 2021 under an identical procedure, and finally answers
the question the feasibility probe could not: is Kent's local **political**
coverage comparable to Surrey's?

## Design

- **Outlets** (analogous triples): Surrey: getsurrey.co.uk (SurreyLive's
  2021 domain), BBC Surrey, Surrey Comet. Kent: KentLive, BBC Kent,
  KentOnline. The population is each site's **news section** (`/news/`) where
  the URL scheme allows it. Whole-domain listings timed out on Wayback and
  mostly add sport, listings and media pages. KentOnline has no single news
  prefix, and its whole-domain listing failed on Wayback (repeated 504), so
  it is listed section by section (`/<town>/news/`, 23 town sections) and
  merged into one outlet.
- **Publication window:** 90–31 days before 6 May 2021, i.e. 5 Feb – 5 Apr
  2021. **Capture window:** 5 Feb – 5 May 2021, ending on the eve of polling
  day, so no post-election page can be fetched.
- **Sample:** 100 article-like URLs per outlet, drawn uniformly at random
  (seed 20261007) from each outlet's capture list, one unit per URL.
- **Fetch:** live page first, then the Wayback capture. Parsing uses V1's
  `extract_html_metadata`.
- **Stages per article:** text extracted → published date inside the window
  → prefilter v1 on headline + body → V1's frozen v2 classifier
  (claude-sonnet-5) on prefilter survivors.
- **The only prompt change for Kent:** the word "Surrey" in the L3/L4
  reason-code definitions becomes "Kent". Surrey articles get the
  unmodified prompt.
- **Projection:** for each outlet, the capture-list size times the sample
  share of included articles, summed per county. A per-party figure counts
  included articles that mention the party. Wayback does not archive every
  article, so projections are **lower bounds**.

## Measures and decision

| id | measure | role |
|---|---|---|
| P1 | text-extraction success rate per outlet | engineering. Below 70% for any outlet flags the parser |
| P2 | in-window share of fetched articles | reported |
| P3 | **real prefilter removal rate** = 1 − pass share among in-window articles | reported. This is the M3 that `keyword_prefilter_v1` could not measure |
| P4 | classifier include share among prefilter survivors | reported |
| **K1** | Kent ÷ Surrey ratio of the median projected relevant articles per main party (Con, Lab, LD, Green) | **primary**: ≥ 0.5 pass · 0.2–0.5 partial · < 0.2 fail |
| K2 | Kent's absolute median per main party | reported against 10, the per-party bar carried over from the feasibility probe |

**Calibration check (not graded):** V1 found 10 usable local-outlet
articles in Surrey 2021's 90–31 day window, across all parties. If the
Surrey projection of relevant articles falls far below that, the pipeline is
missing coverage V1 found, and that will be reported.

- **Pass:** proceed to the 3–5 council pilot, using this pipeline.
- **Partial:** proceed only with outlets whose rates match Surrey's.
- **Fail:** Kent's local political coverage is too thin for council-level
  content features. Fall back to the alternatives in
  `power_v1/design_power_findings.md`.

## Known limitations, stated in advance

- 100 URLs per outlet gives coarse rates: a 10% rate has a 95% interval of
  roughly ±6 points.
- Classifier labels on Kent have no human reference. The frozen classifier's
  validation was on Surrey data, with AI-assisted labels.
- Party mention is a proxy for "would feed a party feature". V1 used LLM
  stance judgements, which this pilot does not run.

## Amendments

**A1 (2026-10-08). An expansion rule, fixed after the classification batch
ended but before any result was collected or read.**

- *Why:* with about 20 classified articles per county, K1 carries wide
  sampling error. A value near the 0.5 bar cannot separate pass from fail.
  Deciding whether to collect more data only after seeing K1 would let the
  result steer the stopping point, so the rule is fixed now.
- *Rule:* if K1 falls in **[0.3, 0.7]**, the result is **inconclusive**.
  The sample is then expanded **once**, to 300 URLs per outlet (the original
  100 plus 200 new draws with the same procedure and a new seed, 20261008),
  and the decision thresholds above are applied to the pooled sample. Outside
  [0.3, 0.7], the original thresholds apply directly, with no expansion.
- *Classification route:* the cheapest valid route is used, unchanged from
  V1: the frozen classifier via the Message Batches API (half price), on
  prefilter survivors only. Batch `msgbatch_0187ehjb3KH8prb1RTJqDXYR`, 41
  requests, all succeeded.

**A2 (2026-10-08, after reading results). No threshold is moved.** K1 is
undefined: the projected median per main party is 0 in both counties, so the
ratio is 0/0. The A1 band [0.3, 0.7] does not contain an undefined value, so
no expansion is triggered. The reasons, and why more of the same sample would
not change the substantive finding, are in `pilot_findings.md`.
