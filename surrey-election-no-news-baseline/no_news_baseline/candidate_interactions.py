"""Reform UK interaction terms, and a labelled UKIP counterpart.

The brief asks for them directly:

    permit interactions between Reform UK and relevant historical predictors

By the time they were built the data had asked for them twice as well, which
is why they exist here as a targeted fix rather than a checklist item.

The evidence
------------
**First**, SHAP on the selected tree model showed `previous_party_vote_share`
contributing +0.0498 to Conservative predictions and −0.0880 to Reform ones —
the same feature moving two parties in opposite directions.

**Second**, adding county-level strength features made the two linear
architectures substantially *worse* on Reform: Architecture A from 16.7 to
42.6 per cent worse than an equal split, C from 15.8 to 31.6. Both predicted
Reform lower after being handed a feature saying Reform had been polling 20
per cent.

Both observations have one explanation. County strength and division share
move together for almost every party; Reform is the exception, at 20.67 per
cent county-wide from single-member by-elections against 10.80 in two-member
wards where its support splits across two ballot lines. A linear model fits
one global slope per feature and applies it to every party, so Reform is
dragged along a relationship it does not follow. A tree can condition on
party, which is why Architecture B was unharmed.

An interaction column lets a linear model hold a second slope for one party.
That is the whole mechanism.

Why only Reform UK and UKIP
---------------------------
Interacting every party with every historical predictor would add roughly 40 ×
6 = 240 columns to a 1,150-row training fold, which is a reliable way to fit
noise. Reform UK gets them because it is the study party and because the data
twice showed it following a different relationship. UKIP gets them as the
brief's explicitly optional, clearly labelled sensitivity feature:

    An optional experimental model may use UKIP as a separate contextual
    feature, but only if Reform UK and UKIP remain separate; the assumption
    is clearly labelled; performance is compared with a model that does not
    use this information.

so the UKIP block is off by default and must be switched on deliberately.

What an interaction is not
--------------------------
It is not more information. Every value here is a product of two columns the
model already had. It changes what the model can *express*, not what it
knows, and if the mechanism above is wrong the terms will simply be shrunk
toward zero by the penalty rather than helping.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence


# The historical predictors worth interacting. Each is a quantity whose
# relationship with vote share plausibly differs for a party with no local
# record, which is the case the interaction exists to separate. Contest
# structure and party identity are excluded: the first is not historical, the
# second would interact an indicator with itself.
INTERACTED_PREDICTORS: tuple[str, ...] = (
    "previous_party_vote_share",
    "party_county_strength_previous",
    "party_county_strength_trend",
    "party_contest_rate_previous",
)

REFORM_PREFIX = "reform_x_"
UKIP_PREFIX = "ukip_x_"


def reform_interaction_names() -> tuple[str, ...]:
    return tuple(f"{REFORM_PREFIX}{name}" for name in INTERACTED_PREDICTORS)


def ukip_interaction_names() -> tuple[str, ...]:
    return tuple(f"{UKIP_PREFIX}{name}" for name in INTERACTED_PREDICTORS)


def attach_interactions(
    rows: Sequence[Mapping[str, object]],
    *,
    include_reform: bool = True,
    include_ukip: bool = False,
) -> tuple[dict[str, object], ...]:
    """Return copies of the rows with interaction columns added.

    ``include_reform`` exists so the terms can be switched off. The brief
    requires the optional UKIP block to be "compared with a model that does
    not use this information", and an ablation needs a control arm; the same
    switch is what produced the before-and-after table in
    ``docs/reform_interaction_terms.md``.

    A missing base value produces a missing interaction, never zero. Zero
    would be a lie in both directions: for a Reform row it would say "Reform
    with a county strength of nothing", and for a non-Reform row it would be
    indistinguishable from that. The encoder gives every numeric column its
    own missing indicator, so a null here stays visible as a null.

    Rows are copied rather than mutated so the contract as published stays
    exactly as the extractor wrote it, and any difference between the two is
    inspectable.
    """

    if include_ukip and not include_reform:
        # UKIP's block is a contextual extra to the Reform terms, never a
        # replacement for them. Allowing it alone would produce a run that
        # models UKIP's history conditionally and Reform's globally, which is
        # the opposite of the study's purpose.
        raise ValueError(
            "include_ukip requires include_reform: the UKIP block is a "
            "sensitivity extension of the Reform terms, not a substitute."
        )

    output: list[dict[str, object]] = []
    for row in rows:
        enriched = dict(row)
        is_reform = bool(row.get("is_reform_uk"))
        is_ukip = bool(row.get("is_ukip"))

        for name in INTERACTED_PREDICTORS:
            base = row.get(name)
            # For a non-Reform row the interaction is genuinely zero - the
            # indicator is off, so the product is zero and the model reads it
            # as "this term does not apply here". For a Reform row with a
            # missing base value it is unknown, not zero.
            if include_reform:
                enriched[f"{REFORM_PREFIX}{name}"] = (
                    None if (is_reform and base is None)
                    else (float(base) if is_reform and base is not None else 0.0)
                )
            if include_ukip:
                enriched[f"{UKIP_PREFIX}{name}"] = (
                    None if (is_ukip and base is None)
                    else (float(base) if is_ukip and base is not None else 0.0)
                )
        output.append(enriched)
    return tuple(output)


def interaction_coverage(
    rows: Sequence[Mapping[str, object]],
    *,
    include_ukip: bool = False,
) -> dict[str, object]:
    """How many rows each interaction actually carries a non-zero value for.

    Published because an interaction term that is zero on every row the party
    contests is not a fix, it is a column of zeros that the penalty will
    remove; and because that has to be checkable before any claim is made
    about whether the terms helped.
    """

    enriched = attach_interactions(rows, include_ukip=include_ukip)

    def block(names: Sequence[str], selector) -> dict[str, object]:
        selected = [row for row in enriched if selector(row)]
        return {
            "rows": len(selected),
            **{
                name: sum(
                    1 for row in selected
                    if row.get(name) not in (None, 0.0)
                )
                for name in names
            },
        }

    report: dict[str, object] = {
        "reform_uk": block(
            reform_interaction_names(), lambda r: bool(r.get("is_reform_uk"))
        ),
        "interacted_predictors": list(INTERACTED_PREDICTORS),
        "note": (
            "A zero on a non-Reform row is correct - the indicator is off. A "
            "null on a Reform row means the base predictor was itself missing "
            "and is kept distinct from zero."
        ),
    }
    if include_ukip:
        report["ukip"] = block(
            ukip_interaction_names(), lambda r: bool(r.get("is_ukip"))
        )
    return report
