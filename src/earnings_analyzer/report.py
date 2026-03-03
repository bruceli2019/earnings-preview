"""Rich-based report formatter for earnings analysis output."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from earnings_analyzer.financials import FinancialMetrics
from earnings_analyzer.stock_price import PriceReaction

console = Console()


def print_header(ticker: str, company_name: str) -> None:
    title = Text(f"Earnings Analysis: {ticker.upper()}", style="bold cyan")
    if company_name:
        title.append(f"  ({company_name})", style="dim")
    console.print()
    console.print(Panel(title, border_style="cyan", expand=False))
    console.print()


def print_financials(metrics: FinancialMetrics) -> None:
    table = Table(
        title="Financial Performance",
        title_style="bold yellow",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Metric", style="cyan", min_width=20)
    table.add_column("Value", style="white")

    rows = [
        ("Revenue", metrics.revenue),
        ("Net Income", metrics.net_income),
        ("EPS (Diluted)", metrics.eps_diluted),
        ("Operating Income", metrics.operating_income),
        ("Gross Margin", metrics.gross_margin),
        ("Free Cash Flow", metrics.free_cash_flow),
    ]
    for label, value in rows:
        if value:
            table.add_row(label, value)

    if table.row_count > 0:
        console.print(table)
    else:
        console.print("[dim]No financial metrics could be extracted from filings.[/dim]")
    console.print()


def print_highlights(highlights: list[str]) -> None:
    if not highlights:
        return
    console.print("[bold yellow]Key Commentary[/bold yellow]")
    for h in highlights:
        console.print(f"  [dim]\u2022[/dim] {h}")
    console.print()


def print_8k_summary(items: list[str], filed_date: str, text_excerpt: str) -> None:
    console.print(f"[bold yellow]8-K Filing[/bold yellow]  [dim](Filed: {filed_date})[/dim]")
    if items:
        item_labels = {
            "2.02": "Results of Operations and Financial Condition",
            "7.01": "Regulation FD Disclosure",
            "8.01": "Other Events",
            "9.01": "Financial Statements and Exhibits",
            "5.02": "Departure/Election of Directors or Officers",
            "2.05": "Costs Associated with Exit or Disposal Activities",
            "2.06": "Material Impairments",
        }
        for item in items:
            label = item_labels.get(item, "")
            if label:
                console.print(f"  Item {item}: {label}")
            else:
                console.print(f"  Item {item}")
    if text_excerpt:
        console.print()
        # Show first ~800 chars of meaningful content
        excerpt = _clean_excerpt(text_excerpt, max_len=800)
        console.print(Panel(excerpt, title="8-K Excerpt", border_style="dim", expand=False))
    console.print()


def print_10q_summary(filed_date: str, text_excerpt: str) -> None:
    console.print(f"[bold yellow]10-Q Filing[/bold yellow]  [dim](Filed: {filed_date})[/dim]")
    if text_excerpt:
        excerpt = _clean_excerpt(text_excerpt, max_len=800)
        console.print(Panel(excerpt, title="10-Q Excerpt", border_style="dim", expand=False))
    console.print()


def print_guidance(guidance: dict[str, str]) -> None:
    if not guidance:
        console.print("[dim]No explicit guidance found in filings.[/dim]")
        console.print()
        return
    console.print("[bold yellow]Forward Guidance[/bold yellow]")
    if "revenue_guidance" in guidance:
        console.print(f"  Revenue Guidance: {guidance['revenue_guidance']}")
    if "eps_guidance" in guidance:
        console.print(f"  EPS Guidance: {guidance['eps_guidance']}")
    if "outlook_statements" in guidance:
        console.print()
        console.print("  [bold]Outlook Statements:[/bold]")
        for stmt in guidance["outlook_statements"].split("\n"):
            if stmt.strip():
                console.print(f"    [dim]\u2022[/dim] {stmt.strip()}")
    console.print()


def print_analyst_questions(questions: list[dict[str, str]]) -> None:
    if not questions:
        console.print("[dim]No analyst Q&A found in filings.[/dim]")
        console.print()
        return
    console.print("[bold yellow]Analyst Q&A[/bold yellow]")
    for i, q in enumerate(questions, 1):
        analyst = q.get("analyst", "Unknown")
        firm = q.get("firm", "")
        question = q.get("question", "")
        header = f"{analyst}"
        if firm:
            header += f" ({firm})"
        console.print(f"  [bold]{i}. {header}[/bold]")
        # Truncate long questions
        if len(question) > 300:
            question = question[:300] + "..."
        console.print(f"     {question}")
    console.print()


def print_price_reaction(pr: PriceReaction) -> None:
    console.print("[bold yellow]Share Price Reaction[/bold yellow]")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric", style="cyan", min_width=25)
    table.add_column("Value", style="white")

    if pr.earnings_date:
        table.add_row("Earnings Date", str(pr.earnings_date))
    if pr.close_before is not None:
        table.add_row("Close Before", f"${pr.close_before:.2f}")
    if pr.close_after is not None:
        table.add_row("Close After", f"${pr.close_after:.2f}")
    if pr.change_pct is not None:
        color = "green" if pr.change_pct >= 0 else "red"
        sign = "+" if pr.change_pct >= 0 else ""
        table.add_row("Immediate Change", f"[{color}]{sign}{pr.change_pct}%[/{color}]")
    if pr.change_1w_pct is not None:
        color = "green" if pr.change_1w_pct >= 0 else "red"
        sign = "+" if pr.change_1w_pct >= 0 else ""
        table.add_row("1-Week Change", f"[{color}]{sign}{pr.change_1w_pct}%[/{color}]")
    if pr.high_after is not None and pr.low_after is not None:
        table.add_row("5-Day Range", f"${pr.low_after:.2f} - ${pr.high_after:.2f}")
    if pr.volume_ratio is not None:
        table.add_row("Volume (Earnings Day)", f"{pr.volume_on_day:,}")
        table.add_row("Avg Volume (Prior 20d)", f"{pr.avg_volume_prior:,}")
        table.add_row("Volume Ratio", f"{pr.volume_ratio}x")
    if pr.current_price is not None:
        table.add_row("Current Price", f"${pr.current_price:.2f}")

    if table.row_count > 0:
        console.print(table)
    else:
        console.print("[dim]Price data unavailable.[/dim]")
    console.print()


def print_filing_links(cik: str, filings_info: list[dict[str, str]]) -> None:
    if not filings_info:
        return
    console.print("[bold yellow]Filing Links[/bold yellow]")
    for info in filings_info:
        console.print(f"  {info['type']}: {info['url']}  [dim]({info['date']})[/dim]")
    console.print()


def _clean_excerpt(text: str, max_len: int = 800) -> str:
    """Clean and truncate text for display."""
    import re

    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    # Try to find the start of meaningful content (skip boilerplate)
    meaningful_starts = [
        "press release", "reported", "announced", "results",
        "revenue", "earnings", "financial results", "quarter",
    ]
    lower = text.lower()
    best_start = 0
    for keyword in meaningful_starts:
        idx = lower.find(keyword)
        if 0 < idx < 5000:
            # Back up to start of sentence
            sentence_start = text.rfind(".", 0, idx)
            if sentence_start > 0:
                best_start = sentence_start + 1
            else:
                best_start = max(0, idx - 50)
            break

    text = text[best_start:].strip()

    if len(text) > max_len:
        # Cut at sentence boundary
        cutoff = text.rfind(".", 0, max_len)
        if cutoff > max_len // 2:
            text = text[: cutoff + 1]
        else:
            text = text[:max_len] + "..."

    return text
