"""AI-powered analysis layer using Gemini (free tier).

Processes raw headlines into an opinionated daily brief that identifies:
- Signal vs. noise — what actually matters today
- Second-order effects — downstream consequences of today's events
- Third-order effects — longer-term systemic implications
- Cross-source patterns — themes that appear across multiple sources
"""

from __future__ import annotations

import os
import time

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
    """Assemble all headlines into a structured prompt."""
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


def _call_gemini(system: str, user_message: str, max_retries: int = 3) -> str:
    """Send a message to Gemini with retry on rate limits."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    from google import genai

    client = genai.Client(api_key=api_key)

    for attempt in range(1, max_retries + 1):
        try:
            resp = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=user_message,
                config={
                    "system_instruction": system,
                    "max_output_tokens": 2048,
                },
            )
            return resp.text
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = 30 * attempt
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Gemini rate limit exceeded after retries.")


def analyze_news(
    news: DailyNewsSources,
    api_key: str | None = None,
) -> str:
    """Send headlines to Gemini and return an opinionated analysis.

    Falls back to a simple summary if no API key is available or the
    request fails.  The *api_key* parameter is accepted for backwards
    compatibility but ignored — uses GEMINI_API_KEY env var.
    """
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return _fallback_summary(news)

    try:
        return _call_gemini(_SYSTEM_PROMPT, _build_headlines_prompt(news))
    except Exception:
        return _fallback_summary(news)


def _fallback_summary(news: DailyNewsSources) -> str:
    """Plain-text summary when Gemini API is unavailable."""
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
        "\n*AI analysis unavailable — set GEMINI_API_KEY for "
        "opinionated briefing (free at https://aistudio.google.com/apikey).*"
    )
    return "\n".join(parts)
