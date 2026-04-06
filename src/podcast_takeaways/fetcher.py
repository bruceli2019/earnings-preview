"""RSS feed parsing and audio download for podcast episodes."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

import feedparser
import requests


@dataclass
class Episode:
    """Metadata for a single podcast episode."""

    title: str
    url: str  # audio enclosure URL
    published: str
    description: str
    duration: str = ""

    @property
    def slug(self) -> str:
        """Filesystem-safe slug derived from the title."""
        s = re.sub(r"[^\w\s-]", "", self.title.lower())
        s = re.sub(r"[\s_]+", "-", s).strip("-")
        return s[:80] or "episode"


def parse_feed(rss_url: str) -> list[Episode]:
    """Parse an RSS feed and return episodes sorted newest-first."""
    feed = feedparser.parse(rss_url)
    episodes: list[Episode] = []

    for entry in feed.entries:
        audio_url = ""
        for link in entry.get("links", []):
            if link.get("type", "").startswith("audio/") or link.get(
                "href", ""
            ).endswith(".mp3"):
                audio_url = link["href"]
                break
        # Also check enclosures
        if not audio_url:
            for enc in entry.get("enclosures", []):
                if enc.get("type", "").startswith("audio/") or enc.get(
                    "href", ""
                ).endswith(".mp3"):
                    audio_url = enc["href"]
                    break

        if not audio_url:
            continue

        duration = entry.get("itunes_duration", "")

        episodes.append(
            Episode(
                title=entry.get("title", "Untitled"),
                url=audio_url,
                published=entry.get("published", ""),
                description=entry.get("summary", ""),
                duration=duration,
            )
        )

    return episodes


def select_episode(
    episodes: list[Episode],
    number: int | None = None,
    search: str | None = None,
) -> Episode:
    """Select an episode by number (1-indexed) or title search."""
    if not episodes:
        raise ValueError("No episodes found in the feed.")

    if number is not None:
        if not 1 <= number <= len(episodes):
            raise ValueError(
                f"Episode {number} out of range (1-{len(episodes)})."
            )
        return episodes[number - 1]

    if search is not None:
        query = search.lower()
        for ep in episodes:
            if query in ep.title.lower():
                return ep
        raise ValueError(f"No episode matching '{search}' found.")

    # Default: latest
    return episodes[0]


def download_audio(
    url: str,
    dest: Path,
    retries: int = 1,
) -> Path:
    """Download audio file to *dest*, retrying once on failure."""
    dest.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1 + retries):
        try:
            resp = requests.get(
                url,
                stream=True,
                timeout=60,
                allow_redirects=True,
                headers={"User-Agent": "PodcastTakeaways/0.1"},
            )
            resp.raise_for_status()

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        print(
                            f"\r  Downloading: {pct}% "
                            f"({downloaded // 1024 // 1024}MB/"
                            f"{total // 1024 // 1024}MB)",
                            end="",
                            flush=True,
                        )
            print()
            return dest

        except (requests.RequestException, OSError) as e:
            if attempt < retries:
                print(f"  Download failed ({e}), retrying in 5s...")
                time.sleep(5)
            else:
                raise RuntimeError(
                    f"Failed to download audio after {1 + retries} attempts: {e}"
                ) from e

    raise RuntimeError("Unreachable")
