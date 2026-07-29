"""Stage 2 news modelling: the residual layer over the frozen Stage 1 baseline.

Prompt 2 names the residual model as the principal approach, because it
directly measures whether news adds information beyond election history rather
than merely fitting alongside it.

Everything here reads the Stage 1 bundle and never writes to it. Stage 1's
out-of-fold predictions are what a news result is measured against, so a news
layer able to regenerate them would make a disappointing news result and a
quietly rebuilt baseline indistinguishable afterwards.
"""
