"""Split news features into the arms the brief asks to be compared separately.

The supervisor's original email sets the comparison out explicitly:

    1. No-news electoral baseline
    2. Local-news model
    3. National-news model
    4. Combined national and local-news model
    5. Full electoral and news model

    "This will tell us whether local or national news adds the most predictive
     value and whether they influence different aspects of voting behaviour."

and states the hypothesis the split exists to test:

    "Can national news reveal the emergence of Reform UK as a wider political
     force, while local news identifies the specific Surrey wards where that
     momentum is most likely to convert into votes or seats?"

That is two different jobs for two different kinds of coverage, so the two
must never be pooled into a single "news" feature block. Pooling them would
answer neither question: a combined coefficient cannot say whether the signal
came from national momentum or from local conversion.

The arms are not symmetric
--------------------------
A **local** article attaches to a division. A **national** article attaches to
a party, an election and a time window - the brief is explicit that national
articles are "stored once and linked to the relevant party, election and time
period, rather than copied separately into every Surrey ward".

So a national feature is constant across the divisions of one election but
varies by party and by window. That is a real signal as long as the model has
enough elections and parties to separate it from election identity; it is not
a defect, but it does mean the national arm needs breadth in elections where
the local arm needs breadth in divisions. The two arms therefore fail in
different ways, and a comparison that reported only a pooled result would hide
which one had failed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

# The brief's five-way article classification, mapped onto the values the
# extraction pipeline actually produces. Kept as an explicit mapping rather
# than a substring test: "national_political" and "mixed_local_national" both
# contain "national", and treating the second as national would quietly move
# every mixed article into the national arm.
SCOPE_TO_ARM: dict[str, str] = {
    "ward_specific_local": "local",
    "surrey_wide_local": "local",
    "regional": "regional",
    "national_political": "national",
    "mixed_local_national": "mixed",
    "uncertain": "uncertain",
}

# Which scopes each arm draws on.
#
# `mixed` counts towards both arms deliberately. An article that is genuinely
# about a national issue with local consequences is evidence for both
# mechanisms, and assigning it to one would understate whichever it was taken
# from. The consequence is that local + national > combined in article counts,
# which is why the combined arm is built from the union of the underlying
# articles rather than by adding the two feature blocks together.
ARM_SCOPES: dict[str, frozenset[str]] = {
    "local": frozenset({"ward_specific_local", "surrey_wide_local", "mixed_local_national"}),
    "national": frozenset({"national_political", "mixed_local_national"}),
    "combined": frozenset({
        "ward_specific_local", "surrey_wide_local", "mixed_local_national",
        "national_political", "regional",
    }),
}

# The five specifications the brief asks to be compared. "baseline" carries no
# news features at all and is the frozen Stage 1 model; "full" is the combined
# news block plus the permitted baseline context, which is the only one that
# may use contextual predictors alongside news.
SPECIFICATIONS: tuple[str, ...] = (
    "baseline", "local", "national", "combined", "full",
)


def arm_of(scope: str) -> str:
    """The arm label for one article's scope classification.

    An unrecognised scope returns ``"uncertain"`` rather than being guessed
    into an arm. A misfiled article is worse than an excluded one here,
    because the whole point of the comparison is which arm carries the signal.
    """

    return SCOPE_TO_ARM.get(str(scope), "uncertain")


def rows_for_arm(
    news_rows: Sequence[Mapping[str, object]],
    arm: str,
) -> list[dict]:
    """The news feature rows an arm is allowed to see.

    ``baseline`` sees none, by definition - it is the comparator the news
    models have to beat, and letting it see any news feature would make the
    comparison meaningless.
    """

    if arm == "baseline":
        return []
    scopes = ARM_SCOPES.get(arm)
    if scopes is None:
        raise ValueError(
            f"Unknown arm {arm!r}. Known arms: {sorted(ARM_SCOPES)} plus 'baseline'."
        )
    return [
        dict(row) for row in news_rows
        if str(row.get("scope_classification")) in scopes
    ]


def arm_coverage(news_rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """How much evidence each arm actually has, before anything is fitted.

    Reported per election as well as in total, because an arm with plenty of
    rows concentrated in one election cannot be separated from that election
    and is not the usable sample its total suggests.
    """

    by_scope: dict[str, int] = {}
    by_arm_election: dict[str, dict[str, int]] = {}
    for row in news_rows:
        scope = str(row.get("scope_classification"))
        by_scope[scope] = by_scope.get(scope, 0) + 1
        election = str(row.get("election_id"))
        for arm, scopes in ARM_SCOPES.items():
            if scope in scopes:
                by_arm_election.setdefault(arm, {})
                by_arm_election[arm][election] = (
                    by_arm_election[arm].get(election, 0) + 1
                )

    return {
        "rows_by_scope": dict(sorted(by_scope.items())),
        "rows_by_arm_and_election": {
            arm: dict(sorted(counts.items()))
            for arm, counts in sorted(by_arm_election.items())
        },
        "elections_per_arm": {
            arm: len(counts) for arm, counts in sorted(by_arm_election.items())
        },
        # An arm present in fewer than three elections cannot show stability
        # across chronological folds, whatever its row count.
        "arms_with_too_few_elections": sorted(
            arm for arm, counts in by_arm_election.items() if len(counts) < 3
        ),
    }
