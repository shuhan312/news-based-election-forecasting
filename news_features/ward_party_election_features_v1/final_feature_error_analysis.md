# Ward-party-election feature table: error analysis

What is thin here, stated before anything is fitted on it.

## Reform UK

- Reform rows in the table: **172**
- of those, in the historical training split: **8**
- of those, carrying any news feature: **8**

Reform UK was renamed from the Brexit Party in January 2021 and did not exist for the 2013 or 2017 elections, so its training-period presence is small for reasons no amount of collection can change. Any Reform-specific estimate has to be quoted with this count.

## Did-not-contest rows

- 4710 rows record a party that did not stand. Their vote-share target is empty, not zero.
- A model fitted with those rows included, and their target read as zero, would learn that every party polls nothing almost everywhere. They are present so the absence is visible, and must be filtered by `party_contested` before fitting rather than left to a null-handling default.

## Window horizon

The principal windows reach 30 days. The corpus was collected on a 180-day horizon, so most collected articles fall outside the principal windows and enter only the retained sensitivity layer. That is a consequence of the window specification, not of the collection.

## Coverage states

`coverage__` columns carry the distinction between no news found, an archive that could not be searched, and a stage still pending. A model that treats a null news feature as zero coverage will conflate all three. The indicators exist so it does not have to.

## The table is wider than it is long, and cannot be fitted as it stands

12,091 columns against 6,323 rows. Any estimator handed the table whole would fit it perfectly and generalise not at all, so a feature selection step is required before anything is trained. The views narrow it - the local view is about 2,700 columns - but not enough.

The width is the product of three counts, all of which the specification asks for: 225 news features, six windows, and nine blocks. Two of those nine are a decision taken here rather than required - splitting each arm into coverage that names a party and coverage that names none - which roughly doubles the width. The split is worth keeping (party-agnostic local coverage reaches 552 columns where party-named coverage reaches 6) but its cost should be stated rather than absorbed.

## Association, not causation

Nothing in this table supports a causal claim. A news feature that predicts a vote share describes an association within this historical sample; it does not establish that the coverage moved anyone's vote.
