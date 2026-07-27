# Issue-layer decisions after Step 3 (findings and fixes)

Two findings came out of the Step 3 pilot audit. This file records
what was found, what was decided, and how each decision is
implemented - so the reasoning is auditable and the Friday
supervisor meeting can ratify rather than reconstruct it.

## Finding 1 - two issue judgements per article (61% agreement)

The same 67 articles carried issues twice: once inside the Step 2
full-schema extraction, once from the Step 3 focused layer.
Primary-issue agreement was 61% (72% code overlap) - not a defect
(half the gap is the focused layer's stricter never-force-a-code
rule judging None, the rest adjacent-code ambiguity), but two
answers to one question cannot both feed the models.

### Decision 1a - the focused issue layer is authoritative

For all downstream use (features, workbook tabs, analysis), issues
come from the Step 3 focused layer ONLY. The full-schema issues
section is demoted to cross-check material and will be REMOVED from
the full-corpus extraction prompt (saves tokens, removes the
duplication at source). One question, one answer, one audit trail.

### Decision 1b - adjacent-code adjudication rules

For the human-review protocol at full scale, the pilot's high-
friction code pairs get explicit tie-breakers:

1. candidate_party_conduct vs crime_policing: a politician's own
   misconduct is CONDUCT, even when criminal; choose crime_policing
   only when the article's subject is policing/crime as an issue.
2. candidate_party_conduct vs scandal: scandal requires an affair
   of scale (investigations, resignations, sustained coverage);
   isolated misbehaviour is conduct.
3. new_party_emergence vs voter_switching: emergence is about the
   PARTY's rise (organisation, candidates, credibility); switching
   is about VOTERS moving. An article doing both genuinely carries
   both codes - primary goes to whichever the headline/lede leads
   with.
4. council_finance vs council_tax: council_tax only when the tax
   itself (level, rise, banding) is the subject; budgets, cuts and
   funding pressure are council_finance.
5. None vs other: None = no political issue at all (letters,
   colour pieces); other = a real political issue that fits no code
   (requires issue_other_label).

The machine self-agreement of 61% is recorded as the calibration
context for the human-vs-machine validation gate (expectations set
against ~0.6, consistent with the classification pipeline's kappa
threshold, not against 90%).

## Finding 2 - national articles uncodable under the local taxonomy

23 of 67 records had no primary issue, concentrated in the national
arm: the approved taxonomy is local-issue oriented, so national
politics coverage (leadership, government performance, national
economy) had no code. That would blank out the local-vs-national
issue-composition comparison in the research design.

### Decision 2 - taxonomy v1.3 adds two national codes

`national_politics` and `national_economy` (definitions in
`issue_taxonomy_v1.3.json`), chosen to mirror the supervisor's own
national search topics; immigration, healthcare, scandal, polling
and switching already had codes. Versioning discipline as always:
v1.1/v1.2 records stay valid under their own stamps; new rule S7
forbids national codes under pre-v1.3 stamps; the classification
prompt moves to issue-cls-prompt-v1.1 stamping issues-v1.3.

**Status: adopted** (decision D1, phase6_research_decisions_v1.md).
The extension matches the project brief's own national search-topic
list; it is documented for the supervisor's information and remains
reversible - old records validate under their own stamps and
nothing already produced depends on v1.3.

### Verification

The pilot articles that previously classified as None/other were
re-run under prompt v1.1 / taxonomy v1.3 as a targeted check that
the new codes activate correctly - results in
`issue_classification_audit.md` (addendum) and the re-run outputs
file.
