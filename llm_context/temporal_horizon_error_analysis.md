# Temporal horizon - error analysis (Phase 6 Step 9)

Nine error lines across 8 of 67 articles; every one caught by
validation. Nothing reached usable data unchecked.

## 1. Misplaced fields inside temporal_mechanism - 5 records

The dominant slip: story_type (and once a stray note, once a
trailing-space key "rationale ") written INSIDE temporal_mechanism
instead of at the record root. additionalProperties: false rejected
all of them. Prompt nit for the full-scale run: one line stating
"story_type is a ROOT field, temporal_mechanism holds exactly five
keys". No vocabulary invention - purely placement.

## 2. H6 - none_political with a definite horizon - 2 records

Two colour pieces got story_type none_political yet a definite
horizon without an explanatory note. The rule held: a non-political
story has no political persistence to classify. These are the rule
working, not a rule gap.

## 3. Under-flagged low confidence - 1 record (H2)

A 0.1-confidence horizon without the flagged status - forced to
review by the rule. Notably 0.1 is the lowest confidence any layer
has produced; the article evidently resists temporal judgement, and
the review pool is where it belongs.

## Non-errors worth recording

- Zero H1 violations - the first layer with NO fabricated quotes at
  all (the horizon evidence is typically a distinctive temporal
  sentence, easy to copy exactly);
- zero H4 violations: Reform temporal characters only ever appeared
  with evidence under applicable=true;
- the deterministic half produced zero errors by construction and
  its boundary behaviour is pinned by twelve explicit test cases;
- the window-by-horizon cross-table shows horizons varying freely
  within windows - empirical confirmation that publication distance
  did not leak into the content judgement.
