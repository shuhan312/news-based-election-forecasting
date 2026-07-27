# Local / national relevance - error analysis (Phase 6 Step 8)

Two errors in 67 articles - the cleanest layer of the eight.

## 1. Unparseable JSON - 1 record

A trailing comma before the closing brace. Caught at parse time;
the article sits in the retry pool for the full-scale run (where
single-record retries are routine). No pattern - first trailing
comma in eight layers.

## 2. Under-flagged low confidence - 1 record (G2)

A 0.4-confidence Reform addendum without the flagged status; the
rule forced it to review, as designed.

## Non-errors worth recording

- Zero G3 violations: every ward_mentioned flag had its named ward
  and vice versa - no unsupported geographic assumption anywhere;
- zero G4 violations: scope labels and dual scores told one story
  in all 65 valid records;
- zero G5 violations: the Reform connection rule (both elements
  required) never had to fire against a false connector - and the
  one genuine connector article passed it legitimately;
- the arm-vs-scope divergence (8 local-arm articles that are
  nationally scoped) is a FINDING about the collection channels,
  not an extraction error - recorded in the audit for the modelling
  design.
