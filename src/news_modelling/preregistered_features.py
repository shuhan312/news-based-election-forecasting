"""The pre-registered news feature set: fixed before the data is touched.

## Why this file exists

The first attempt at feature selection screened roughly 12,000 candidate
columns (the ward-party-election table's 24,151 columns, filtered) against
3,418 training rows. It surfaced correlations of 0.737 and 0.703 - higher
than the frozen Stage 1 baseline prediction's own 0.502 - and
`feature_selection_findings.md` flagged those on sight as "implausible on
its face". They are: with 12,000 candidates and 2 elections carrying
usable variation, the largest observed correlation says almost nothing
about the population and almost everything about the number of draws.

The fix is not a better screen. It is to stop screening. This module names
the features the research question implies, in advance, in one place,
without consulting the data. Whatever they show is then interpretable,
because nothing was selected on the outcome.

## Where the list comes from

Each feature below traces to a specific line in the supervisor's brief
(section 7, "turning news into features") or to the six-window timing
design. Features whose input layer failed the D4 validation gate are
listed but marked unavailable, so this file also records what the research
question wanted and could not have - a reader can see the gap rather than
having to infer it from an absence.

## The budget

At roughly 3,400 training rows the conventional ceiling of one feature per
ten rows would permit 340 features. That ceiling is not the binding
constraint here and never was. The binding constraint is how many
*elections* carry usable variation: news features are constant within an
election for the election-wide blocks, and only two elections have both a
baseline prediction and division-level news. A feature set of 20-30 is
already generous against two effective clusters, and the count below is
deliberately near the low end.

## What "unavailable" means operationally

An unavailable feature is not silently omitted from the specification. It
is carried through with `available=False` and its blocking reason, so the
feature dictionary, the model card and the report all show the same set of
intentions and the same set of gaps. This is the same discipline the
baseline release uses for its null semantics: absence is recorded with a
reason, never left to be guessed.
"""

from __future__ import annotations

from dataclasses import dataclass

# The six collection windows, in the scheme the supervisor confirmed on
# 2026-07-29. Ordered oldest-first so that a feature name's suffix sorts
# chronologically, which makes a coefficient table readable down the page.
WINDOWS = ("180_to_91_days", "90_to_31_days", "30_to_15_days",
           "14_to_8_days", "7_to_4_days", "final_72_hours")

# Cumulative snapshots: what was knowable by each cutoff. The same article
# appears in several, by design - a snapshot is "everything available as
# at this point", not a disjoint band.
SNAPSHOTS = ("as_at_90_days", "as_at_30_days", "as_at_7_days",
             "as_at_polling_eve")

# Extraction layers and their D4 status, so a feature's availability is
# derived from one place rather than asserted per feature.
LAYER_STATUS = {
    "volume": ("available", "counted from the eligible corpus without any "
                            "LLM judgement, so no validation gate applies"),
    # Revised after the validator-gating fault (d4_findings_log.md
    # experiment 8). Every D4 kappa had been computed from records that
    # parsed, without checking whether the record's evidence spans could be
    # found in the article - and a record the validator rejects is discarded
    # downstream while its primary_issue still reads perfectly. Recomputing
    # on accepted records only moved three of the figures this table was
    # built on, and flipped two verdicts. The superseded values are named
    # here so a reader of an older draft can see which number changed.
    "issues": ("available", "kappa 0.616 (Sonnet, n=53) against the human "
                            "coding, 0.742 between arms - the only original "
                            "layer clearing both rulers. Supersedes 0.729, "
                            "which was ungated"),
    "credit_blame": ("unavailable", "kappa 0.521 (Sonnet, n=57) and 0.516 "
                                    "(Haiku) against the human coding; the "
                                    "fallback AC1 route does not trigger at "
                                    "a largest marginal of 0.579. Supersedes "
                                    "an ungated 0.600 recorded as passing. "
                                    "Disagreements scatter across seven "
                                    "cells with matching marginals, so no "
                                    "definitional fix is diagnosed; the "
                                    "binary-split redesign is identified but "
                                    "unrun"),
    # Dropped after its redesign replicated at 0.598 on both arms - see
    # d4_findings_log.md experiment 10. The redesign worked as a diagnosis and
    # failed as a rescue: it closed the threshold gap the confusion matrix
    # found (the model went from calling 60% of articles consequential to 18%
    # against the reviewer's 30%), eliminated all 31 validator rejections, and
    # took inter-model agreement from 0.587 to 0.889 - two models with
    # near-identical marginals, 49 of 60 "none" on each. Both then landed
    # 0.002 below the bar against the reviewer. So the residual disagreement is
    # systematic and replicated rather than noise, which is the best evidence
    # here that the reviewer's coding may be the looser side, and it licenses
    # nothing: two models sharing training data and a prompt are not
    # independent coders, and the reviewer's own test-retest reliability on
    # this field was never measured. Neither side can be shown correct, which
    # is exactly the case the gate exists to catch.
    "consequence": ("unavailable", "frozen layer fails at 0.259 (Sonnet, "
                                   "n=55) human and 0.587 between arms. The "
                                   "redesign reaches presence kappa 0.598 on "
                                   "both arms at n=60, 0.002 short, with "
                                   "inter-model agreement of 0.889. Dropped "
                                   "under the rule stated before the second "
                                   "arm reported"),
    "reform_flag": ("available", "deterministic pattern match on the article "
                                 "text, so no validation gate applies. "
                                 "Supersedes reform_uk.applicable (kappa "
                                 "0.680 on Haiku), which lives in the "
                                 "excluded consequence layer and is "
                                 "unreachable on either arm - see "
                                 "REFORM_PATTERNS for why, and for the "
                                 "3.4-point under-count the strict pattern "
                                 "carries"),
    # Recovered. The original layer failed both rulers (0.482-0.490 human,
    # 0.316 inter-model); the revised single-question layer clears both
    # (0.848 inter-model, 0.736-0.741 human). Available at three levels
    # rather than five - there is no `mixed` category and no separate
    # intensity - so features built on it must not be described as
    # five-level sentiment.
    "stance": ("available", "revised layer: kappa 0.848 between arms and "
                            "0.736-0.741 against the human labels, after the "
                            "original failed at 0.316 / 0.482. Three-level "
                            "portrayal, no mixed category, no intensity"),
    # Partially recovered. The original sixteen-way primary_frame failed
    # every ruler; a revised layer asking four independent binary presence
    # questions clears two of the four. The other two - challenger_emergence
    # and voter_discontent - are undetermined rather than failed: detected
    # in 2-6 of 55 articles, so their agreement figures rest on articles
    # where both arms said absent. See frame_rescue_agreement.md.
    "framing": ("available", "revised layer, binary presence: "
                             "incumbent_judgement kappa 0.705 and "
                             "local_impact 0.635 between arms, after the "
                             "sixteen-way original failed at 0.502. Human "
                             "recall is only 0.49-0.58, so the construct "
                             "divergence is larger than for any other "
                             "adopted layer"),
    "framing_thin": ("undetermined", "challenger_emergence (2-6 positives "
                                     "of 55) and voter_discontent (4-5) - "
                                     "too few positive cases for a verdict, "
                                     "not failed. A Reform-enriched sample "
                                     "would settle them"),
    "horizon": ("unavailable", "failed all three, as above (0.229 / 0.339)"),
}


@dataclass(frozen=True)
class Feature:
    """One pre-registered feature, with its provenance and its status."""

    name: str
    layer: str
    description: str
    brief_reference: str
    windowed: bool = True

    @property
    def status(self) -> str:
        return LAYER_STATUS[self.layer][0]

    @property
    def status_reason(self) -> str:
        return LAYER_STATUS[self.layer][1]


# --- the set -----------------------------------------------------------
# Grouped by what each group is for, because a reader assessing the
# specification needs to see the theory, not just the column names.

VOLUME = [
    Feature("article_count", "volume",
            "eligible articles linked to this area and election",
            "section 7: 'number of Reform-related articles'"),
    Feature("party_article_count", "volume",
            "eligible articles naming this party",
            "section 7: 'number of Reform-related articles', per party"),
    Feature("local_article_count", "volume",
            "eligible articles from the local collection arm",
            "section 7: 'split between local Surrey vs UK national'"),
    Feature("national_article_count", "volume",
            "eligible articles from the national collection arm",
            "section 7: 'split between local Surrey vs UK national'"),
    Feature("independent_source_count", "volume",
            "distinct publications, one per duplicate group",
            "section 7: 'we always keep the article-level data'; guards "
            "against one syndicated story counting as many"),
    Feature("recency_weighted_count", "volume",
            "articles weighted by proximity to polling day",
            "section 7: 'recency-weighted coverage'"),
    Feature("days_since_most_recent_article", "volume",
            "gap between the newest eligible article and polling day",
            "section 7: 'days since the most recent Reform-related story'",
            windowed=False),
]

ISSUES = [
    Feature("issue_immigration_count", "issues",
            "articles whose primary issue is immigration",
            "section 8: 'national immigration coverage'"),
    Feature("issue_crime_policing_count", "issues",
            "articles whose primary issue is crime and policing",
            "section 8: 'local crime reporting'"),
    Feature("issue_housing_planning_count", "issues",
            "articles whose primary issue is housing or planning",
            "section 7: 'topic breakdowns'"),
    Feature("issue_council_services_count", "issues",
            "articles on council services, finance or council tax",
            "section 7: 'topic breakdowns'"),
    Feature("issue_national_politics_count", "issues",
            "articles whose primary issue is national politics or economy",
            "section 5: 'national stories that may influence local voting'"),
    Feature("issue_diversity", "issues",
            "distinct primary issues present, as a count",
            "derived: distinguishes a single dominant story from a broad "
            "news environment, which no single-issue count can"),
]

ATTRIBUTION = [
    Feature("blame_count", "credit_blame",
            "articles attributing blame to this party",
            "section 7: 'number of negative stories' - the adopted "
            "substitute for per-party sentiment"),
    Feature("credit_count", "credit_blame",
            "articles attributing credit to this party",
            "section 7: 'net sentiment', substituted"),
    Feature("net_attribution", "credit_blame",
            "credit_count minus blame_count",
            "section 7: 'net sentiment', substituted"),
    Feature("recency_weighted_blame", "credit_blame",
            "blame weighted by proximity to polling day",
            "section 7: 'recency-weighted coverage' x tonal direction"),
]

CONSEQUENCE = [
    Feature("implied_damage_count", "consequence",
            "articles implying potential electoral damage to this party",
            "section 7: 'relevance to Reform UK' and 'how strong the "
            "signal is'"),
    Feature("implied_benefit_count", "consequence",
            "articles implying potential electoral benefit to this party",
            "section 7: as above, opposite sign"),
    Feature("anti_incumbent_mechanism_count", "consequence",
            "articles whose implied mechanism is anti-incumbent sentiment",
            "section 7: 'whether it is a controversy, endorsement, policy "
            "announcement'"),
]

# Re-operationalised 2026-07-30, from an LLM judgement to a deterministic
# string match, because the judgement has no reachable data source.
#
# `reform_uk.applicable` is a property of the electoral-consequence schema.
# That layer failed the D4 gate and is not extracted, so the two features
# below had no data behind them - which the 20-feature count concealed until
# the corpus run was already submitted.
#
# Re-including the layer does not fix it, because its two arms fail in
# opposite directions. The `applicable` judgement validated on Haiku at kappa
# 0.680 and failed on Sonnet at 0.288; but the layer requires verbatim
# evidence spans, which Haiku satisfies on 56% of them, and the reform_uk
# block carries its own span requirement - so on Haiku the flag is discarded
# with the record. The arm that can make the judgement cannot produce the
# evidence, and the arm that can produce the evidence cannot make the
# judgement. No amount of extraction resolves that.
#
# So the construct is narrowed to one that needs no judgement: does the
# article name Reform UK. `stance_rescue.parties_present` already matches it
# deterministically, on `reform uk` and `reform party`, with bare "reform"
# excluded so that policy reform does not count as the party.
#
# THE COST OF THE CHANGE, STATED RATHER THAN ABSORBED. "Names Reform UK" is a
# weaker construct than "is materially about Reform UK", and the report must
# use the weaker wording. Measured on the 178 articles extracted so far, the
# strict pattern matches 19 (10.7%) while a bare capitalised "Reform" matches
# 25 (14.0%), so the strict form under-counts by about 3.4 percentage points -
# articles that write "Reform" without ever writing "Reform UK". Both forms
# are computed, the strict one as primary and the loose one as a sensitivity
# check, because the choice between them is a judgement call and free to test.
#
# WHAT THE CHANGE BUYS, beyond having any data at all: no validation gate
# applies to a string match, the count is reproducible from the corpus and the
# pattern alone, and it can be explained in one sentence - which is one of the
# four constraints the supervisor set in writing.
REFORM_PATTERNS = {
    "strict": (r"\breform uk\b", r"\breform party\b"),
    "loose": (r"\bReform\b",),   # sensitivity form: case-sensitive, party-ish
}

REFORM_SPECIFIC = [
    Feature("reform_named_count", "reform_flag",
            "articles naming Reform UK, by deterministic pattern match "
            "(strict form primary, loose form as a sensitivity check)",
            "section 1: Reform UK is the principal research party"),
    Feature("reform_share_of_coverage", "reform_flag",
            "reform_named_count over article_count",
            "section 7: 'Reform share of local political coverage'"),
]

STANCE_PENDING = [
    Feature("unfavourable_count", "stance",
            "articles portraying this party unfavourably",
            "section 7: 'number of negative stories'"),
    Feature("favourable_count", "stance",
            "articles portraying this party favourably",
            "section 7: 'net sentiment'"),
    Feature("net_portrayal", "stance",
            "favourable_count minus unfavourable_count",
            "section 7: 'net sentiment'"),
]

FRAMING = [
    Feature("frame_incumbent_judgement_count", "framing",
            "articles passing judgement on the governing administration's "
            "record",
            "section 7: 'whether it is about a candidate, party or general "
            "issue'"),
    Feature("frame_local_impact_count", "framing",
            "articles framing the matter through concrete local consequences",
            "section 5: 'local political reporting' vs national coverage"),
]

UNAVAILABLE = [
    Feature("frame_challenger_emergence_count", "framing_thin",
            "articles presenting an outsider party as a rising force - the "
            "frame most directly about Reform UK, and the one the sample "
            "cannot yet validate",
            "section 8: 'whether certain types of news are more strongly "
            "associated with changes in Reform support'"),
    Feature("frame_voter_discontent_count", "framing_thin",
            "articles portraying voters as dissatisfied or wanting to punish",
            "section 7: 'topic breakdowns', anti-incumbent aspect"),
    Feature("persistent_effect_count", "horizon",
            "articles implying a persistent rather than transient effect",
            "section 7: 'how strong the signal is', temporal aspect"),
]

ALL_FEATURES = (VOLUME + ISSUES + ATTRIBUTION + CONSEQUENCE +
                REFORM_SPECIFIC + STANCE_PENDING + FRAMING + UNAVAILABLE)


def available_features() -> list[Feature]:
    """Features whose input layer cleared the D4 gate."""
    return [f for f in ALL_FEATURES if f.status == "available"]


def column_names(features: list[Feature] | None = None,
                 *, window: str | None = None) -> list[str]:
    """The columns for ONE specification - one window, not all of them.

    This signature is deliberate. Expanding 22 windowed features across
    six windows gives 127 columns, and with only two elections carrying
    usable variation that is far past the point where a fit describes
    anything but itself. It also is not what the brief asks for: it
    specifies separate comparisons ("baseline plus one-month news",
    "baseline plus one-week news", each against the frozen baseline), not
    one model holding every window at once.

    So each window is its own specification of about 22 columns, run and
    reported separately, and the question "does timing matter" is answered
    by comparing those runs to each other rather than by reading
    coefficients out of a single wide model.

    ``window=None`` returns the unwindowed features only - the shape used
    by a specification that deliberately ignores timing.
    """
    features = available_features() if features is None else features
    out: list[str] = []
    for f in features:
        if not f.windowed:
            out.append(f.name)
        elif window is not None:
            out.append(f"{f.name}__{window}")
    return out


def specifications_to_run() -> list[dict]:
    """Every model specification the comparison harness should fit.

    One per disjoint window and one per cumulative snapshot, plus a
    volume-only control. The control matters: if the full feature set beats
    the baseline but the volume-only set beats it by the same margin, then
    what the news layer detected was "an election that got covered a lot",
    not anything about the content - and only running both makes that
    visible.
    """
    # The control uses the widest cumulative snapshot - everything knowable
    # before polling - so it is comparable with the content specifications
    # rather than handicapped by a narrower window. Passing window=None
    # here would have left only the single unwindowed feature, which is a
    # control against nothing.
    specs = [{
        "name": "volume_only__as_at_polling_eve",
        "window": "as_at_polling_eve",
        "features": [f for f in available_features() if f.layer == "volume"],
        "purpose": ("control - distinguishes a content effect from a bare "
                    "coverage-volume effect. If this matches the full "
                    "specification's improvement, the news layer detected "
                    "how much an election was covered, not what was said"),
    }]
    for window in WINDOWS:
        specs.append({
            "name": f"full__{window}",
            "window": window,
            "features": available_features(),
            "purpose": f"all validated features, articles in the {window} band",
        })
    for snapshot in SNAPSHOTS:
        specs.append({
            "name": f"full__{snapshot}",
            "window": snapshot,
            "features": available_features(),
            "purpose": (f"all validated features, everything knowable "
                        f"{snapshot.replace('as_at_', 'as at ')}"),
        })
    return specs


def specification() -> dict:
    """The machine-readable pre-registration record.

    Written to disk before the features are built, so the claim that the
    set was fixed in advance is checkable against a timestamp rather than
    resting on assertion.
    """
    by_status: dict[str, list[dict]] = {}
    for f in ALL_FEATURES:
        by_status.setdefault(f.status, []).append({
            "name": f.name, "layer": f.layer, "windowed": f.windowed,
            "description": f.description,
            "brief_reference": f.brief_reference,
        })
    available = available_features()
    return {
        "windows": list(WINDOWS),
        "cumulative_snapshots": list(SNAPSHOTS),
        "layer_status": {k: {"status": v[0], "reason": v[1]}
                         for k, v in LAYER_STATUS.items()},
        "features_by_status": by_status,
        "counts": {
            "features_declared": len(ALL_FEATURES),
            "features_available": len(available),
            "columns_per_specification":
                len(column_names(available, window=WINDOWS[0])),
            "specifications_to_fit": len(specifications_to_run()),
        },
        "note": (
            "Fixed before the feature table was rebuilt. No column here was "
            "chosen by screening against the outcome - the earlier "
            "12,000-candidate screen produced correlations above the frozen "
            "baseline's own, which is the signature of selection on noise "
            "rather than of signal."),
    }
