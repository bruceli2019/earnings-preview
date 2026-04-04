"""Fetch and curate news from multiple sources for the daily summary."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

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
    hacker_news: list[NewsItem] = field(default_factory=list)
    reddit_finance: list[NewsItem] = field(default_factory=list)
    sec_filings: list[NewsItem] = field(default_factory=list)
    analysis: str = ""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_USER_AGENT = (
    "Mozilla/5.0 (compatible; EarningsAnalyzer/0.1; +https://github.com)"
)

_ALLOWED_SCHEMES = {"http", "https"}

_MAX_RESPONSE_BYTES = 5_000_000  # 5 MB ceiling for any single fetch


def _sanitize_url(url: str) -> str | None:
    """Validate and return a URL, or None if suspicious."""
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return None
    if not parsed.netloc:
        return None
    return url


def _safe_get(url: str, **kwargs: object) -> httpx.Response:
    """Wrapper around httpx.get with size guard and sane defaults."""
    kwargs.setdefault("headers", {"User-Agent": _USER_AGENT})
    kwargs.setdefault("timeout", 15)
    kwargs.setdefault("follow_redirects", True)
    resp = httpx.get(url, **kwargs)
    resp.raise_for_status()
    if len(resp.content) > _MAX_RESPONSE_BYTES:
        raise ValueError("Response too large")
    return resp


# ---------------------------------------------------------------------------
# Techmeme scraper
# ---------------------------------------------------------------------------

_TECHMEME_URL = "https://www.techmeme.com/"


def fetch_techmeme_headlines(max_items: int = 15) -> list[NewsItem]:
    """Scrape top headlines from Techmeme's front page."""
    max_items = min(max(1, max_items), 100)
    try:
        resp = _safe_get(_TECHMEME_URL)
    except (httpx.HTTPError, ValueError):
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    items: list[NewsItem] = []
    seen_titles: set[str] = set()

    for cluster in soup.select(".clus"):
        link_tag = cluster.select_one("a.ourh")
        if link_tag is None:
            continue
        title = link_tag.get_text(strip=True)[:300]
        raw_url = link_tag.get("href", "")
        url = _sanitize_url(raw_url)
        if not title or not url or title in seen_titles:
            continue
        seen_titles.add(title)

        cite = cluster.select_one(".ii")
        summary = cite.get_text(strip=True)[:200] if cite else ""

        items.append(
            NewsItem(title=title, url=url, source="Techmeme", summary=summary)
        )
        if len(items) >= max_items:
            break

    return items


# ---------------------------------------------------------------------------
# Hacker News (public Firebase API — no auth)
# ---------------------------------------------------------------------------

_HN_API = "https://hacker-news.firebaseio.com/v0"


def fetch_hacker_news(max_items: int = 10, min_score: int = 50) -> list[NewsItem]:
    """Fetch top Hacker News stories above *min_score*."""
    max_items = min(max(1, max_items), 100)
    try:
        resp = _safe_get(f"{_HN_API}/topstories.json")
        story_ids: list[int] = resp.json()[:max_items * 3]
    except (httpx.HTTPError, ValueError):
        return []

    items: list[NewsItem] = []
    for sid in story_ids:
        try:
            item = _safe_get(f"{_HN_API}/item/{sid}.json").json()
        except (httpx.HTTPError, ValueError):
            continue
        if not item or item.get("type") != "story":
            continue
        score = item.get("score", 0)
        if score < min_score:
            continue
        url = _sanitize_url(item.get("url", ""))
        if url is None:
            url = f"https://news.ycombinator.com/item?id={sid}"
        items.append(
            NewsItem(
                title=item.get("title", "")[:300],
                url=url,
                source="Hacker News",
                summary=f"Score: {score} | Comments: {item.get('descendants', 0)}",
            )
        )
        if len(items) >= max_items:
            break

    return items


# ---------------------------------------------------------------------------
# Reddit finance (public JSON endpoint — no auth)
# ---------------------------------------------------------------------------

_REDDIT_SUBREDDITS = ["investing", "stocks", "finance"]


def fetch_reddit_finance(
    max_items: int = 10,
    subreddits: list[str] | None = None,
) -> list[NewsItem]:
    """Fetch top posts from finance-related subreddits."""
    max_items = min(max(1, max_items), 100)
    subs = subreddits or _REDDIT_SUBREDDITS
    items: list[NewsItem] = []
    seen: set[str] = set()

    for sub in subs:
        # Validate subreddit name (alphanumeric + underscores only)
        if not re.match(r"^[A-Za-z0-9_]{1,30}$", sub):
            continue
        try:
            resp = _safe_get(
                f"https://www.reddit.com/r/{sub}/hot.json",
                headers={
                    "User-Agent": "EarningsAnalyzer/0.1 (news summary tool)",
                },
            )
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            continue

        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            title = post.get("title", "")[:300]
            if not title or title in seen:
                continue
            seen.add(title)

            post_url = _sanitize_url(post.get("url", ""))
            if post_url is None:
                post_url = f"https://www.reddit.com{post.get('permalink', '')}"

            items.append(
                NewsItem(
                    title=title,
                    url=post_url,
                    source=f"r/{sub}",
                    summary=(
                        f"Score: {post.get('score', 0)} | "
                        f"Comments: {post.get('num_comments', 0)}"
                    ),
                )
            )
            if len(items) >= max_items:
                return items

    return items


# ---------------------------------------------------------------------------
# SEC EDGAR recent filings (RSS/Atom — no auth)
# ---------------------------------------------------------------------------

_SEC_FULL_TEXT_SEARCH = "https://efts.sec.gov/LATEST/search-index"
_SEC_FILINGS_RSS = "https://www.sec.gov/cgi-bin/browse-edgar"


def fetch_sec_filings(
    form_types: list[str] | None = None,
    max_items: int = 10,
) -> list[NewsItem]:
    """Fetch latest SEC filings (8-K, 10-Q by default) as news items."""
    max_items = min(max(1, max_items), 50)
    types = form_types or ["8-K", "10-Q"]

    items: list[NewsItem] = []
    for form in types:
        # Validate form type (alphanumeric + hyphens only)
        if not re.match(r"^[A-Za-z0-9\-/]{1,10}$", form):
            continue
        try:
            resp = _safe_get(
                _SEC_FILINGS_RSS,
                headers={"User-Agent": "EarningsAnalyzer/0.1 admin@example.com"},
                params={
                    "action": "getcompany",
                    "type": form,
                    "dateb": "",
                    "owner": "exclude",
                    "count": str(min(max_items, 40)),
                    "output": "atom",
                },
            )
        except (httpx.HTTPError, ValueError):
            continue

        try:
            root = ET.fromstring(resp.content[:_MAX_RESPONSE_BYTES])
        except ET.ParseError:
            continue

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            link_el = entry.find("atom:link", ns)
            summary_el = entry.find("atom:summary", ns)
            if title_el is None or link_el is None:
                continue
            url = _sanitize_url(link_el.get("href", ""))
            if url is None:
                continue
            items.append(
                NewsItem(
                    title=(title_el.text or "")[:300],
                    url=url,
                    source="SEC EDGAR",
                    summary=(summary_el.text or "")[:200] if summary_el is not None else "",
                )
            )
            if len(items) >= max_items:
                return items

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
            title=t["title"][:300],
            url=_sanitize_url(t["url"]) or "",
            source="X",
            summary=t.get("summary", "")[:200],
        )
        for t in topics
        if _sanitize_url(t.get("url", ""))
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
            title=s["title"][:300],
            url=_sanitize_url(s["url"]) or "",
            source="Financial Times",
            summary=s.get("summary", "")[:200],
        )
        for s in sections
        if _sanitize_url(s.get("url", ""))
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
            title=p["title"][:300],
            url=_sanitize_url(p["url"]) or "",
            source="Spotify",
            summary=p.get("summary", "")[:200],
        )
        for p in podcasts
        if _sanitize_url(p.get("url", ""))
    ]


# ---------------------------------------------------------------------------
# Aggregate all sources
# ---------------------------------------------------------------------------


def gather_daily_news(
    techmeme_count: int = 15,
    hn_count: int = 10,
    reddit_count: int = 10,
    sec_count: int = 10,
    x_topics: list[dict[str, str]] | None = None,
    ft_sections: list[dict[str, str]] | None = None,
    spotify_podcasts: list[dict[str, str]] | None = None,
    reddit_subreddits: list[str] | None = None,
    sec_form_types: list[str] | None = None,
) -> DailyNewsSources:
    """Collect news from all configured sources."""
    return DailyNewsSources(
        date=date.today(),
        techmeme_headlines=fetch_techmeme_headlines(max_items=techmeme_count),
        hacker_news=fetch_hacker_news(max_items=hn_count),
        reddit_finance=fetch_reddit_finance(
            max_items=reddit_count, subreddits=reddit_subreddits
        ),
        sec_filings=fetch_sec_filings(
            form_types=sec_form_types, max_items=sec_count
        ),
        x_links=get_x_links(custom_topics=x_topics),
        ft_links=get_ft_links(custom_sections=ft_sections),
        spotify_links=get_spotify_links(custom_podcasts=spotify_podcasts),
    )
