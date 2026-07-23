# Article Eligibility Manual Review Codebook

Companion to `article_eligibility_rules.md` (the frozen rules
document) and `src/news_collection/manual_review_schema.py` (the
machine-checkable version of everything in this file - the two are
required to stay in exact agreement; `REASON_CODES` in that module is
the single source of truth if this document and the code ever
disagree, and this document should be corrected to match, not the
other way round).

This codebook does not redefine I1-I6 or E1-E10. It operationalises
the four rules `assess_eligibility.py` explicitly refuses to decide by
script - **E4** (result leakage), **E5**'s L/N relevance test (the
part not already covered by the Guardian/SerpAPI relevance-flag
audits), **E6** (Reform UK disambiguation), and **E8** (genuine
editorial content) - into criteria a human reviewer applies the same
way every time.

## How to use this codebook

For every one of the four rules, a reviewer reads the article's
stored extract (or the live/archived page if the extract is thin) and
records **one decision** from the closed set `include / exclude /
needs_second_review / insufficient_evidence / not_applicable` (E6
only), a **reason code** from that rule's table below, a **quoted
supporting_text** fragment (unless the decision is
`insufficient_evidence`, whose whole point is that no fragment could
be found), and a **confidence level** (`high / medium / low`) for
`include`/`exclude` decisions.

No rule may be judged from the headline alone if the extract is
available - and no rule may consider the article's stance, tone, or
which party or candidate it favours (article_eligibility_rules.md §0).

---

## E4 - Result leakage

**Protects against:** an article that reports, previews-while-citing,
or reacts to the election's outcome, exit information, or count
surviving in the corpus on its date alone. A mis-dated results article
must never count as pre-election evidence (this is the exact failure
mode the BBC 2013 pilot case surfaced during date resolution - a
results-day article whose metadata claimed a pre-poll date).

| Decision | Reason code | When it applies |
|---|---|---|
| include | `E4-CLEAR` | Nothing in the text reports, cites, or reacts to a declared result, count, or exit poll for **this** election. |
| exclude | `E4-LEAK-RESULT` | States who won, lost, or by how much for this election. |
| exclude | `E4-LEAK-COUNT` | Describes the count as under way or complete (turnout announced, ballots being counted, declaration made). |
| exclude | `E4-LEAK-EXIT-POLL` | Cites an exit poll or other unofficial early result for this election. |
| exclude | `E4-LEAK-PREVIEW-CITING-RESULT` | Framed as a preview/forecast but nonetheless cites the actual result (e.g. republished or updated after polling day without a new dateline). |
| needs_second_review | `E4-AMBIGUOUS-TENSE` | Verb tense or phrasing makes it genuinely unclear whether the count had happened yet (the BBC 2013 pattern - resolve the same way that case was resolved: look for independent corroboration of timing, never guess). |
| needs_second_review | `E4-POSSIBLE-POST-PUBLICATION-EDIT` | The stored text shows signs of having been updated after first publication (an "updated at" marker, a byline correction note) and the update may have added result information. |
| insufficient_evidence | `E4-NO-FULL-TEXT` | The stored extract is too short to judge either way (typically `content.has_full_text=false` or a very low `word_count`). |

**Note on "this election" vs. other elections:** an article about a
*different* contest (e.g. a 2015 general election piece inside the
2017 SCC window) is not an E4 concern purely for reporting that
contest's result - see article_eligibility_rules.md §5 edge case 6.
E4 only fires for the specific election this record was
`discovered_for_election` under.

---

## E5 - Relevance (the L/N test, remaining cases only)

**Protects against:** content with no genuine connection to the local
division/ward being sampled, or (for the national arm) to UK
politics/policy relevant to this project. Two mechanical audits
already cover a known subset of E5 failures automatically -
`guardian_geographic_relevance_flags.csv` (non-UK Guardian editions)
and `serpapi_domain_relevance_flags.csv` (off-topic domain
collisions, e.g. a US kennel club PDF). **This codebook covers
everything those two audits do not** - the actual L/N content test
from article_eligibility_rules.md §1.

| Decision | Reason code | When it applies |
|---|---|---|
| include | `E5-L1-PLACE` | Names the sampled division/ward, or a town/village/place within it. |
| include | `E5-L2-CANDIDATE` | Names a candidate or sitting councillor for it, in a political/civic context (verify against the candidate standardisation table - not an unrelated namesake). |
| include | `E5-L3-COUNCIL-ISSUE` | Concerns a Surrey council decision/service/issue identifiably affecting that division (a road scheme, school, development). |
| include | `E5-L4-COUNTY-WIDE` | Surrey-wide political coverage (county control, county-wide campaign coverage) - link at county scope. |
| include | `E5-N1-PARTY-POLITICS` | UK national politics involving a party contesting the election (leadership, government/opposition performance, scandal, polling, voter switching). |
| include | `E5-N2-POLICY-ISSUE` | A national policy issue on the supervisor's list (cost of living, tax, immigration, NHS/public services, local government funding). |
| include | `E5-N3-REFORM-GROWTH` | Reform UK's national growth or its relationship with the Conservatives/Labour/Lib Dems (or the UKIP equivalent for 2013/2017). |
| exclude | `E5-NO-L-OR-N-RULE-MET` | Fails every L-rule and every N-rule (sport, entertainment, or commercial content that merely mentions a place name - article_eligibility_rules.md's own E5 example). |
| needs_second_review | `E5-BORDERLINE-PLACE-MENTION` | A place name appears but only incidentally (e.g. a dateline or a passing reference), and it's genuinely unclear whether L1-L3 are actually satisfied. |
| needs_second_review | `E5-BORDERLINE-POLICY-RELEVANCE` | Touches a policy area but it's unclear whether it's really on the supervisor's N2 list or a related-but-different topic. |
| insufficient_evidence | `E5-NO-FULL-TEXT` | Extract too short to apply any L/N test. |

---

## E6 - Reform UK disambiguation

**Protects against:** counting a hit for "reform" in its ordinary
English sense (planning reform, NHS reform, electoral reform) as if it
were about Reform UK. Manual disambiguation is mandatory for **every**
record whose originating search query mentioned "reform" - this is a
named supervisor requirement in article_eligibility_rules.md, not a
discretionary check (`needs_reform_disambiguation=yes` in
`eligibility_assessment.csv` marks exactly this set).

| Decision | Reason code | When it applies |
|---|---|---|
| include | `E6-PARTY-CONFIRMED` | The text unambiguously refers to the political party Reform UK (or a named Reform UK figure/candidate). |
| exclude | `E6-GENERIC-WORD-USE` | "Reform" is used in its ordinary sense with no connection to the party (planning reform, NHS reform, electoral reform, etc.). |
| needs_second_review | `E6-AMBIGUOUS-USAGE` | Genuinely unclear which sense is meant (e.g. a headline pun, or a policy-reform piece that also happens to mention the party elsewhere without clarity on emphasis). |
| insufficient_evidence | `E6-NO-FULL-TEXT` | Extract too short to disambiguate. |
| not_applicable | `E6-NOT-REFORM-FLAGGED` | The record never matched a Reform-related query - there is nothing to disambiguate. Pre-filled automatically by `build_manual_review_sample.py`, never chosen by a reviewer. |

---

## E8 - Genuine editorial content

**Protects against:** adverts, listings, category/tag/search-result
pages, and bare notices counting as "coverage" (article_eligibility_
rules.md I4/E8). This is a format/content-type question, never a
quality or stance judgement.

| Decision | Reason code | When it applies |
|---|---|---|
| include | `E8-EDITORIAL-CONFIRMED` | A news report, analysis, opinion piece, editorial, letter, interview, profile, or published press release (I4's own list). |
| exclude | `E8-LISTING-OR-INDEX-PAGE` | A category, tag, index, or search-results page, not a single article. |
| exclude | `E8-ADVERT-OR-COMMERCIAL` | An advertisement or purely commercial listing. |
| exclude | `E8-NOTICE-ONLY` | A bare procedural notice with no editorial content (distinct from a council/party press release, which IS eligible per edge case 4 when genuinely published). |
| needs_second_review | `E8-UNCLEAR-FORMAT` | Doesn't clearly fit either category (a live-blog fragment, a data table, a mixed listing-plus-commentary page). |
| insufficient_evidence | `E8-NO-FULL-TEXT` | Extract too short to tell what kind of page this is. |

---

## Reviewer confidence levels

Recorded per rule, for `include`/`exclude` decisions only (a
`needs_second_review` or `insufficient_evidence` decision already
states its own uncertainty and does not need a separate confidence
value):

| Level | Meaning |
|---|---|
| `high` | The supporting_text alone settles the question; a second reviewer would very likely reach the same decision from the same quote. |
| `medium` | The decision is reasonable but rests on some inference beyond the literal text (e.g. inferring the sampled division from a named village, or inferring "clear of leakage" from an absence of certain phrasing rather than a positive statement of timing). |
| `low` | The reviewer is genuinely unsure but is making a decision rather than escalating - use sparingly; when in real doubt, `needs_second_review` is almost always the more honest choice than a low-confidence `include`/`exclude`. |

## Overall decision

The whole-article decision is never set by hand - it is derived
mechanically from the four per-rule decisions by
`manual_review_schema.derive_overall_decision()`, with the same
precedence article_eligibility_rules.md's own check order implies:
**any `exclude` wins outright; otherwise any open `needs_second_review`
blocks a final `include`; otherwise any `insufficient_evidence` blocks
it; only when every applicable rule (E6 counts only when it isn't
`not_applicable`) resolves to `include` does the article count as
`include`.** This function is a pure, tested function
(`tests/test_manual_review.py`) precisely so the derivation can never
silently drift from this table.
