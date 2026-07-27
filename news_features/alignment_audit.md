# Article-to-Entity Alignment Audit

Phase 7, Step 1. Alignment version:
`article-entity-alignment-v1.0-2026-07-27`
Input: frozen context layer `context-cards-v1.0-pilot67-2026-07-27`
(sha256-verified against the version manifest before aligning;
byte-untouched). Official tables: `data/elections/` party and
candidate standardisation registries, per-election results files,
election calendar.

## Headline numbers

404 alignment records over 67 articles (all original article IDs
preserved). Method: exact match after conservative normalisation
only - no fuzzy matching, no geographic inference, no candidate
identity inference. Unresolved is a recorded outcome, not a failure
state.

| alignment type | records | unresolved |
|---|---|---|
| election | 67 | 0 |
| party | 151 | 28 |
| ward | 57 | 8 |
| town_reference | 67 | 67 (by design) |
| borough | 21 | 3 |
| county | 19 | 0 |
| candidate | 22 | 18 |

Matching methods: collection_window 67, party_registry_exact 123,
exact_ward_mention 45, council_area 37, candidate_location 4,
candidate_registry_exact 4, town_location_reference 67,
unresolved 57.

## Election alignment - 67/67

Every article links to exactly one election through its collection
window (the election_id carried since Phase 3), corroborated by the
frozen deterministic temporal layer's polling date (the runner
raises on any mismatch; none occurred). Elections: SCC-2013-05 (16),
SCC-2017-05 (16), SCC-2021-05 (16), ESWS-2026-05 (19).

## Party linkage - 45/67 articles carry >=1 resolved party link

123 resolved links to 8 registry parties: Conservative 37,
Labour 37, Liberal Democrats 18, UK Independence Party 12,
Reform UK 11, Green 6, Guildford Greenbelt Group 1, Residents for
Guildford and Villages 1. Grammatical variants ('Conservatives',
'Labour Party', 'Ukip', 'Greens', ...) resolve through an explicit
synonym table in `alignment.py`; every mention also keeps its
name-as-published and its role_in_article (which frozen layer said
what about it).

28 unresolved party mentions are all correctly outside the Surrey
registry: national parties that never contested these elections
(SNP, Plaid Cymru, Brexit Party, Republican Party, Danish Social
Democrats) and composite political actors the extraction layer
legitimately targeted but which are not parties ('Conservative
government', 'Rebel Tory backbenchers', 'Jeremy Corbyn / Labour
leadership'). These remain available to feature engineering as
national-context actors; they are simply not Surrey party links.

## Ward linkage - concentrated in guide articles (a real finding)

49 resolved ward links, but only 2 articles carry them: a
SurreyLive 2026 every-candidate guide (43 wards) and a Guildford
Dragon 2021 division guide (6 divisions). Ordinary coverage names
towns, not wards: 67 town/village references across the corpus,
kept as references and never promoted to wards (boundary rule - no
town-to-ward gazetteer inference). Implication for the research
design, recorded early: ward-level news features will be sparse and
guide-article-driven; borough (18 resolved) and county (19) levels
are where most local geographic signal lives. 8 unresolved ward
mentions are borough-council wards or descriptive names absent from
the county/unitary ward lists ('North Ward (Shere and Gomshall)') -
correctly left unlinked.

## Candidate linkage - 4 resolved, 18 unresolved, 0 ambiguous

Resolved (exact registry match): Fiona Davidson, Fiona White,
Sallie Barker, Sue Hackman - each also yields a candidate_location
ward link where their official results row places them. The 18
unresolved names are overwhelmingly national politicians (Jeremy
Hunt, Dominic Raab, Philip Hammond, Ed Davey, Nadine Dorries ...)
mentioned as MPs, not as candidates in these council elections -
zero-match against the registry, recorded without inference. No
name matched multiple registry candidates, so the ambiguity path
(built and tested) fired zero times on the pilot.

## Ambiguous cases

None at pilot scale: every match was unique or absent. The
ambiguous_multiple_registry_matches outcome exists in code and
tests for the full corpus, where same-name collisions across 694
registry candidates become likely.

## Reproducibility and integrity

Rebuilding from unchanged inputs is byte-identical (tested); the
frozen context layer's sha256 is checked before aligning and
re-checked by the test suite after; every linked ward/party/
candidate ID is verified to exist in the official tables; duplicate
links are structurally impossible (merge on identical keys, tested).
14 alignment tests pass; full suite 509.
