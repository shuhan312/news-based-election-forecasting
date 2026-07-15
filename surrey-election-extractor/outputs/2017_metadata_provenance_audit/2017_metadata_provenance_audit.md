# 2017 Surrey County Council Election: Metadata Provenance Audit

**Scope:** diagnosis only. No pipeline code, records, or outputs were changed or rerun.

## Verified current outcome

The completed 2017 run processed 81 official division result pages and created 377 candidate records. There are no failed extraction attempts and no failed validation checks. All 377 candidate records and all 81 division-level validation results are `Incomplete`.

| Field | Affected candidate records | Evidence-based explanation |
|---|---:|---|
| `election_name` | 377 | Individual 2017 official result pages do not publish the election name. |
| `ballot_papers_rejected` | 5 | The Reigate official page does not publish this Voting Summary value. |

`final_position` is not published in the 2017 candidate tables, but it is currently optional and does not produce the recorded incomplete status.

Sources reviewed: `config/elections.json`, `election_config.py`, `official_source.py`, `extraction.py`, `validation.py`, and the completed `outputs/2017_full_extraction/2017_validation_report.json`.

## Current completeness logic

`CandidateResultRecord` repeats election-level and division-level fields on each candidate row. Its single `REQUIRED_RECORD_FIELDS` tuple treats election metadata, division Voting Summary data, and candidate values as required for every candidate. Extraction copies each absence into `record.missing_fields` and marks that candidate `incomplete`.

Validation then imports every `record.missing_fields` item into the division-level result. Therefore one election-level absence (`election_name`) is counted once per candidate: 377 times. This is a completeness-layer and provenance issue, not an official-page parser failure.

## Correct field ownership and provenance

### Election level

| Field | Recommended primary source | Completeness treatment |
|---|---|---|
| `election_name` | Selected election configuration | Required once at election level; not required as text published on every result page. |
| `election_date` | Official result-page title | Required once at election level when needed; retain official evidence and never derive it from year. |
| `election_type` | Selected election configuration | Required once at election level with configuration provenance. |
| `authority` | Official result page | Required once at election level when published; do not assume it from the election year. |

The 2017 configuration already contains `election_name` and `election_type`. Using them must be recorded as **configuration provenance**, not represented as text published on every official result page.

### Division level

| Field | Correct source | Missing-value treatment |
|---|---|---|
| Division/ward name | Official page title, checked against discovery/index evidence | Missing or conflicting identity affects division completeness. |
| `number_of_seats` | Official `Voting Summary` | Keep an absent official value missing. Supplementary Seats metadata remains separate and must not overwrite it. |
| `electorate` | Official `Voting Summary` | Report absence once at division level. |
| `ballot_papers_issued` | Official `Voting Summary` | Report absence once at division level. |
| `ballot_papers_rejected` | Official `Voting Summary` | Leave blank if absent; Reigate is one division limitation, not five candidate failures. |
| `turnout` | Official `Voting Summary` | Report absence once at division level. |

The existing official parser already accepts summary values only from the table explicitly labelled `Voting Summary`; this source rule should be preserved.

### Candidate level

| Field | Correct source | Completeness treatment |
|---|---|---|
| Candidate name | Official candidate table | Required; do not create unsupported candidate rows. |
| Original party name | Official candidate table | Required where published; preserve exact wording. |
| Standardised party name | Separate controlled party lookup | Not required for official extraction. A missing mapping is a curation issue, not missing official result data. UKIP and Reform UK remain distinct. |
| Votes | Official candidate table | Required; never substitute zero. |
| Vote share | Official candidate table | Required if the project output requires it; do not calculate into the published field. |
| Elected status / outcome | Official candidate table | Required as the published outcome; do not separately require duplicate representations. |
| Final position | Official candidate table, if published | Keep missing when absent. Do not derive a ranking from votes unless a later, separately documented derived field is approved. |

## Answers to the audit questions

1. **Is `election_name` expected on every individual result page?** No. It is absent from all 81 examined 2017 official result pages. The configuration is the correct election-level source.
2. **Are election-level fields currently required at candidate level?** Yes. The single required-field list includes `election_name`, `election_date`, and `authority`, and their absence is copied to every candidate row.
3. **Should completeness be separate?** Yes: election metadata completeness, division/Voting Summary completeness, and candidate-result completeness.
4. **Does this match the supervisor requirements?** Yes. It preserves official values, makes provenance explicit, retains uncertainty, and avoids invented data.
5. **Is it compatible with 2013, 2021, and 2026 East/West Surrey?** Yes as a source-layer design. It makes no year, seat-count, or page-layout assumption. Each election still requires its own compatibility assessment.

## Recommended minimal future change

No code change is made by this audit. If approved, the smallest safe change is to introduce a separate immutable election-metadata record sourced from the selected configuration, then evaluate completeness at election, division, and candidate levels independently.

Candidate rows may still repeat shared values for workbook convenience, but a candidate extraction status should depend only on candidate evidence. Division summary absences should remain division-level limitations. Configuration values must carry their own provenance and must never overwrite an official value.

## Risks and controls

| Risk | Required control |
|---|---|
| Incorrect configuration value affects every joined row | Retain election ID and configuration source in audit output; validate the configuration. |
| Configuration value is mistaken for page content | Keep configuration and official-page provenance separate. |
| Candidate success hides a missing Voting Summary value | Continue reporting division-level missing fields, including Reigate rejected ballots. |
| Derived rank is mistaken for official final position | Keep `final_position` blank unless officially published. |
| Different future page layouts | Run the compatibility audit before each full extraction. |

## Recommended next step

Review this report with the supervisor. If approved, create a separate minimal implementation task for layered completeness only. It must not backfill source data, overwrite official values, or rerun an election before tests are added.
