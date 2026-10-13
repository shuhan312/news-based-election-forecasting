"""Tests for the ward-level coverage probe (forecast.ward_coverage)."""

from forecast import ward_coverage as wc


def test_article_ids_from_each_outlet_url_style():
    assert wc.article_id("https://www.getsurrey.co.uk/news/surrey-news/x-20290053") == 20290053
    assert wc.article_id("https://www.bbc.co.uk/news/uk-england-kent-56962571") == 56962571
    assert wc.article_id("https://www.kentonline.co.uk/dover/news/blooming-243433/") == 243433
    assert wc.article_id("https://www.kentlive.news/news/kent-news/x-5107351.amp") == 5107351
    assert wc.article_id("https://www.surreycomet.co.uk/news/19279019.some-slug/") == 19279019
    assert wc.article_id("https://www.kentonline.co.uk/whats-on/") is None


def test_place_tokens_drop_generic_words():
    assert wc.place_tokens("Bagshot, Windlesham & Chobham") == \
        ["bagshot", "windlesham", "chobham"]
    assert wc.place_tokens("Tunbridge Wells East") == ["tunbridge wells"]
    assert wc.place_tokens("Ash") == []              # too short, too common


CONTESTS = [{"county": "kent", "ballot": "b1", "label": "Shere Valley",
             "candidates": ["Jane Doe", "Bob Roe"]},
            {"county": "kent", "ballot": "b2", "label": "Gomshall",
             "candidates": ["Al Smith", "Cy Young"]}]


def art(text, headline=""):
    return {"council": "kent", "url": text[:20], "headline": headline,
            "text": text}


def test_candidate_names_count_anywhere_places_only_in_political_articles():
    articles = [
        art("Jane Doe opened a fete."),                       # C for b1
        art("Crash closes the road in Gomshall."),            # not political
        art("Shere council plans approved by councillors."),  # P for b1
    ]
    out = wc.coverage(CONTESTS, articles)
    div = out["per_division"]
    assert div["b1"] == {"label": "Shere Valley", "C": 1, "P": 1}
    assert div["b2"]["P"] == 0                 # the crash story does not count
    assert out["pooled"]["W1_any"] == 0.5


def test_single_word_names_are_never_matched():
    contests = [dict(CONTESTS[0], candidates=["Cher"])]
    out = wc.coverage(contests, [art("Cher sang at the council.")])
    assert out["per_division"]["b1"]["C"] == 0


# --- follow-up: coverage by candidate type ----------------------------------------------

def test_candidates_are_classified_by_2017_history_and_party():
    from forecast import candidate_coverage as cc
    c2017 = [{"person_id": 1, "elected": True}, {"person_id": 2, "elected": False}]
    c2021 = [{"person_id": 1, "party": "PP52", "name": "A B"},
             {"person_id": 2, "party": "PP63", "name": "C D"},
             {"person_id": 3, "party": "PP7931", "name": "E F"}]
    tagged = {c["person_id"]: c for c in cc.classify(c2021, c2017)}
    assert tagged[1]["history"] == "incumbent" and not tagged[1]["minor"]
    assert tagged[2]["history"] == "past" and tagged[2]["minor"]
    assert tagged[3]["history"] == "new" and tagged[3]["insurgent"]


def test_named_share_counts_full_names_only():
    from forecast import candidate_coverage as cc
    cands = [{"person_id": 1, "name": "Jane Doe"},
             {"person_id": 2, "name": "Prince"}]
    arts = [{"headline": "", "text": "Jane Doe and Prince spoke."}]
    counts = cc.named_counts(cands, arts)
    assert counts[1] == 1 and 2 not in counts
    assert cc.share_named(cands, counts)["named_share"] == 0.5
