"""Tests for the daily news summary pipeline."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from earnings_analyzer.news_sources import (
    DailyNewsSources,
    NewsItem,
    _sanitize_url,
    get_ft_links,
    get_spotify_links,
    get_x_links,
)
from earnings_analyzer.newsletter import render_newsletter, save_newsletter
from earnings_analyzer.news_config import NewsConfig
from earnings_analyzer.news_analyzer import _build_headlines_prompt, _fallback_summary


# ---------------------------------------------------------------------------
# URL sanitization
# ---------------------------------------------------------------------------


def test_sanitize_url_valid():
    assert _sanitize_url("https://example.com/foo") == "https://example.com/foo"
    assert _sanitize_url("http://example.com") == "http://example.com"


def test_sanitize_url_rejects_bad_schemes():
    assert _sanitize_url("javascript:alert(1)") is None
    assert _sanitize_url("ftp://example.com") is None
    assert _sanitize_url("file:///etc/passwd") is None
    assert _sanitize_url("data:text/html,<h1>hi</h1>") is None


def test_sanitize_url_rejects_empty():
    assert _sanitize_url("") is None
    assert _sanitize_url("not-a-url") is None


# ---------------------------------------------------------------------------
# news_sources — curated link tests
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


def test_get_x_links_rejects_bad_url():
    custom = [{"title": "Bad", "url": "javascript:alert(1)", "summary": "s"}]
    links = get_x_links(custom_topics=custom)
    assert len(links) == 0


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
        hacker_news=[
            NewsItem(
                title="Show HN: Cool Project",
                url="https://example.com/hn",
                source="Hacker News",
                summary="Score: 200 | Comments: 50",
            ),
        ],
        reddit_finance=[
            NewsItem(
                title="Market rally continues",
                url="https://reddit.com/r/investing/post",
                source="r/investing",
                summary="Score: 500 | Comments: 120",
            ),
        ],
        sec_filings=[
            NewsItem(
                title="AAPL 8-K Filed",
                url="https://www.sec.gov/filing",
                source="SEC EDGAR",
            ),
        ],
        x_links=get_x_links(),
        ft_links=get_ft_links(),
        spotify_links=get_spotify_links(),
        analysis="## Top Stories\n- **AI funding** is the big story today.",
    )


def test_render_newsletter_contains_all_sections():
    html = render_newsletter(_make_sample_news())
    assert "Daily News Summary" in html
    assert "Saturday, April 4, 2026" in html
    assert "Techmeme Headlines" in html
    assert "Hacker News" in html
    assert "Reddit Finance" in html
    assert "SEC Filings" in html
    assert "X / Twitter" in html
    assert "Financial Times" in html
    assert "Spotify Podcasts" in html
    assert "AI Intelligence Brief" in html


def test_render_newsletter_contains_items():
    html = render_newsletter(_make_sample_news())
    assert "AI Startup Raises $1B" in html
    assert "https://example.com/ai" in html
    assert "A major AI company secures funding." in html
    assert "Show HN: Cool Project" in html
    assert "Market rally continues" in html
    assert "AAPL 8-K Filed" in html


def test_render_newsletter_contains_analysis():
    html = render_newsletter(_make_sample_news())
    assert "Top Stories" in html
    assert "AI funding" in html


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


def test_save_newsletter_rejects_path_traversal(tmp_path: Path):
    news = _make_sample_news()
    with pytest.raises(ValueError, match="Invalid filename"):
        save_newsletter(news, output_dir=tmp_path, filename="../../etc/evil.html")


def test_save_newsletter_rejects_slash_in_filename(tmp_path: Path):
    news = _make_sample_news()
    with pytest.raises(ValueError, match="Invalid filename"):
        save_newsletter(news, output_dir=tmp_path, filename="sub/file.html")


# ---------------------------------------------------------------------------
# config tests
# ---------------------------------------------------------------------------


def test_config_defaults():
    cfg = NewsConfig()
    assert cfg.techmeme_count == 15
    assert cfg.hn_count == 10
    assert cfg.reddit_count == 10
    assert cfg.sec_count == 10
    assert cfg.output_dir == "./newsletters"
    assert cfg.x_topics is None
    assert cfg.anthropic_api_key is None


def test_config_load_missing_file():
    cfg = NewsConfig.load("/nonexistent/path.json")
    assert cfg.techmeme_count == 15


def test_config_load_from_file(tmp_path: Path):
    config_file = tmp_path / "news_config.json"
    config_file.write_text(
        '{"techmeme_count": 5, "hn_count": 3, "output_dir": "./out",'
        ' "x_topics": [{"title": "Test", "url": "https://x.com/test"}]}'
    )
    cfg = NewsConfig.load(config_file)
    assert cfg.techmeme_count == 5
    assert cfg.hn_count == 3
    assert cfg.output_dir == "./out"
    assert cfg.x_topics is not None
    assert len(cfg.x_topics) == 1


def test_config_rejects_bad_techmeme_count(tmp_path: Path):
    config_file = tmp_path / "bad.json"
    config_file.write_text('{"techmeme_count": 999}')
    with pytest.raises(ValueError, match="techmeme_count"):
        NewsConfig.load(config_file)


def test_config_rejects_path_traversal_output_dir(tmp_path: Path):
    config_file = tmp_path / "bad.json"
    config_file.write_text('{"output_dir": "../../etc"}')
    with pytest.raises(ValueError, match="output_dir"):
        NewsConfig.load(config_file)


def test_config_rejects_bad_url_in_topics(tmp_path: Path):
    config_file = tmp_path / "bad.json"
    config_file.write_text(
        '{"x_topics": [{"title": "Evil", "url": "javascript:alert(1)"}]}'
    )
    with pytest.raises(ValueError, match="Invalid URL"):
        NewsConfig.load(config_file)


def test_config_rejects_bad_subreddit(tmp_path: Path):
    config_file = tmp_path / "bad.json"
    config_file.write_text('{"reddit_subreddits": ["valid", "../../bad"]}')
    with pytest.raises(ValueError, match="Invalid subreddit"):
        NewsConfig.load(config_file)


# ---------------------------------------------------------------------------
# analysis tests
# ---------------------------------------------------------------------------


def test_fallback_summary():
    news = _make_sample_news()
    summary = _fallback_summary(news)
    assert "Daily Brief" in summary
    assert "Techmeme" in summary
    assert "Hacker News" in summary
    assert "AI Startup Raises $1B" in summary
    assert "ANTHROPIC_API_KEY" in summary


def test_build_headlines_prompt():
    news = _make_sample_news()
    prompt = _build_headlines_prompt(news)
    assert "2026-04-04" in prompt
    assert "Techmeme" in prompt
    assert "Hacker News" in prompt
    assert "AI Startup Raises $1B" in prompt
    assert "intelligence brief" in prompt


def test_fallback_summary_empty_sources():
    news = DailyNewsSources(date=date(2026, 1, 1))
    summary = _fallback_summary(news)
    assert "Daily Brief" in summary
    assert "ANTHROPIC_API_KEY" in summary
