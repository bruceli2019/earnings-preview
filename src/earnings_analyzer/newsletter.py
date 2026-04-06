"""Generate an HTML newsletter from aggregated daily news sources."""

from __future__ import annotations

import html
from pathlib import Path

from earnings_analyzer.news_sources import DailyNewsSources, NewsItem


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _render_news_section(title: str, icon: str, items: list[NewsItem]) -> str:
    """Render one source section as HTML."""
    if not items:
        return ""

    rows = []
    for item in items:
        summary_html = (
            f'<p class="summary">{_esc(item.summary)}</p>' if item.summary else ""
        )
        rows.append(
            f"""        <div class="news-item">
          <a href="{_esc(item.url)}" target="_blank" rel="noopener">{_esc(item.title)}</a>
          <span class="source-badge">{_esc(item.source)}</span>
          {summary_html}
        </div>"""
        )

    return f"""
    <div class="section">
      <h2>{icon} {_esc(title)}</h2>
      {"".join(rows)}
    </div>"""


def _render_analysis_section(analysis_md: str) -> str:
    """Render the AI analysis as an HTML section with simple markdown."""
    if not analysis_md:
        return ""

    # Convert minimal markdown to HTML (headers, bold, bullets, links)
    lines: list[str] = []
    for line in analysis_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            lines.append(f'<h4 class="analysis-h">{_esc(stripped[4:])}</h4>')
        elif stripped.startswith("## "):
            lines.append(f'<h3 class="analysis-h">{_esc(stripped[3:])}</h3>')
        elif stripped.startswith("# "):
            lines.append(f'<h3 class="analysis-h">{_esc(stripped[2:])}</h3>')
        elif stripped.startswith("- "):
            content = _esc(stripped[2:])
            # Bold
            import re
            content = re.sub(
                r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content
            )
            lines.append(f'<li class="analysis-li">{content}</li>')
        elif stripped:
            content = _esc(stripped)
            import re
            content = re.sub(
                r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content
            )
            lines.append(f'<p class="analysis-p">{content}</p>')
        else:
            lines.append("")

    body = "\n          ".join(lines)
    return f"""
    <div class="section analysis-section">
      <h2>&#x1F9E0; AI Intelligence Brief</h2>
      <div class="analysis-body">
          {body}
      </div>
    </div>"""


def render_newsletter(news: DailyNewsSources) -> str:
    """Generate a complete HTML newsletter string."""
    formatted_date = news.date.strftime("%A, %B %d, %Y").replace(" 0", " ")

    sections = [
        _render_analysis_section(news.analysis),
        _render_news_section("Techmeme Headlines", "&#x1F4F0;", news.techmeme_headlines),
        _render_news_section("Hacker News", "&#x1F4E1;", news.hacker_news),
        _render_news_section("Reddit Finance", "&#x1F4AC;", news.reddit_finance),
        _render_news_section("SEC Filings", "&#x1F4DC;", news.sec_filings),
        _render_news_section("X / Twitter", "&#x1D54F;", news.x_links),
        _render_news_section("Financial Times", "&#x1F4CA;", news.ft_links),
        _render_news_section("Spotify Podcasts", "&#x1F3A7;", news.spotify_links),
        _render_news_section("ArXiv Papers", "&#x1F4D1;", news.arxiv_papers),
        _render_news_section("HF Daily Papers", "&#x1F917;", news.hf_papers),
    ]

    body = "\n".join(s for s in sections if s)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
  <meta http-equiv="Pragma" content="no-cache">
  <meta http-equiv="Expires" content="0">
  <title>Daily News Summary &mdash; {_esc(formatted_date)}</title>
  <style>
    :root {{
      --bg: #0f1117;
      --card: #1a1d27;
      --border: #2a2d3a;
      --text: #e4e4e7;
      --muted: #9ca3af;
      --accent: #6366f1;
      --accent-light: #818cf8;
      --green: #22c55e;
      --analysis-bg: #141820;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 2rem 1rem;
    }}
    .container {{
      max-width: 680px;
      margin: 0 auto;
    }}
    header {{
      text-align: center;
      margin-bottom: 2.5rem;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid var(--border);
    }}
    header h1 {{
      font-size: 1.75rem;
      font-weight: 700;
      background: linear-gradient(135deg, var(--accent-light), var(--green));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }}
    header .date {{
      color: var(--muted);
      font-size: 0.95rem;
      margin-top: 0.35rem;
    }}
    .section {{
      margin-bottom: 2rem;
    }}
    .section h2 {{
      font-size: 1.15rem;
      font-weight: 600;
      color: var(--accent-light);
      margin-bottom: 0.75rem;
      padding-bottom: 0.4rem;
      border-bottom: 1px solid var(--border);
    }}
    .news-item {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.85rem 1rem;
      margin-bottom: 0.5rem;
      transition: border-color 0.15s;
    }}
    .news-item:hover {{
      border-color: var(--accent);
    }}
    .news-item a {{
      color: var(--text);
      text-decoration: none;
      font-weight: 500;
      font-size: 0.95rem;
    }}
    .news-item a:hover {{
      color: var(--accent-light);
      text-decoration: underline;
    }}
    .source-badge {{
      display: inline-block;
      font-size: 0.7rem;
      color: var(--accent-light);
      background: rgba(99, 102, 241, 0.12);
      border: 1px solid rgba(99, 102, 241, 0.25);
      border-radius: 4px;
      padding: 0.1rem 0.4rem;
      margin-left: 0.5rem;
      vertical-align: middle;
    }}
    .summary {{
      color: var(--muted);
      font-size: 0.82rem;
      margin-top: 0.3rem;
      line-height: 1.45;
    }}
    /* Analysis section */
    .analysis-section {{
      background: var(--analysis-bg);
      border: 1px solid var(--accent);
      border-radius: 10px;
      padding: 1.25rem 1.5rem;
    }}
    .analysis-body {{
      font-size: 0.92rem;
      line-height: 1.65;
    }}
    .analysis-h {{
      color: var(--green);
      margin-top: 1rem;
      margin-bottom: 0.4rem;
    }}
    .analysis-p {{
      margin-bottom: 0.5rem;
    }}
    .analysis-li {{
      list-style: disc;
      margin-left: 1.2rem;
      margin-bottom: 0.3rem;
    }}
    .analysis-body strong {{
      color: var(--accent-light);
    }}
    footer {{
      text-align: center;
      color: var(--muted);
      font-size: 0.8rem;
      margin-top: 2rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border);
    }}
    footer a {{ color: var(--accent-light); text-decoration: none; }}
    footer a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Daily News Summary</h1>
      <div class="date">{_esc(formatted_date)}</div>
    </header>
{body}
    <footer>
      Generated by <a href="#">Earnings Analyzer</a> &middot; Sources:
      <a href="https://www.techmeme.com">Techmeme</a> &middot;
      <a href="https://news.ycombinator.com">HN</a> &middot;
      <a href="https://www.reddit.com">Reddit</a> &middot;
      <a href="https://www.sec.gov/edgar">SEC</a> &middot;
      <a href="https://x.com">X</a> &middot;
      <a href="https://www.ft.com">FT</a> &middot;
      <a href="https://open.spotify.com">Spotify</a>
    </footer>
  </div>
</body>
</html>
"""


def save_newsletter(
    news: DailyNewsSources,
    output_dir: str | Path = ".",
    filename: str | None = None,
) -> Path:
    """Render and save the newsletter to an HTML file.

    Returns the path to the written file.
    """
    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    if filename is None:
        filename = f"news-summary-{news.date.isoformat()}.html"

    # Path traversal guard
    if ".." in filename or "/" in filename or "\\" in filename:
        raise ValueError(f"Invalid filename: {filename}")

    filepath = (output_path / filename).resolve()
    if not str(filepath).startswith(str(output_path)):
        raise ValueError("Filename escapes output directory")

    filepath.write_text(render_newsletter(news), encoding="utf-8")
    return filepath
