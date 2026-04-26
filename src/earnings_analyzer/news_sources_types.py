"""Shared dataclasses for news fetchers and the cache layer.

Lives in its own module so that ``cache.py`` and ``news_sources.py`` can both
depend on these types without forming a circular import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


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
    viral_tweets: list[NewsItem] = field(default_factory=list)
    analysis: str = ""
