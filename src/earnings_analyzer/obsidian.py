"""Export daily news to Obsidian-compatible markdown notes."""

from __future__ import annotations

import re
from pathlib import Path

from earnings_analyzer.news_sources import DailyNewsSources, NewsItem

# Regex to parse a markdown link item line:  - [title](url) `source`
_ITEM_RE = re.compile(
    r"^- \[(?P<title>[^\]]+)\]\((?P<url>[^\)]+)\)"
    r"(?:\s+`(?P<source>[^`]*)`)?",
)


def _render_items(items: list[NewsItem], header: str, icon: str) -> str:
    """Render a list of news items as a markdown section."""
    if not items:
        return ""
    lines = [f"## {icon} {header}\n"]
    for item in items:
        line = f"- [{item.title}]({item.url})"
        if item.source:
            line += f" `{item.source}`"
        lines.append(line)
        if item.summary:
            lines.append(f"  - {item.summary}")
    lines.append("")
    return "\n".join(lines)


def _render_analysis(analysis: str) -> str:
    """Render the AI analysis section."""
    if not analysis:
        return ""
    return f"## 🧠 AI Intelligence Brief\n\n{analysis}\n\n"


def _parse_existing_items(text: str) -> dict[str, list[NewsItem]]:
    """Parse an existing Obsidian note and extract items grouped by section header.

    Returns a dict mapping section header (e.g. "Techmeme Headlines") to items.
    """
    sections: dict[str, list[NewsItem]] = {}
    current_section: str | None = None
    current_items: list[NewsItem] = []
    last_item: NewsItem | None = None

    for line in text.splitlines():
        # Detect section headers like "## 📰 Techmeme Headlines"
        if line.startswith("## ") and not line.startswith("## 🧠"):
            # Save previous section
            if current_section is not None:
                sections[current_section] = current_items
            # Strip the icon (first space-separated token after "## ")
            header_text = line[3:].strip()
            # Remove leading emoji/icon characters — take everything after first space
            # Icons are typically a single emoji char or HTML entity
            parts = header_text.split(" ", 1)
            current_section = parts[1] if len(parts) > 1 else parts[0]
            current_items = []
            last_item = None
            continue

        if current_section is None:
            continue

        m = _ITEM_RE.match(line)
        if m:
            last_item = NewsItem(
                title=m.group("title"),
                url=m.group("url"),
                source=m.group("source") or "",
            )
            current_items.append(last_item)
        elif line.startswith("  - ") and last_item is not None:
            # Summary line for the previous item
            last_item.summary = line[4:]

    # Save last section
    if current_section is not None:
        sections[current_section] = current_items

    return sections


def _merge_items(existing: list[NewsItem], new: list[NewsItem]) -> list[NewsItem]:
    """Merge two item lists, deduplicating by URL. Existing items come first."""
    seen_urls: set[str] = set()
    merged: list[NewsItem] = []
    for item in existing:
        if item.url not in seen_urls:
            seen_urls.add(item.url)
            merged.append(item)
    for item in new:
        if item.url not in seen_urls:
            seen_urls.add(item.url)
            merged.append(item)
    return merged


# Map section header names to DailyNewsSources field names
_SECTION_MAP: list[tuple[str, str, str]] = [
    ("Techmeme Headlines", "📰", "techmeme_headlines"),
    ("Hacker News", "📡", "hacker_news"),
    ("X / Twitter", "𝕏", "x_links"),
    ("Financial Times", "📊", "ft_links"),
    ("Podcast Episodes", "🎧", "spotify_links"),
    ("ArXiv Papers", "📑", "arxiv_papers"),
    ("HF Daily Papers", "🤗", "hf_papers"),
    ("Reddit Finance", "💬", "reddit_finance"),
    ("SEC Filings", "📜", "sec_filings"),
]

_TAG_TERMS = [
    "openai", "anthropic", "google", "meta", "microsoft",
    "gpt", "claude", "gemini", "llama", "llm",
    "transformer", "diffusion", "agent", "agi",
]


def _collect_tags(all_items: list[NewsItem]) -> list[str]:
    """Build tag list from item titles."""
    tags = ["daily-news", "ai"]
    source_tags: set[str] = set()
    for item in all_items:
        title_lower = item.title.lower()
        for term in _TAG_TERMS:
            if term in title_lower:
                source_tags.add(term)
    tags.extend(sorted(source_tags))
    return tags


def render_obsidian_note(
    news: DailyNewsSources,
    existing_sections: dict[str, list[NewsItem]] | None = None,
) -> str:
    """Generate a full Obsidian markdown note, merging with existing items."""
    date_str = news.date.isoformat()
    formatted = news.date.strftime("%A, %B %d, %Y").replace(" 0", " ")

    # Build merged sections
    section_blocks: list[str] = []
    all_items: list[NewsItem] = []
    total = 0

    # Analysis (always use latest)
    section_blocks.append(_render_analysis(news.analysis))

    for header, icon, field in _SECTION_MAP:
        new_items: list[NewsItem] = getattr(news, field, [])
        old_items = (existing_sections or {}).get(header, [])
        merged = _merge_items(old_items, new_items)
        total += len(merged)
        all_items.extend(merged)
        section_blocks.append(_render_items(merged, header, icon))

    tags = _collect_tags(all_items)
    tags_yaml = ", ".join(tags)

    frontmatter = f"""---
date: {date_str}
type: daily-news
tags: [{tags_yaml}]
sources: {total}
---
"""

    header = f"# Daily AI & Tech News — {formatted}\n\n"
    from datetime import date as _date
    prev = _date.fromordinal(news.date.toordinal() - 1)
    nav = f"[[{date_str} |Today]] · [[{prev.isoformat()}|← Previous]]\n\n"

    body = "".join(s for s in section_blocks if s)

    return frontmatter + header + nav + body


def export_to_obsidian(
    news: DailyNewsSources,
    vault_path: str | Path,
) -> Path:
    """Export the daily news to a markdown note in the Obsidian vault.

    If a note for the same date already exists, merges new items into it
    and deduplicates by URL. Creates a ``Daily Notes/`` subfolder.
    Returns the path to the written file.
    """
    vault = Path(vault_path).resolve()
    daily_dir = vault / "Daily Notes"
    daily_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{news.date.isoformat()}.md"
    filepath = (daily_dir / filename).resolve()

    # Path traversal guard
    if not str(filepath).startswith(str(vault)):
        raise ValueError("Filename escapes vault directory")

    # Parse existing note if present
    existing_sections: dict[str, list[NewsItem]] | None = None
    if filepath.exists():
        existing_text = filepath.read_text(encoding="utf-8")
        existing_sections = _parse_existing_items(existing_text)

    filepath.write_text(
        render_obsidian_note(news, existing_sections=existing_sections),
        encoding="utf-8",
    )
    return filepath
