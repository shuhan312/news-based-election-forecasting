# Narrative framing detection - error analysis (Phase 6 Step 5)

Three validation errors in 67 articles, plus one taxonomy-boundary
observation from manual review. Nothing reached usable data
unchecked.

## 1. Non-verbatim quotes - 2 records (F1)

Two frames cited lightly reconstructed passages (a Miliband lessons
sentence; a Davey local-issues sentence). Caught by string-matching
and quarantined - the familiar ~3% residual seen in every layer.
The affected records sit in the review pool; no new mitigation
beyond the existing hardened rule.

## 2. Primary frame repeated in secondaries - 1 record (F3)

One record listed government_performance as both primary and
secondary. Structural discipline caught it; a one-line prompt
reminder ("the primary category must not reappear in
secondary_frames") folds into the full-scale prompt.

## 3. Taxonomy-boundary observation (not an error):
   momentum vs emergence for insurgent parties

For UKIP/Reform-type stories, challenger_emergence (a rising force
arrives) and national_political_momentum (the national tide reading)
often co-occur and can blur. The pilot handled it well (the
Eastleigh record correctly carries both as distinct frames with
separate evidence), but for full scale the human-review protocol
gains a tie-breaker: emergence is about the CHALLENGER's arrival
and organisational reality; momentum is about a party's fortunes as
a national trend reading. An article doing both carries both -
primary goes to whichever the headline/lede leads with (same
convention as the Step 3 adjudication rules).

## Non-errors worth recording

- ZERO uses of "other" across 234 frames - the 16-category taxonomy
  covered the entire sample; no taxonomy extension is needed for
  full scale on current evidence;
- zero invented categories, zero F4 violations;
- benefits/damages left null in most frames (57 and 112 of 234
  named respectively) - the model claims a favoured or harmed party
  only where the article supports it;
- 13 honest empty records passed correctly as partial-with-note;
- all low-confidence frames landed in review-flagged records (F2);
- frames are measurably distinct from stance and issues (78% mapped
  overlap with the coarse pilot frames, but with far finer
  narrative differentiation on manual reading).
