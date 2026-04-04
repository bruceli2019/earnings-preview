"""User-customizable configuration for the daily news summary.

Drop a ``news_config.json`` file next to your working directory (or point
to one with ``--config``) to override defaults.  The schema is:

{
  "techmeme_count": 15,
  "hn_count": 10,
  "reddit_count": 10,
  "sec_count": 10,
  "output_dir": "./newsletters",
  "anthropic_api_key": null,
  "x_topics": [
    {"title": "My Topic", "url": "https://x.com/search?q=...", "summary": "..."}
  ],
  "ft_sections": [
    {"title": "Markets", "url": "https://www.ft.com/markets", "summary": "..."}
  ],
  "spotify_podcasts": [
    {"title": "Podcast Name", "url": "https://open.spotify.com/show/...", "summary": "..."}
  ],
  "reddit_subreddits": ["investing", "stocks"],
  "sec_form_types": ["8-K", "10-Q"]
}
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


def _validate_url(url: str) -> None:
    """Raise ValueError if *url* is not a valid http(s) URL."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Invalid URL (must be http/https): {url}")


def _validate_link_list(items: list | None, label: str) -> None:
    """Validate a list of {title, url, ...} dicts from config."""
    if items is None:
        return
    if not isinstance(items, list):
        raise ValueError(f"{label} must be a list")
    for i, entry in enumerate(items):
        if not isinstance(entry, dict):
            raise ValueError(f"{label}[{i}] must be a dict")
        if "title" not in entry or "url" not in entry:
            raise ValueError(f"{label}[{i}] must have 'title' and 'url'")
        _validate_url(entry["url"])


@dataclass
class NewsConfig:
    """Resolved news summary configuration."""

    techmeme_count: int = 15
    hn_count: int = 10
    reddit_count: int = 10
    sec_count: int = 10
    output_dir: str = "./newsletters"
    anthropic_api_key: str | None = None
    x_topics: list[dict[str, str]] | None = None
    ft_sections: list[dict[str, str]] | None = None
    spotify_podcasts: list[dict[str, str]] | None = None
    reddit_subreddits: list[str] | None = None
    sec_form_types: list[str] | None = None

    @classmethod
    def load(cls, path: str | Path | None = None) -> NewsConfig:
        """Load config from a JSON file, falling back to defaults."""
        if path is None:
            path = Path("news_config.json")
        else:
            path = Path(path)

        if not path.exists():
            return cls()

        raw = path.read_text(encoding="utf-8")
        if len(raw) > 1_000_000:
            raise ValueError("Config file too large (>1 MB)")
        data = json.loads(raw)

        # --- validate scalars ---
        techmeme_count = data.get("techmeme_count", 15)
        if not isinstance(techmeme_count, int) or not 1 <= techmeme_count <= 100:
            raise ValueError(f"techmeme_count must be 1-100, got {techmeme_count}")

        hn_count = data.get("hn_count", 10)
        if not isinstance(hn_count, int) or not 1 <= hn_count <= 100:
            raise ValueError(f"hn_count must be 1-100, got {hn_count}")

        reddit_count = data.get("reddit_count", 10)
        if not isinstance(reddit_count, int) or not 1 <= reddit_count <= 100:
            raise ValueError(f"reddit_count must be 1-100, got {reddit_count}")

        sec_count = data.get("sec_count", 10)
        if not isinstance(sec_count, int) or not 1 <= sec_count <= 50:
            raise ValueError(f"sec_count must be 1-50, got {sec_count}")

        output_dir = data.get("output_dir", "./newsletters")
        if not isinstance(output_dir, str) or ".." in output_dir:
            raise ValueError(f"Invalid output_dir: {output_dir}")

        # --- validate link lists ---
        _validate_link_list(data.get("x_topics"), "x_topics")
        _validate_link_list(data.get("ft_sections"), "ft_sections")
        _validate_link_list(data.get("spotify_podcasts"), "spotify_podcasts")

        # --- validate string lists ---
        reddit_subs = data.get("reddit_subreddits")
        if reddit_subs is not None:
            if not isinstance(reddit_subs, list):
                raise ValueError("reddit_subreddits must be a list")
            for s in reddit_subs:
                if not isinstance(s, str) or not re.match(r"^[A-Za-z0-9_]{1,30}$", s):
                    raise ValueError(f"Invalid subreddit name: {s}")

        sec_forms = data.get("sec_form_types")
        if sec_forms is not None:
            if not isinstance(sec_forms, list):
                raise ValueError("sec_form_types must be a list")
            for f in sec_forms:
                if not isinstance(f, str) or not re.match(r"^[A-Za-z0-9\-/]{1,10}$", f):
                    raise ValueError(f"Invalid SEC form type: {f}")

        return cls(
            techmeme_count=techmeme_count,
            hn_count=hn_count,
            reddit_count=reddit_count,
            sec_count=sec_count,
            output_dir=output_dir,
            anthropic_api_key=data.get("anthropic_api_key"),
            x_topics=data.get("x_topics"),
            ft_sections=data.get("ft_sections"),
            spotify_podcasts=data.get("spotify_podcasts"),
            reddit_subreddits=reddit_subs,
            sec_form_types=sec_forms,
        )
