# News Scope Classification - Error Analysis

Phase 7, Step 3. Companion to `news_scope_audit.md`. This file
walks the cases where the five-way scheme is under strain, so the
feature stage inherits known weaknesses explicitly instead of
discovering them later.

## 1. Difficult cases: hard label vs continuous scores

Seven articles carry BOTH relevance scores >= 0.4 but only some of
them classify as mixed_local_national. Example pattern: a Guardian
national-politics piece with a substantial Surrey case study scores
local 0.4 / national 0.8 and labels national_political - the label
keeps the dominant scope, the local echo survives only in the
score. This is not a defect of this layer (it carries the frozen
judgement faithfully) but a known lossiness of ANY single-label
scheme. Mitigation, already decided (D2): downstream features use
the continuous scores as weights; the hard label is for stratified
reporting.

## 2. Mixed articles (6)

The mixed_local_national set is the analytically interesting
national-to-local transmission channel (e.g. national party
turmoil framed through Surrey campaigning). At pilot scale it is
6 articles - enough to validate the category exists and extracts
cleanly, not enough to model. Recorded expectation (D5): if the
full corpus keeps this class rare, the national-momentum-to-local-
conversion question is power-limited and will be treated
descriptively.

## 3. Uncertain geography (2 + 1)

* 2 articles have no valid frozen relevance record (one
  quarantined JSON, one missing output) - classified "uncertain",
  flagged, no evidence fabricated. They rejoin via the post-full-
  scale adjudication pass, not via re-guessing here.
* 1 article classifies "regional" - a single South East England
  case. The category is legitimate but near-empty at pilot scale;
  at full scale, if it stays this thin it will be reported jointly
  with national_political rather than modelled separately.

## 4. Possible classification errors (inherited, quantified)

The frozen Step 8 layer this step carries was pilot-audited at
65/67 valid with machine-vs-machine cross-layer agreement in the
0.6-0.8 band, and its low-confidence records are flagged (4 here,
plus the 2 uncertain). The most likely genuine error mode is
mixed-vs-national boundary placement when the Surrey element is a
brief peg rather than substance - exactly the cases in section 1.
These 6 flagged records are in the human review pool; the D4
50-article validation gate (post full-corpus) covers geographic
scope as one of its six fields, so the error rate of this layer
gets an independent human number before any model consumes it.

## 5. What this layer does NOT hand downstream

No aggregation, no ward-party features, no recency weighting, no
embeddings, no models. The layer hands exactly: one label + two
scores + evidence + confidence + preserved join keys (election,
ward links, party links) per article.
