"""Command-line interface for the earnings analyzer."""

from __future__ import annotations

import click
from rich.console import Console

from earnings_analyzer.analyzer import analyze_earnings

console = Console()


@click.command()
@click.argument("ticker")
@click.version_option(package_name="earnings-analyzer")
def main(ticker: str) -> None:
    """Analyze quarterly earnings for a publicly traded company.

    TICKER is the stock ticker symbol (e.g., AAPL, MSFT, GOOG).

    Fetches the latest 8-K and 10-Q filings from SEC EDGAR,
    extracts financial metrics and guidance, analyzes price
    reaction, and presents a consolidated earnings report.
    """
    try:
        analyze_earnings(ticker)
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled.[/dim]")
    except Exception as e:
        console.print(f"[red]Error analyzing {ticker.upper()}: {e}[/red]")
        raise click.Abort()


if __name__ == "__main__":
    main()
