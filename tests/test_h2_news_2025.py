"""Leakage guards for the 2025 H2 news collection (offline)."""

from forecast import h2_news_2025 as h


def test_fetch_reads_only_the_archived_capture(tmp_path, monkeypatch):
    # The live page may have been edited after polling day, so only the
    # pre-polling-day Wayback capture may ever be requested.
    calls = []

    class Resp:
        status_code, text = 200, "<html></html>"

    monkeypatch.setattr(h, "CACHE", tmp_path)
    monkeypatch.setattr(h, "http_get",
                        lambda url, archive=False: calls.append(url) or Resp())
    h.fetch_archived({"outlet": "x", "timestamp": "20250410120000",
                      "url": "https://www.devonlive.com/news/a-reform-1"})
    assert calls == ["https://web.archive.org/web/20250410120000/"
                     "https://www.devonlive.com/news/a-reform-1"]


def test_capture_window_ends_before_polling_day():
    assert h.CAP_END.isoformat() < "2025-05-01"
    assert h.PUB_END.isoformat() < "2025-05-01"


def test_publication_window():
    assert h.in_window({"published_date": "2025-04-01"})
    assert h.in_window({"published_date": "2025-04-30"})
    assert not h.in_window({"published_date": "2025-03-31"})
    assert not h.in_window({"published_date": "2025-05-01"})
    assert not h.in_window({"published_date": None})


def test_politics_slug_filter():
    assert h.SLUG.search("/news/reform-uk-candidate-devon-10123456")
    assert h.SLUG.search("/news/county-council-election-2025-123")
    assert not h.SLUG.search("/news/man-arrested-after-crash-10123456")


def test_every_council_has_an_outlet_candidate():
    assert len(h.CANDIDATES) == 23
    assert all(h.CANDIDATES.values())
