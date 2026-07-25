"""Phase 5 / Step 2 tests: canonicalisation rules, grouping and
relationship classification, determinism and incremental stability."""

from src.dedup.url_canonical import (RULE_VERSION, canonicalise,
                                     resolve_url_groups)

# -------------------------------------------------- canonicalisation

def test_tracking_params_removed_meaningful_kept():
    c = canonicalise("https://example.org/story?id=42&utm_source=x"
                     "&fbclid=abc&gclid=zzz&page=2")
    assert c["canonical"] == "https://example.org/story?id=42&page=2"
    assert any(t.startswith("tracking_params:") for t in c["transforms"])


def test_fragment_port_slashes_normalised():
    c = canonicalise("https://Example.org:443//news//story/#comments")
    assert c["canonical"] == "https://example.org/news/story"
    assert "fragment_removed" in c["transforms"]
    assert "default_port" in c["transforms"]


def test_host_lowercased_path_case_preserved():
    c = canonicalise("https://WWW.Example.org/News/Story-ID")
    assert c["canonical"] == "https://www.example.org/News/Story-ID"


def test_amp_and_mobile_variants_unwrapped():
    a = canonicalise("https://m.example.org/story/amp")
    assert a["canonical"] == "https://example.org/story"
    assert "mobile_host" in a["transforms"]
    assert "amp_path" in a["transforms"]


def test_wayback_unwrapped_with_capture_ts():
    c = canonicalise("https://web.archive.org/web/20260417060507/"
                     "https://www.getsurrey.co.uk/news/surrey-news/x")
    assert c["canonical"] == \
        "https://www.getsurrey.co.uk/news/surrey-news/x"
    assert c["capture_ts"] == "20260417060507"
    assert "wayback_unwrapped" in c["transforms"]


def test_malformed_url_flagged_not_guessed():
    c = canonicalise("not a url at all")
    assert c["canonical"] == ""
    assert "malformed_url" in c["flags"]


def test_canonicalisation_deterministic():
    u = "https://example.org/a?b=1&utm_source=x#f"
    assert canonicalise(u) == canonicalise(u)

# ---------------------------------------------- grouping / classification

def rec(aid, url, body="h1"):
    return {"article_id": aid, "original_url": url, "body_hash": body,
            "retrieved_at": "2026-07-01T00:00:00Z"}


def by_id(res):
    return {r["article_id"]: r for r in res["mapping"]}


def test_same_url_same_content():
    res = resolve_url_groups([
        rec("A1", "https://ex.org/story?utm_source=a"),
        rec("A2", "https://ex.org/story?utm_source=b")])
    m = by_id(res)
    assert m["A1"]["relationship"] == "same_url_same_content"
    assert m["A1"]["group_id"] == m["A2"]["group_id"]


def test_same_url_changed_content_is_possible_update():
    res = resolve_url_groups([
        rec("A1", "https://ex.org/story", body="h1"),
        rec("A2", "https://ex.org/story", body="h2")])
    m = by_id(res)
    assert m["A1"]["relationship"] == "same_url_content_changed"
    assert "possible_updated_version" in m["A1"]["flags"]


def test_variant_merge_with_different_content_is_weaker_claim():
    res = resolve_url_groups([
        rec("A1", "https://web.archive.org/web/20200101/"
                  "https://ex.org/story", body="h1"),
        rec("A2", "https://ex.org/story", body="h2")])
    m = by_id(res)
    assert m["A1"]["relationship"] == "url_variant_probable_same_page"


def test_different_url_same_exact_content_kept_from_step1():
    res = resolve_url_groups([
        rec("A1", "https://ex.org/story-a", body="same"),
        rec("A2", "https://mirror.org/copy", body="same")])
    m = by_id(res)
    assert m["A1"]["relationship"] == "different_url_same_exact_content"


def test_unique_url():
    res = resolve_url_groups([rec("A1", "https://ex.org/only")])
    assert by_id(res)["A1"]["relationship"] == "unique_url"


def test_malformed_goes_to_ambiguous():
    res = resolve_url_groups([rec("A1", "::: not a url")])
    assert by_id(res)["A1"]["relationship"] == "ambiguous_url_relationship"

# ------------------------------------------ determinism / incremental

def test_every_record_once_and_order_independent():
    rs = [rec("A1", "https://ex.org/1"), rec("A2", "https://ex.org/2"),
          rec("A3", "https://ex.org/3")]
    res = resolve_url_groups(rs)
    assert len(res["mapping"]) == 3
    assert res == resolve_url_groups(list(reversed(rs)))


def test_incremental_addition_keeps_group_ids():
    before = resolve_url_groups([rec("A1", "https://ex.org/story"),
                                 rec("A2", "https://ex.org/story")])
    gid = by_id(before)["A1"]["group_id"]
    after = resolve_url_groups([rec("A1", "https://ex.org/story"),
                                rec("A2", "https://ex.org/story"),
                                rec("Z9", "https://other.org/new")])
    assert by_id(after)["A1"]["group_id"] == gid


def test_version_stamped():
    assert resolve_url_groups([rec("A1", "https://x.org/a")])[
        "rule_version"] == RULE_VERSION
