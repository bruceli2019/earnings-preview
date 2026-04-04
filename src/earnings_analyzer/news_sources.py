"""Fetch and curate news from multiple sources for the daily summary."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import httpx
from bs4 import BeautifulSoup


@dataclass
class NewsItem:
    """A single news headline with source metadata."""

    title: str
    url: str
    source: str
    summary: str = ""


@dataclass
class DailyNewsSources:
    """Aggregated news content for one day."""

    date: date
    techmeme_headlines: list[NewsItem] = field(default_factory=list)
    x_links: list[NewsItem] = field(default_factory=list)
    ft_links: list[NewsItem] = field(default_factory=list)
    spotify_links: list[NewsItem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Techmeme scraper
# ---------------------------------------------------------------------------

_TECHMEME_URL = "https://www.techmeme.com/"
_USER_AGENT = (
    "Mozilla/5.0 (compatible; EarningsAnalyzer/0.1; +https://github.com)"
)


def fetch_techmeme_headlines(max_items: int = 15) -> list[NewsItem]:
    """Scrape top headlines from Techmeme's front page."""
    try:
        resp = httpx.get(
            _TECHMEME_URL,
            headers={"User-Agent": _USER_AGENT},
            timeout=15,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    items: list[NewsItem] = []
    seen_titles: set[str] = set()

    # Techmeme wraps top stories in divs with class "clus" (cluster)
    for cluster in soup.select(".clus"):
        link_tag = cluster.select_one("a.ourh")
        if link_tag is None:
            continue
        title = link_tag.get_text(strip=True)
        url = link_tag.get("href", "")
        if not title or not url or title in seen_titles:
            continue
        seen_titles.add(title)

        # Grab optional summary snippet
        cite = cluster.select_one(".ii")
        summary = cite.get_text(strip=True)[:200] if cite else ""

        items.append(
            NewsItem(title=title, url=url, source="Techmeme", summary=summary)
        )
        if len(items) >= max_items:
            break

    return items


# ---------------------------------------------------------------------------
# Curated X (Twitter) topic links
# ---------------------------------------------------------------------------

_DEFAULT_X_TOPICS: list[dict[str, str]] = [
    {
        "title": "Trending in Tech",
        "url": "https://x.com/search?q=%23tech&src=trend_click&vertical=trends",
        "summary": "Latest trending tech discussions on X",
    },
    {
        "title": "Markets & Finance",
        "url": "https://x.com/search?q=%23markets%20OR%20%23finance&f=live",
        "summary": "Live market and finance posts",
    },
    {
        "title": "Earnings Season",
        "url": "https://x.com/search?q=%23earnings%20OR%20%23earningsseason&f=live",
        "summary": "Earnings announcements and reactions",
    },
    {
        "title": "AI & Machine Learning",
        "url": "https://x.com/search?q=%23AI%20OR%20%23MachineLearning&f=live",
        "summary": "AI and ML news and discussions",
    },
]


def get_x_links(custom_topics: list[dict[str, str]] | None = None) -> list[NewsItem]:
    """Return curated X search/topic links."""
    topics = custom_topics or _DEFAULT_X_TOPICS
    return [
        NewsItem(
            title=t["title"],
            url=t["url"],
            source="X",
            summary=t.get("summary", ""),
        )
        for t in topics
    ]


# ---------------------------------------------------------------------------
# Curated FT links
# ---------------------------------------------------------------------------

_DEFAULT_FT_SECTIONS: list[dict[str, str]] = [
    {
        "title": "FT Home",
        "url": "https://www.ft.com/",
        "summary": "Today's top stories from the Financial Times",
    },
    {
        "title": "Markets",
        "url": "https://www.ft.com/markets",
        "summary": "Global markets overview and analysis",
    },
    {
        "title": "Technology",
        "url": "https://www.ft.com/technology",
        "summary": "Tech sector news and analysis",
    },
    {
        "title": "Companies",
        "url": "https://www.ft.com/companies",
        "summary": "Corporate news, earnings, and M&A",
    },
]


def get_ft_links(custom_sections: list[dict[str, str]] | None = None) -> list[NewsItem]:
    """Return curated FT section links."""
    sections = custom_sections or _DEFAULT_FT_SECTIONS
    return [
        NewsItem(
            title=s["title"],
            url=s["url"],
            source="Financial Times",
            summary=s.get("summary", ""),
        )
        for s in sections
    ]


# ---------------------------------------------------------------------------
# Curated Spotify podcast links
# ---------------------------------------------------------------------------

_DEFAULT_SPOTIFY_PODCASTS: list[dict[str, str]] = [
    {
        "title": "Bloomberg Surveillance",
        "url": "https://open.spotify.com/show/0CkTj9Pt3kOT3kSBLgFNEE",
        "summary": "Daily markets, economics, and politics from Bloomberg",
    },
    {
        "title": "The All-In Podcast",
        "url": "https://open.spotify.com/show/2IqXAVFR4e0Bmyjsdc8QzF",
        "summary": "Tech, business, and politics with Silicon Valley insiders",
    },
    {
        "title": "Acquired",
        "url": "https://open.spotify.com/show/7Fj0XEuUQLbqnTICXBSKAE",
        "summary": "Deep dives into great technology companies and IPOs",
    },
    {
        "title": "Odd Lots (Bloomberg)",
        "url": "https://open.spotify.com/show/35IczmCnU09IEcz5P5jZ89",
        "summary": "Exploring unusual stories in finance and economics",
    },
]


def get_spotify_links(
    custom_podcasts: list[dict[str, str]] | None = None,
) -> list[NewsItem]:
    """Return curated Spotify podcast links."""
    podcasts = custom_podcasts or _DEFAULT_SPOTIFY_PODCASTS
    return [
        NewsItem(
            title=p["title"],
            url=p["url"],
            source="Spotify",
            summary=p.get("summary", ""),
        )
        for p in podcasts
    ]


# ---------------------------------------------------------------------------
# Aggregate all sources
# ---------------------------------------------------------------------------


def gather_daily_news(
    techmeme_count: int = 15,
    x_topics: list[dict[str, str]] | None = None,
    ft_sections: list[dict[str, str]] | None = None,
    spotify_podcasts: list[dict[str, str]] | None = None,
) -> DailyNewsSources:
    """Collect news from all configured sources."""
    return DailyNewsSources(
        date=date.today(),
        techmeme_headlines=fetch_techmeme_headlines(max_items=techmeme_count),
        x_links=get_x_links(custom_topics=x_topics),
        ft_links=get_ft_links(custom_sections=ft_sections),
        spotify_links=get_spotify_links(custom_podcasts=spotify_podcasts),
    )
