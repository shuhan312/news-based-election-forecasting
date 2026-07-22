# N5 candidate specifications (audit-backed, not yet implemented)

This document specifies — but does not implement — the hierarchical
Bayesian compositional model family (N5), constrained by what the
identifiability audit (`docs/n5_data_requirements_and_risks.md`,
`outputs/n5_specification/`) shows the real Surrey release can support.
Method anchors: Hanretty (2021) for Dirichlet regression over multiparty
vote shares and its structural-zero complications; Stoetzer et al. (2019)
for Bayesian multiparty forecasting with posterior-predictive validation;
Chen, Garnett & Montgomery (2023) for hierarchical Dirichlet regression
with cycle-level effects.

## Observation unit

One CONTEST: election event x analytical area, with the complete set of
contesting parties as one compositional observation. Party rows are never
independent observations. The audit finds 258 usable closed compositions
(1,139 party rows); the 81 multi-member 2026 contests are excluded because
their party-share estimand is undefined, not missing.

## N5a — the specified model

- **Likelihood**: contest-level Dirichlet over the S_c contesting parties'
  share vector, alternative-mean parameterisation
  y_c ~ Dirichlet(phi * mu_c), with one global precision phi (Hanretty
  2021's parameterisation).
- **Linear predictor** (softmax link over the contest's actual ballot):
  eta_{c,p} = alpha_{party(p)} + gamma_{cycle(c)} + x_{c,p}' beta;
  mu_{c,p} = softmax over the parties actually standing in c. Varying
  party sets are handled by construction: the softmax runs over each
  contest's own ballot, so absent parties receive no share and no
  pseudo-zero — consistent with the release, where structural
  non-participation has no row at all. No epsilon replacement, ever.
- **Fixed effects x_{c,p}** (strictly pre-election, no news): the N4
  cold-start smoothed Surrey-wide strength (log or logit scale), the
  approved previous local party share where it exists WITH its existing
  missing/applicability indicator (never imputed as zero), incumbency
  where resolved, and a by-election indicator.
- **Hierarchical effects**:
  - party intercepts alpha_p: partial pooling across all 35 audited
    parties, alpha_p ~ Normal(0, sigma_party). The audit shows only 6
    parties (Conservative, Labour, Labour and Co-operative, Liberal
    Democrats, Green, UKIP) carry enough repetition for individually
    stable intercepts; the remaining 29 — including Reform UK with 13
    usable contests — are exactly what partial pooling is for.
  - cycle effect gamma_e ~ Normal(0, sigma_cycle) over the 18 election
    events, accepting that 15 by-election singletons are informed almost
    entirely by the pooled sigma_cycle rather than their own data.
- **Priors**: weakly informative, fold-fixed before fitting — e.g.
  Normal(0, 1) on beta, half-Normal on sigma_party/sigma_cycle, and a
  prior on phi centred near Hanretty's reported precision scale
  (phi ~= 20) rather than tuned on Surrey outcomes.
- **Training universe**: the 258 usable compositions strictly earlier
  than each fold's target. **Prediction universe**: all folds' contests,
  including Cohort B/C rows (predicted geography-agnostically, as N4
  does); scoring restricted to defined targets as in the coverage layer.
- **Expected advantages over N0-N4**: replaces N4's demonstrably weak
  equal-share prior with learned partial pooling (the N4 ablation is
  direct evidence for this change); adds calibrated posterior-predictive
  uncertainty, which no existing model provides.
- **Risks**: phi misspecification distorting interval width; softmax
  non-identifiability requiring a reference-party or sum-to-zero
  constraint on alpha; small-sample MCMC cost is minor (258 contests).

An area-level random effect was considered against the area audit and
not pursued: with only 3-4 observations per area its variance would
compete with the global precision to explain contest-level dispersion,
and the existing local-history predictor already carries most area
information (the four-model comparison showed area identity adds under
one MAE point over party identity alone). The area audit remains on
record as the evidence behind that decision.

## Temporal validation design (binding on any future implementation)

Reuse `temporal_validation.iter_temporal_folds` unchanged: strictly
earlier training, same-day separation, 2013 never a target. Per fold:
priors and any preprocessing fixed before seeing the held-out election;
fit on the fold's usable training compositions; draw posterior-predictive
share vectors for the held-out contests. Report, integrated into the
existing coverage-aware layer (same joins, same cohort splits, same
common-sample discipline as N0-N4):

- posterior-predictive mean share MAE (own-covered and common-sample);
- winner accuracy from the posterior mode where a unique leader exists;
- 50%/90% credible-interval coverage of realised shares and mean interval
  width (sharpness) — credible-interval coverage is a calibration
  property and must never be conflated with the observational coverage
  rates of the evaluation layer;
- convergence (R-hat, divergences, effective sample size) per fold;
- posterior-predictive checks: simulated share sums, winner margins, and
  zero-history party shares against realised values.
