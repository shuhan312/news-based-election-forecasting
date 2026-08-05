"""Build the party-grain table with the E5-local by-election articles admitted.

    PYTHONPATH=src .venv/bin/python -m news_features.build_feature_table_v4e5local

EXPLORATORY, post-unblinding. The 2026 holdout was unsealed on 2026-08-01, so
nothing built here can become a confirmatory result.

## What changed, and why it took a human pass

The `e5local1` extraction tranche has sat on disk since 2026-08-02 holding 29
by-election local candidates that no release admitted. The reason is recorded
in `PRODUCTION_NEWS_EVIDENCE_REGISTER.md`: the E5 classifier was validated
against human judgement at **kappa 0.4762 against a 0.600 bar and failed**, so
its verdicts could not open the gate. Every other gate on those articles was
already settled - `byelection_eligibility_decisions.csv` carries E4, E6 and E8
verdicts from `llm_v2` and a `resolution_status` of `awaiting_human_e5`.

The gate that was missing is now closed. The author judged the 39 queued rows
by hand against `news_protocol/eligibility_manual_review_codebook.md`, blind to
any prior labelling, and those verdicts are recorded in
`news_collection/byelection_eligibility_decisions_e5human_v1.csv` with
`e5_source = human`. Four rows whose stored extract is 32 characters carry
`insufficient_evidence` / `E5-NO-FULL-TEXT`, which is a mechanical consequence
of the extract rather than a judgement and is marked `mechanical`.

**No gate other than E5 was touched.** The E4, E6 and E8 verdicts are the ones
the pipeline already held. That matters: E5 needed a human because E5 failed
its validation, and the others did not.

Net effect on the by-election decision file: 627 terminal includes become 656.

## What this wrapper changes from v3party, and what it does not

Three lines, all of them scope declarations:

- the output paths (`news_feature_table_v4e5local.*`);
- `release_v2.BYELECTION_DECISIONS`, pointed at the file carrying the human
  E5 verdicts;
- `EXCLUDED_TRANCHES`, which keeps `haslemere1` and `wokingsouth1` out and now
  admits `e5local1`, because a release finally admits its articles.

Every aggregation rule, share definition, zero-cell policy, arm-reconciliation
assertion, gate threshold and the party-grain content attribution are
v3party's, untouched. Tables v1, v2 and v3party keep their own wrappers and
their own corpora; this one does not write to any of them.

## What to check in the output

The four by-elections that carried zero coverage - Caterham Valley, Guildford
South East, Hinchley Wood, Weybridge - should now carry local articles. The
expected gain is twelve (election x party) cells, because most of the admitted
Weybridge articles are fires, crashes and a burglary that name no party and so
produce no stance record. A build that shows those four elections still at zero
means the release did not admit what the decision file says it admits.
"""

from __future__ import annotations

import csv
from pathlib import Path

from src.news_collection import canonical_corpus_release_v2 as release_v2
from src.news_features import build_feature_table as frozen
from src.news_features import build_feature_table_v3party  # noqa: F401

_frozen_load_records = frozen.load_records


def configure() -> None:
    """Rebind the builder's globals to this table's lineage.

    Called at import, and callable again. Import-time-only configuration is
    not enough: Python caches modules, so a test that restores the builder's
    globals cannot get them back by re-importing this one.
    """

    # Output paths: beside the others, never overwriting.
    frozen.OUT_CSV = frozen.OUT_CSV.with_name("news_feature_table_v4e5local.csv")
    frozen.OUT_META = frozen.OUT_META.with_name(
        "news_feature_table_v4e5local_metadata.json")

    # The decision file carrying the human E5 pass. Pointing the v2 release
    # at it is the whole change: the same selection machinery now sees 656
    # terminal by-election includes instead of 627.
    release_v2.BYELECTION_DECISIONS = Path(
        "news_collection/byelection_eligibility_decisions_e5human_v1.csv"
    ).resolve()

    # `e5local1` leaves the exclusion set because a release now admits its
    # articles. The two single-contest case-study tranches stay out: no
    # release admits those, and loading them would trip the corpus assertion.
    frozen.EXCLUDED_TRANCHES = {"haslemere1", "wokingsouth1"}

    frozen.load_records = load_records


def _decisions_index() -> dict[str, str]:
    """Every by-election decision, article id -> overall decision."""

    with release_v2.BYELECTION_DECISIONS.open(encoding="utf-8", newline="") as f:
        return {row["article_id"]: row["overall_decision"]
                for row in csv.DictReader(f)}


def load_records() -> tuple[dict, dict]:
    """The frozen loader, minus records for articles the release did not admit.

    Why this is needed here and nowhere else. Every other tranche was
    extracted AFTER its eligibility was settled, so its records are a subset
    of the release by construction. `e5local1` was extracted on 2026-08-02
    while its E5 gate was still open, so it holds 29 articles of which the
    human pass admits 28: one is `needs_second_review` /
    `E5-BORDERLINE-PLACE-MENTION` and correctly stays out.

    The builder's corpus assertion exists to stop articles from ANOTHER
    release entering the table, and that guard is kept intact. What is dropped
    here is only an article this release's own decision file names and does
    not admit - the assertion below re-states that, so an article from
    anywhere else still reaches the frozen guard and still stops the build.
    """

    records, provenance = _frozen_load_records()
    decisions = _decisions_index()
    dropped: set[str] = set()
    for layer, by_article in records.items():
        for article_id in list(by_article):
            verdict = decisions.get(article_id)
            if verdict is not None and verdict != "include":
                del by_article[article_id]
                dropped.add(article_id)
    assert all(decisions.get(a, "include") != "include" for a in dropped), (
        "the admission filter dropped an article the decision file admits"
    )
    if dropped:
        print(f"  admission filter dropped {len(dropped)} unadmitted "
              f"article(s): {sorted(dropped)}")
    return records, provenance


configure()


def main() -> None:
    frozen.main()


if __name__ == "__main__":
    main()
