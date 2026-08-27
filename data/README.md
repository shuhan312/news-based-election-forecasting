# `data/` — election reference tables (Layer 1A)

The small, canonical election-result reference tables the whole pipeline
aligns against. Everything committed here is either converted
deterministically from the frozen extractor workbooks or fetched from an
official/public source by a script in `src/`; the raw workbooks, scraped
pages and the news corpus live outside Git (OneDrive / `data/raw/`,
git-ignored) per the large-file rule.

## Complete file index

| File | Produced by | What it is |
| --- | --- | --- |
| `elections/2013_scc_results.csv` | `src/convert_2013_extractor_output.py` | the 2013 Surrey County Council results, converted from the validated extractor workbook |
| `elections/2013_conversion_log.csv` | same | the per-row conversion log for that build |
| `elections/2013_wikipedia_turnout_audit.csv` | `src/add_2013_wikipedia_turnout.py` | the audited Wikipedia fill for the 2013 turnout gap the official page lacks |
| `elections/2026_east_surrey_results.csv`, `elections/2026_west_surrey_results.csv` | `src/convert_2026_extractor_output.py` (collected by `src/fetch_2026_surrey_results.py`) | the separate East/West Surrey 2026 candidate results |
| `elections/2026_conversion_log.csv` | same | the per-row conversion log for the 2026 build |
| `elections/results_2017_2024.csv` | `src/fetch_election_results.py` | ward-level results extracted from the calendar's Wikipedia pages |
| `elections/official_scc_candidate_results_test.csv` | `src/fetch_official_scc_results.py` | the official-page candidate-results extraction check |
| `elections/election_calendar.csv` | `src/build_election_calendar.py` | the Surrey election calendar the news windows align against |
| `elections/ward_winners.csv` | derived from the results tables | 2017/2021 winner and margin per ward — an input to the pre-registered division sample |
| `elections/ward_party_results.csv` | derived from the results tables | party-level ward results used by the early aggregation path |
| `elections/candidate_name_standardisation.csv`, `elections/party_name_standardisation.csv` | `src/build_name_standardisation.py` | the reviewed name-standardisation tables; Reform UK and UKIP are never merged |
| `elections/turnout_audit.csv` | `src/audit_turnout.py` | the turnout audit over the cached election tables |

## Reproduction

The `convert_*` builds are deterministic from the frozen extractor
workbooks; the `fetch_*`, calendar and Wikipedia scripts read external
sources, so re-running them yields a fresh snapshot rather than a
byte-identical copy of the committed table — the committed versions are the
frozen reference. Run any script from the repository root; see
`src/README.md` ("Top-level collection scripts") for the grouped commands
and `surrey-election-extractor/README.md` for the workbook lineage upstream
of the `convert_*` steps.
