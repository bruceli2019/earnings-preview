"""AI-powered analysis layer using Claude API.

Processes raw headlines into an opinionated daily brief that identifies:
- Signal vs. noise — what actually matters today
- Second-order effects — downstream consequences of today's events
- Third-order effects — longer-term systemic implications
- Cross-source patterns — themes that appear across multiple sources
"""

from __future__ import annotations

import os

from earnings_analyzer.news_sources import DailyNewsSources, NewsItem


_SYSTEM_PROMPT = """\
You are an expert financial and technology analyst writing a concise daily
intelligence brief.  Your readers are sophisticated investors and technologists
who need signal, not noise.

Rules:
1. Lead with the 3-5 stories that ACTUALLY matter today.  Ignore filler.
2. For each key story, identify at least one second-order effect (what happens
   next as a consequence) and, where relevant, a third-order effect (systemic
   or long-term implication).
3. Call out cross-source patterns: if the same theme appears on Techmeme,
   Hacker News, AND Reddit, that's a signal worth highlighting.
4. Be opinionated — take a stance on what's signal vs. noise.
5. Keep the whole brief under 800 words.
6. Use markdown formatting with headers and bullet points.
7. End with a "Watch List" of 2-3 developing stories to track over the
   coming days/weeks.
"""


def _build_headlines_prompt(news: DailyNewsSources) -> str:
    """Assemble all headlines into a structured prompt for Claude."""
    sections: list[str] = []

    def _fmt(label: str, items: list[NewsItem]) -> None:
        if not items:
            return
        lines = [f"## {label}"]
        for it in items:
            line = f"- {it.title}"
            if it.summary:
                line += f" — {it.summary}"
            line += f"  [{it.source}]({it.url})"
            lines.append(line)
        sections.append("\n".join(lines))

    _fmt("Techmeme", news.techmeme_headlines)
    _fmt("Hacker News", news.hacker_news)
    _fmt("Reddit Finance", news.reddit_finance)
    _fmt("SEC Filings", news.sec_filings)
    _fmt("X / Twitter Links", news.x_links)
    _fmt("Financial Times Links", news.ft_links)

    all_headlines = "\n\n".join(sections)
    return (
        f"Today is {news.date.isoformat()}.  Here are the raw headlines and "
        f"links I've gathered from multiple sources:\n\n{all_headlines}\n\n"
        "Write your daily intelligence brief now."
    )


def analyze_news(
    news: DailyNewsSources,
    api_key: str | None = None,
) -> str:
    """Send headlines to Claude and return an opinionated analysis.

    Falls back to a simple summary if no API key is available or the
    request fails.
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return _fallback_summary(news)

    try:
        import anthropic
    except ImportError:
        return _fallback_summary(news)

    try:
        client = anthropic.Anthropic(api_key=key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": _build_headlines_prompt(news)},
            ],
        )
        return message.content[0].text
    except Exception:
        return _fallback_summary(news)


def _fallback_summary(news: DailyNewsSources) -> str:
    """Plain-text summary when Claude API is unavailable."""
    parts: list[str] = [f"# Daily Brief — {news.date.isoformat()}\n"]

    counts = [
        ("Techmeme", len(news.techmeme_headlines)),
        ("Hacker News", len(news.hacker_news)),
        ("Reddit", len(news.reddit_finance)),
        ("SEC Filings", len(news.sec_filings)),
    ]
    parts.append(
        "Sources scanned: "
        + ", ".join(f"{n} ({c})" for n, c in counts if c)
        + "\n"
    )

    if news.techmeme_headlines:
        parts.append("## Top Headlines")
        for item in news.techmeme_headlines[:5]:
            parts.append(f"- **{item.title}**")
            if item.summary:
                parts.append(f"  {item.summary}")

    if news.hacker_news:
        parts.append("\n## Hacker News Highlights")
        for item in news.hacker_news[:5]:
            parts.append(f"- **{item.title}** ({item.summary})")

    parts.append(
        "\n*AI analysis unavailable — set ANTHROPIC_API_KEY or "
        "anthropic_api_key in news_config.json for opinionated briefing.*"
    )
    return "\n".join(parts)
