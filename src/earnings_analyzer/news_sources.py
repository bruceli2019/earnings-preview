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
    arxiv_papers: list[NewsItem] = field(default_factory=list)
    hf_papers: list[NewsItem] = field(default_factory=list)
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


def fetch_techmeme_headlines(max_items: int = 5) -> list[NewsItem]:
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


def fetch_hacker_news(max_items: int = 5, min_score: int = 50) -> list[NewsItem]:
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
# X / Twitter — fetch actual posts (API v2 > Playwright > syndication)
# ---------------------------------------------------------------------------

_DEFAULT_X_ACCOUNTS = [
    "OpenAI",
    "AnthropicAI",
    "GoogleDeepMind",
]

_X_API_SEARCH = "https://api.twitter.com/2/tweets/search/recent"
_SYNDICATION_URL = "https://syndication.twitter.com/srv/timeline-profile/screen-name"


def _fetch_x_via_api(
    accounts: list[str],
    bearer_token: str,
    max_per_account: int,
) -> list[NewsItem]:
    """Fetch tweets via X API v2 (requires bearer token)."""
    items: list[NewsItem] = []
    for handle in accounts:
        if not re.match(r"^[A-Za-z0-9_]{1,30}$", handle):
            continue
        try:
            resp = _safe_get(
                _X_API_SEARCH,
                headers={"Authorization": f"Bearer {bearer_token}"},
                params={
                    "query": f"from:{handle} -is:retweet",
                    "max_results": str(min(max_per_account, 10)),
                    "tweet.fields": "text,created_at,author_id",
                },
            )
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            continue

        for tweet in data.get("data", [])[:max_per_account]:
            tweet_id = tweet.get("id", "")
            text = tweet.get("text", "")[:300]
            if not text:
                continue
            items.append(
                NewsItem(
                    title=text,
                    url=f"https://x.com/{handle}/status/{tweet_id}",
                    source=f"@{handle}",
                    summary="",
                )
            )
    return items


def _fetch_x_via_browser(
    accounts: list[str],
    max_per_account: int,
) -> list[NewsItem]:
    """Fetch tweets using a headless browser (Playwright).

    Renders the X SPA fully, bypassing JS-rendering requirements.
    Requires ``pip install playwright && playwright install chromium``.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    items: list[NewsItem] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
            )

            for handle in accounts:
                if not re.match(r"^[A-Za-z0-9_]{1,30}$", handle):
                    continue
                try:
                    page.goto(
                        f"https://x.com/{handle}",
                        wait_until="domcontentloaded",
                        timeout=30_000,
                    )
                    # Wait for tweet articles to render (X is an SPA)
                    page.wait_for_selector(
                        'article[data-testid="tweet"]',
                        timeout=15_000,
                    )
                except Exception:
                    continue

                tweets = page.query_selector_all(
                    'article[data-testid="tweet"]'
                )
                count = 0
                for tweet_el in tweets:
                    if count >= max_per_account:
                        break
                    # Extract tweet text
                    text_el = tweet_el.query_selector(
                        '[data-testid="tweetText"]'
                    )
                    if not text_el:
                        continue
                    text = text_el.inner_text()[:300].strip()
                    if not text:
                        continue

                    # Extract tweet URL from the timestamp link
                    time_link = tweet_el.query_selector('a[href*="/status/"]')
                    if time_link:
                        href = time_link.get_attribute("href") or ""
                        url = f"https://x.com{href}" if href.startswith("/") else href
                    else:
                        url = f"https://x.com/{handle}"

                    items.append(
                        NewsItem(
                            title=text,
                            url=url,
                            source=f"@{handle}",
                            summary="",
                        )
                    )
                    count += 1

            browser.close()
    except Exception:
        pass

    return items


def _fetch_x_via_syndication(
    accounts: list[str],
    max_per_account: int,
) -> list[NewsItem]:
    """Last-resort fallback via X syndication embed endpoint."""
    items: list[NewsItem] = []
    for handle in accounts:
        if not re.match(r"^[A-Za-z0-9_]{1,30}$", handle):
            continue
        try:
            resp = _safe_get(
                f"{_SYNDICATION_URL}/{handle}",
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"
                    ),
                    "Referer": "https://platform.twitter.com/",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
        except (httpx.HTTPError, ValueError):
            continue

        soup = BeautifulSoup(resp.text, "lxml")
        count = 0
        for tweet_div in soup.select("[data-tweet-id]"):
            text_el = tweet_div.select_one(".timeline-Tweet-text")
            if text_el is None:
                continue
            text = text_el.get_text(strip=True)[:300]
            if not text:
                continue
            tweet_id = tweet_div.get("data-tweet-id", "")
            items.append(
                NewsItem(
                    title=text,
                    url=f"https://x.com/{handle}/status/{tweet_id}",
                    source=f"@{handle}",
                    summary="",
                )
            )
            count += 1
            if count >= max_per_account:
                break

    return items


def fetch_x_posts(
    accounts: list[str] | None = None,
    bearer_token: str | None = None,
    max_per_account: int = 3,
) -> list[NewsItem]:
    """Fetch recent posts from X accounts.

    Tries in order: API v2 (bearer token) > Playwright (headless browser)
    > syndication embed (rate-limited fallback).
    """
    accts = accounts or _DEFAULT_X_ACCOUNTS
    if bearer_token:
        return _fetch_x_via_api(accts, bearer_token, max_per_account)
    # Try headless browser (Playwright) if installed
    items = _fetch_x_via_browser(accts, max_per_account)
    if items:
        return items
    # Last resort: syndication
    return _fetch_x_via_syndication(accts, max_per_account)


# ---------------------------------------------------------------------------
# ArXiv — latest AI/ML research papers (free API, no auth)
# ---------------------------------------------------------------------------

_ARXIV_API = "http://export.arxiv.org/api/query"
_ARXIV_CATEGORIES = "cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.CL"


def fetch_arxiv_papers(max_items: int = 5) -> list[NewsItem]:
    """Fetch the latest AI/ML papers from ArXiv."""
    max_items = min(max(1, max_items), 50)
    try:
        # Build URL manually — httpx params encoding breaks ArXiv's `+` OR syntax
        url = (
            f"{_ARXIV_API}?search_query={_ARXIV_CATEGORIES}"
            f"&sortBy=submittedDate&sortOrder=descending"
            f"&max_results={max_items}"
        )
        resp = _safe_get(url, timeout=15)
    except (httpx.HTTPError, ValueError):
        return []

    try:
        root = ET.fromstring(resp.content[:_MAX_RESPONSE_BYTES])
    except ET.ParseError:
        return []

    ns = {"a": "http://www.w3.org/2005/Atom"}
    items: list[NewsItem] = []
    for entry in root.findall("a:entry", ns)[:max_items]:
        title = (entry.findtext("a:title", "", ns) or "").strip()
        title = re.sub(r"\s+", " ", title)[:300]
        link = entry.findtext("a:id", "", ns) or ""
        summary = (entry.findtext("a:summary", "", ns) or "").strip()
        summary = re.sub(r"\s+", " ", summary)[:200]
        if not title or not link:
            continue
        items.append(
            NewsItem(title=title, url=link, source="ArXiv", summary=summary)
        )

    return items


# ---------------------------------------------------------------------------
# Hugging Face Daily Papers — trending ML research (free API, no auth)
# ---------------------------------------------------------------------------

_HF_PAPERS_API = "https://huggingface.co/api/daily_papers"


def fetch_hf_papers(max_items: int = 5) -> list[NewsItem]:
    """Fetch trending papers from Hugging Face Daily Papers."""
    max_items = min(max(1, max_items), 50)
    try:
        resp = _safe_get(_HF_PAPERS_API, timeout=15)
        papers = resp.json()
    except (httpx.HTTPError, ValueError):
        return []

    if not isinstance(papers, list):
        return []

    items: list[NewsItem] = []
    for entry in papers[:max_items]:
        paper = entry.get("paper", {})
        title = (paper.get("title") or "")[:300]
        paper_id = paper.get("id", "")
        summary = (paper.get("summary") or "")[:200]
        upvotes = paper.get("upvotes", 0)
        if not title or not paper_id:
            continue
        url = f"https://huggingface.co/papers/{paper_id}"
        items.append(
            NewsItem(
                title=title,
                url=url,
                source="HF Papers",
                summary=f"Upvotes: {upvotes} | {summary}" if summary else "",
            )
        )

    return items


# ---------------------------------------------------------------------------
# Financial Times — fetch real articles via RSS feeds
# ---------------------------------------------------------------------------

_DEFAULT_FT_FEEDS: list[dict[str, str]] = [
    {
        "title": "Technology",
        "url": "https://www.ft.com/technology?format=rss",
    },
    {
        "title": "Artificial Intelligence",
        "url": "https://www.ft.com/artificial-intelligence?format=rss",
    },
]


def fetch_ft_articles(
    sections: list[dict[str, str]] | None = None,
    max_per_section: int = 5,
) -> list[NewsItem]:
    """Fetch actual FT article headlines via public RSS feeds."""
    ft_feeds = sections or _DEFAULT_FT_FEEDS
    items: list[NewsItem] = []
    seen: set[str] = set()

    for feed_info in ft_feeds:
        feed_url = feed_info.get("url", "")
        # Ensure RSS format param is present
        if "format=rss" not in feed_url:
            feed_url = feed_url.rstrip("/") + "?format=rss"
        safe_url = _sanitize_url(feed_url)
        if not safe_url:
            continue

        try:
            resp = _safe_get(safe_url)
        except (httpx.HTTPError, ValueError):
            continue

        try:
            root = ET.fromstring(resp.content[:_MAX_RESPONSE_BYTES])
        except ET.ParseError:
            continue

        count = 0
        for item_el in root.findall(".//item"):
            title = (item_el.findtext("title") or "").strip()[:300]
            link = (item_el.findtext("link") or "").strip()
            desc = (item_el.findtext("description") or "").strip()[:200]
            if not title or not link or title in seen:
                continue
            article_url = _sanitize_url(link)
            if not article_url:
                continue
            seen.add(title)

            items.append(
                NewsItem(
                    title=title,
                    url=article_url,
                    source=f"FT {feed_info.get('title', '')}",
                    summary=desc,
                )
            )
            count += 1
            if count >= max_per_section:
                break

    return items


# ---------------------------------------------------------------------------
# Spotify — fetch actual episodes with descriptions
# ---------------------------------------------------------------------------

_DEFAULT_SPOTIFY_SHOWS: list[dict[str, str]] = [
    {
        "title": "The All-In Podcast",
        "url": "https://open.spotify.com/show/2IqXAVFR4e0Bmyjsdc8QzF",
    },
    {
        "title": "Acquired",
        "url": "https://open.spotify.com/show/7Fj0XEuUQLbqnTICXBSKAE",
    },
    {
        "title": "Lex Fridman Podcast",
        "url": "https://open.spotify.com/show/2MAi0BvDc6GTFvKFPXnkCL",
    },
    {
        "title": "Odd Lots (Bloomberg)",
        "url": "https://open.spotify.com/show/35IczmCnU09IEcz5P5jZ89",
    },
]

_SPOTIFY_OEMBED = "https://open.spotify.com/oembed"


def fetch_spotify_episodes(
    shows: list[dict[str, str]] | None = None,
    max_episodes: int = 1,
) -> list[NewsItem]:
    """Fetch the latest episode from each Spotify podcast with description.

    Scrapes the show page for episode links and uses oEmbed for metadata.
    """
    podcast_list = shows or _DEFAULT_SPOTIFY_SHOWS
    items: list[NewsItem] = []

    for show in podcast_list:
        show_url = _sanitize_url(show.get("url", ""))
        if not show_url:
            continue
        show_title = show.get("title", "Podcast")

        try:
            resp = _safe_get(show_url)
        except (httpx.HTTPError, ValueError):
            continue

        soup = BeautifulSoup(resp.text, "lxml")

        # Spotify embeds episode data in JSON-LD or meta tags
        import json as _json

        episode_links: list[tuple[str, str, str]] = []  # (url, title, desc)

        # Try parsing JSON-LD for episode data
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                ld = _json.loads(script.string or "")
            except (ValueError, TypeError):
                continue
            # PodcastSeries schema includes episodes
            episodes = []
            if isinstance(ld, dict):
                episodes = ld.get("episode", [])
                if isinstance(episodes, dict):
                    episodes = [episodes]
            for ep in episodes[:max_episodes]:
                ep_url = ep.get("url", "")
                ep_title = ep.get("name", "")[:300]
                ep_desc = ep.get("description", "")[:500]
                if ep_url and ep_title:
                    episode_links.append((ep_url, ep_title, ep_desc))

        # Fallback: look for episode links in the page HTML
        if not episode_links:
            for link in soup.select('a[href*="/episode/"]'):
                href = link.get("href", "")
                title = link.get_text(strip=True)[:300]
                if href.startswith("/"):
                    href = f"https://open.spotify.com{href}"
                ep_url = _sanitize_url(href)
                if ep_url and title and len(title) > 5:
                    episode_links.append((ep_url, title, ""))
                    if len(episode_links) >= max_episodes:
                        break

        # Fallback: use oEmbed to get at least the show description
        if not episode_links:
            try:
                oembed_resp = _safe_get(
                    _SPOTIFY_OEMBED, params={"url": show_url}
                )
                oembed = oembed_resp.json()
                items.append(
                    NewsItem(
                        title=f"{show_title}: Latest Episode",
                        url=show_url,
                        source="Spotify",
                        summary=oembed.get("title", "")[:200],
                    )
                )
            except (httpx.HTTPError, ValueError, KeyError):
                pass
            continue

        for ep_url, ep_title, ep_desc in episode_links:
            # If we don't have a description, try fetching the episode page
            if not ep_desc:
                try:
                    ep_resp = _safe_get(ep_url)
                    ep_soup = BeautifulSoup(ep_resp.text, "lxml")
                    # Check meta description
                    meta_desc = ep_soup.select_one('meta[name="description"]')
                    if meta_desc:
                        ep_desc = meta_desc.get("content", "")[:500]
                    # Check JSON-LD
                    if not ep_desc:
                        for script in ep_soup.select(
                            'script[type="application/ld+json"]'
                        ):
                            try:
                                ld = _json.loads(script.string or "")
                            except (ValueError, TypeError):
                                continue
                            if isinstance(ld, dict) and ld.get("description"):
                                ep_desc = ld["description"][:500]
                                break
                except (httpx.HTTPError, ValueError):
                    pass

            items.append(
                NewsItem(
                    title=f"{show_title}: {ep_title}",
                    url=ep_url,
                    source="Spotify",
                    summary=ep_desc[:200] if ep_desc else "",
                )
            )

    return items


# ---------------------------------------------------------------------------
# Aggregate all sources
# ---------------------------------------------------------------------------


def gather_daily_news(
    techmeme_count: int = 5,
    hn_count: int = 5,
    reddit_count: int = 10,
    sec_count: int = 10,
    arxiv_count: int = 5,
    hf_count: int = 5,
    x_accounts: list[str] | None = None,
    x_bearer_token: str | None = None,
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
        x_links=fetch_x_posts(accounts=x_accounts, bearer_token=x_bearer_token),
        ft_links=fetch_ft_articles(sections=ft_sections),
        spotify_links=fetch_spotify_episodes(shows=spotify_podcasts),
        arxiv_papers=fetch_arxiv_papers(max_items=arxiv_count),
        hf_papers=fetch_hf_papers(max_items=hf_count),
    )
