"""Tests for the daily news summary pipeline."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from earnings_analyzer.news_sources import (
    DailyNewsSources,
    NewsItem,
    get_ft_links,
    get_spotify_links,
    get_x_links,
)
from earnings_analyzer.newsletter import render_newsletter, save_newsletter
from earnings_analyzer.news_config import NewsConfig


# ---------------------------------------------------------------------------
# news_sources tests
# ---------------------------------------------------------------------------


def test_get_x_links_defaults():
    links = get_x_links()
    assert len(links) >= 3
    assert all(isinstance(l, NewsItem) for l in links)
    assert all(l.source == "X" for l in links)
    assert all(l.url.startswith("https://x.com/") for l in links)


def test_get_x_links_custom():
    custom = [{"title": "My Topic", "url": "https://x.com/custom", "summary": "s"}]
    links = get_x_links(custom_topics=custom)
    assert len(links) == 1
    assert links[0].title == "My Topic"


def test_get_ft_links_defaults():
    links = get_ft_links()
    assert len(links) >= 3
    assert all(l.source == "Financial Times" for l in links)
    assert all("ft.com" in l.url for l in links)


def test_get_ft_links_custom():
    custom = [{"title": "Lex", "url": "https://www.ft.com/lex"}]
    links = get_ft_links(custom_sections=custom)
    assert len(links) == 1
    assert links[0].title == "Lex"


def test_get_spotify_links_defaults():
    links = get_spotify_links()
    assert len(links) >= 3
    assert all(l.source == "Spotify" for l in links)
    assert all("spotify.com" in l.url for l in links)


def test_get_spotify_links_custom():
    custom = [{"title": "My Pod", "url": "https://open.spotify.com/show/abc"}]
    links = get_spotify_links(custom_podcasts=custom)
    assert len(links) == 1
    assert links[0].title == "My Pod"


# ---------------------------------------------------------------------------
# newsletter rendering tests
# ---------------------------------------------------------------------------


def _make_sample_news() -> DailyNewsSources:
    return DailyNewsSources(
        date=date(2026, 4, 4),
        techmeme_headlines=[
            NewsItem(
                title="AI Startup Raises $1B",
                url="https://example.com/ai",
                source="Techmeme",
                summary="A major AI company secures funding.",
            ),
            NewsItem(
                title="Apple Announces New Chip",
                url="https://example.com/apple",
                source="Techmeme",
            ),
        ],
        x_links=get_x_links(),
        ft_links=get_ft_links(),
        spotify_links=get_spotify_links(),
    )


def test_render_newsletter_contains_sections():
    html = render_newsletter(_make_sample_news())
    assert "Daily News Summary" in html
    assert "Saturday, April 4, 2026" in html
    assert "Techmeme Headlines" in html
    assert "X / Twitter" in html
    assert "Financial Times" in html
    assert "Spotify Podcasts" in html


def test_render_newsletter_contains_items():
    html = render_newsletter(_make_sample_news())
    assert "AI Startup Raises $1B" in html
    assert "https://example.com/ai" in html
    assert "A major AI company secures funding." in html


def test_render_newsletter_escapes_html():
    news = DailyNewsSources(
        date=date(2026, 1, 1),
        techmeme_headlines=[
            NewsItem(
                title='<script>alert("xss")</script>',
                url="https://example.com",
                source="Techmeme",
            )
        ],
    )
    html = render_newsletter(news)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_save_newsletter(tmp_path: Path):
    news = _make_sample_news()
    filepath = save_newsletter(news, output_dir=tmp_path)
    assert filepath.exists()
    assert filepath.name == "news-summary-2026-04-04.html"
    content = filepath.read_text(encoding="utf-8")
    assert "Daily News Summary" in content


def test_save_newsletter_custom_filename(tmp_path: Path):
    news = _make_sample_news()
    filepath = save_newsletter(news, output_dir=tmp_path, filename="custom.html")
    assert filepath.name == "custom.html"
    assert filepath.exists()


# ---------------------------------------------------------------------------
# config tests
# ---------------------------------------------------------------------------


def test_config_defaults():
    cfg = NewsConfig()
    assert cfg.techmeme_count == 15
    assert cfg.output_dir == "./newsletters"
    assert cfg.x_topics is None


def test_config_load_missing_file():
    cfg = NewsConfig.load("/nonexistent/path.json")
    assert cfg.techmeme_count == 15


def test_config_load_from_file(tmp_path: Path):
    config_file = tmp_path / "news_config.json"
    config_file.write_text(
        '{"techmeme_count": 5, "output_dir": "/tmp/news",'
        ' "x_topics": [{"title": "Test", "url": "https://x.com/test"}]}'
    )
    cfg = NewsConfig.load(config_file)
    assert cfg.techmeme_count == 5
    assert cfg.output_dir == "/tmp/news"
    assert cfg.x_topics is not None
    assert len(cfg.x_topics) == 1
