# 2013 Runnymede Archived Declaration Audit

## Scope

This read-only audit reviewed six archived Runnymede Borough Council official
declaration pages for the 2 May 2013 Surrey County Council election:
Addlestone, Chertsey, Egham, Englefield Green, Foxhills, Thorpe & Virginia
Water, and Woodham and New Haw.

## Sources reviewed

- [Runnymede 2013 County Council results index (archived)](https://web.archive.org/web/20130506043742id_/http://www.runnymede.gov.uk:80/portal/site/elections/CCE2013_results)
- [Addlestone declaration](https://web.archive.org/web/20130507085342id_/http://www.runnymede.gov.uk:80/portal/site/elections/Addlestone_results/)
- [Chertsey declaration](https://web.archive.org/web/20130507085346id_/http://www.runnymede.gov.uk:80/portal/site/elections/Chertsey_results/)
- [Egham declaration](https://web.archive.org/web/20130507085353id_/http://www.runnymede.gov.uk:80/portal/site/elections/Egham_results/)
- [Englefield Green declaration](https://web.archive.org/web/20130506043826id_/http://www.runnymede.gov.uk:80/portal/site/elections/Englefield_results)
- [Foxhills, Thorpe & Virginia Water declaration](https://web.archive.org/web/20130507085402id_/http://www.runnymede.gov.uk:80/portal/site/elections/FoxhillsThVw_results/)
- [Woodham and New Haw declaration](https://web.archive.org/web/20130507085407id_/http://www.runnymede.gov.uk:80/portal/site/elections/Woodham_NH_results/)

## Findings

Each page is a named official declaration and its candidate-vote list agrees
with the corresponding Surrey County Council official result page. The pages
publish rejected-ballot categories and (apart from a display anomaly noted
below) percentage turnout. They do **not** publish a field named `Ballot Papers
Issued`, so no Runnymede value is added as
`secondary_division_ballot_papers_issued`.

The Foxhills declaration displays `2917` beside the label `Percentage turnout`.
The page does not state that this number is a ballot-paper count, and therefore
it is not interpreted or integrated as either turnout or issued ballot papers.
The Chertsey rejection-category rows also do not provide a usable stated total.
Neither archived-page rejection display is used as a calculation input.

## Derived-layer boundary

Separately, every audited 2013 Surrey result page publishes `total_votes` and
`rejected_ballots`. The project derives `derived_ballot_papers_issued` only
from those two values on the same Surrey official page when that page also
explicitly publishes `Seats = 1`, under the reviewed formula `total_votes +
rejected_ballots`. This is not a value published by Runnymede, does not
populate Surrey's official `ballot_papers_issued` field, and does not change
completeness.
