"""Main orchestrator that ties together all analysis components."""

from __future__ import annotations

from rich.console import Console

from earnings_analyzer.financials import (
    extract_analyst_questions,
    extract_financial_metrics,
    extract_guidance,
)
from earnings_analyzer.report import (
    print_8k_summary,
    print_10q_summary,
    print_analyst_questions,
    print_filing_links,
    print_financials,
    print_guidance,
    print_header,
    print_highlights,
    print_price_reaction,
)
from earnings_analyzer.sec_client import SECClient
from earnings_analyzer.stock_price import get_price_reaction

console = Console()


def analyze_earnings(ticker: str) -> None:
    """Run the full earnings analysis pipeline for a given ticker."""
    ticker = ticker.upper()

    with console.status(f"[bold cyan]Analyzing {ticker} earnings..."):
        with SECClient() as sec:
            # Resolve ticker to CIK
            console.log(f"Resolving {ticker} to CIK...")
            try:
                cik = sec.resolve_cik(ticker)
            except ValueError as e:
                console.print(f"[red]Error: {e}[/red]")
                return
            except Exception as e:
                console.print(f"[red]Network error resolving ticker: {e}[/red]")
                console.print("[dim]Check your internet connection and try again.[/dim]")
                return
            console.log(f"CIK: {cik}")

            # Get company name from yfinance
            company_name = _get_company_name(ticker)

            # Fetch filings
            console.log("Fetching 8-K filing...")
            filing_8k = sec.get_latest_8k(cik)

            console.log("Fetching 10-Q filing...")
            filing_10q = sec.get_latest_10q(cik)

            # Get stock price data
            console.log("Fetching price data...")
            earnings_date = filing_8k.filed_date if filing_8k else None
            price_reaction = get_price_reaction(ticker, earnings_date)

    # --- Render report ---
    print_header(ticker, company_name)

    # Combine text from both filings for analysis
    combined_text = ""
    if filing_8k:
        combined_text += filing_8k.text_content + "\n"
    if filing_10q:
        combined_text += filing_10q.text_content + "\n"

    # Financial metrics
    if combined_text:
        metrics = extract_financial_metrics(combined_text)
        print_financials(metrics)
        print_highlights(metrics.highlights)
    else:
        console.print("[dim]No filing content available for financial extraction.[/dim]\n")

    # 8-K details
    if filing_8k:
        print_8k_summary(
            items=filing_8k.items,
            filed_date=str(filing_8k.filed_date),
            text_excerpt=filing_8k.text_content,
        )
    else:
        console.print("[dim]No recent 8-K (earnings) filing found.[/dim]\n")

    # 10-Q details
    if filing_10q:
        print_10q_summary(
            filed_date=str(filing_10q.filed_date),
            text_excerpt=filing_10q.text_content,
        )
    else:
        console.print("[dim]No recent 10-Q filing found.[/dim]\n")

    # Guidance
    if combined_text:
        guidance = extract_guidance(combined_text)
        print_guidance(guidance)

    # Analyst Q&A
    if combined_text:
        questions = extract_analyst_questions(combined_text)
        print_analyst_questions(questions)

    # Price reaction
    print_price_reaction(price_reaction)

    # Filing links
    filings_info: list[dict[str, str]] = []
    if filing_8k:
        filings_info.append({
            "type": "8-K",
            "url": filing_8k.html_url,
            "date": str(filing_8k.filed_date),
        })
    if filing_10q:
        filings_info.append({
            "type": "10-Q",
            "url": filing_10q.html_url,
            "date": str(filing_10q.filed_date),
        })
    print_filing_links(cik, filings_info)


def _get_company_name(ticker: str) -> str:
    """Get company name from yfinance."""
    try:
        import yfinance as yf

        stock = yf.Ticker(ticker)
        info = stock.info
        return info.get("longName", "") or info.get("shortName", "")
    except Exception:
        return ""
