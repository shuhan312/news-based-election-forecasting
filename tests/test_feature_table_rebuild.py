"""The committed feature tables must rebuild from the committed code.

Four extraction tranches were written to `llm_context/` after the tables were
built, and none of them belongs to the lineage it now sits beside:

    news_feature_table_v1.csv   2026-08-01 12:26
    news_feature_table_v2.csv   2026-08-01 16:23
    haslemere1                  2026-08-01 22:55   single-contest probe
    e5local1                    2026-08-02 01:31   E5 triage, kappa 0.4762
    wokingsouth1                2026-08-02 17:23   blind protocol corpus

They put 948 articles outside release v1 and 321 outside v2, so the builder's
corpus assertion stopped both - correctly, since a table mixing corpora is
the failure that assertion exists to catch. The fix is for each wrapper to
declare its own lineage, and these tests are what keep those declarations
honest: name too few tranches and the build dies, too many and the bytes move.
"""

import hashlib
import io
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

import pytest

V1_CSV = Path("news_features/news_feature_table_v1.csv")
V2_CSV = Path("news_features/news_feature_table_v2.csv")

needs_corpus = pytest.mark.skipif(
    not Path("llm_context/corpus_extraction_outputs_all.json").exists(),
    reason="extraction outputs not present")


@contextmanager
def frozen_globals_restored():
    """Every wrapper configures the builder by rebinding module globals."""
    from src.news_features import build_feature_table as frozen
    names = ("OUT_CSV", "OUT_META", "build_release", "CANONICAL_MANIFEST",
             "GRID_ELECTIONS", "EXCLUDED_TRANCHES")
    saved = {n: getattr(frozen, n) for n in names}
    split = dict(frozen.SPLIT_ROLE)
    try:
        yield frozen
    finally:
        for name, value in saved.items():
            setattr(frozen, name, value)
        frozen.SPLIT_ROLE.clear()
        frozen.SPLIT_ROLE.update(split)


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_the_default_excludes_nothing():
    """Importing the builder must stay inert.

    `build_haslemere_probe_features` and `build_woking_south_blind_features`
    import this module and need exactly the tranches the v1 set removes, so a
    non-empty default would break two builds that currently work.
    """
    from src.news_features import build_feature_table as frozen
    assert frozen.EXCLUDED_TRANCHES == set()


@needs_corpus
def test_v1_rebuilds_byte_identically(tmp_path):
    with frozen_globals_restored() as frozen:
        frozen.OUT_CSV = tmp_path / "v1.csv"
        frozen.OUT_META = tmp_path / "v1_meta.json"
        frozen.EXCLUDED_TRANCHES = set(frozen.V1_EXCLUDED_TRANCHES)
        with redirect_stdout(io.StringIO()):
            frozen.main()
        rebuilt = sha256(frozen.OUT_CSV)
    assert rebuilt == sha256(V1_CSV)


@needs_corpus
def test_v2_rebuilds_byte_identically(tmp_path):
    """Imports the v2 wrapper rather than restating its configuration.

    What is tested is then the shipped build, not a copy of it that could
    drift away from the wrapper without anything noticing.
    """
    with frozen_globals_restored() as frozen:
        from src.news_features import build_feature_table_v2  # noqa: F401
        frozen.OUT_CSV = tmp_path / "v2.csv"
        frozen.OUT_META = tmp_path / "v2_meta.json"
        with redirect_stdout(io.StringIO()):
            frozen.main()
        rebuilt = sha256(frozen.OUT_CSV)
    assert rebuilt == sha256(V2_CSV)
