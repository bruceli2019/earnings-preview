"""User-customizable configuration for the daily news summary.

Drop a ``news_config.json`` file next to your working directory (or point
to one with ``--config``) to override defaults.  The schema is:

{
  "techmeme_count": 15,
  "output_dir": "./newsletters",
  "x_topics": [
    {"title": "My Topic", "url": "https://x.com/search?q=...", "summary": "..."}
  ],
  "ft_sections": [
    {"title": "Markets", "url": "https://www.ft.com/markets", "summary": "..."}
  ],
  "spotify_podcasts": [
    {"title": "Podcast Name", "url": "https://open.spotify.com/show/...", "summary": "..."}
  ]
}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class NewsConfig:
    """Resolved news summary configuration."""

    techmeme_count: int = 15
    output_dir: str = "./newsletters"
    x_topics: list[dict[str, str]] | None = None
    ft_sections: list[dict[str, str]] | None = None
    spotify_podcasts: list[dict[str, str]] | None = None

    @classmethod
    def load(cls, path: str | Path | None = None) -> NewsConfig:
        """Load config from a JSON file, falling back to defaults."""
        if path is None:
            path = Path("news_config.json")
        else:
            path = Path(path)

        if not path.exists():
            return cls()

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        return cls(
            techmeme_count=data.get("techmeme_count", 15),
            output_dir=data.get("output_dir", "./newsletters"),
            x_topics=data.get("x_topics"),
            ft_sections=data.get("ft_sections"),
            spotify_podcasts=data.get("spotify_podcasts"),
        )
