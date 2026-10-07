# Keyword prefilter: findings

**2026-10-07.** The v0 criteria were committed first (f092e5e). v1 was
declared final on dev before test was run (81e86ec, amendment A1). Test was
run once: `prefilter_v1_test.json`.

## Verdict: adopt v1 for party features ("M1 passes, M2 fails")

| measure | bar | dev (v1) | **test (v1, run once)** |
|---|---|---|---|
| M1 feature recall | ≥ 0.97 | 1.000 (958/958) | **1.000 (987/987)** [1.000, 1.000] |
| M1, local arm | — | 1.000 (52) | 1.000 (56) |
| M2 relevance recall (local) | ≥ 0.90 | 0.798 | **0.633** [0.517, 0.750] |
| M3 removal of local irrelevant | none | 0.044 | 0.028 |

All 1,945 V1 articles that fed party features pass. Across both splits, the
filter loses no article V2's party-level features depend on.

## What it does lose

Every one of the 42 relevance misses (20 dev, 22 test) is a human include
under L1 ("names a place") with no political content. They are crime,
collisions, court cases, missing persons, fires and animal stories, e.g. "A25
Shere Road crash: Motorcyclist dies following collision with two cars in
Gomshall". None names a party. The lower test figure (0.633 vs 0.798) reflects
how many such stories fell into each half, not a different kind of miss.

This is a scope decision, not a defect. V2's local news layer will measure
**political coverage**, not "any news naming a Surrey place". V1's L1 rule is
broader than anything a party-level feature can use. Reports of local
coverage volume must say which definition they use.

## What is not yet known

M3 is near zero because V1's labelled excludes were retrieved by political
keyword search, so they almost all contain the filter's terms. The filter's
real benefit, the share of an unfiltered outlet dump it removes, can only be
measured on outlet-first output. That is the next step.

## Engineering note for collection code

Call the filter on `keyword_prefilter.article_text(headline, body)`, never on
the body alone. One feature article named its party only in the headline.
