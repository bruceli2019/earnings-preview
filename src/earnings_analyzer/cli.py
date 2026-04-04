"""Command-line interface for the earnings analyzer."""

from __future__ import annotations

import click
from rich.console import Console

from earnings_analyzer.analyzer import analyze_earnings

console = Console()


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(package_name="earnings-analyzer")
def main(ctx: click.Context) -> None:
    """Earnings Analyzer - earnings reports & daily news summaries."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command()
@click.argument("ticker")
def earnings(ticker: str) -> None:
    """Analyze quarterly earnings for TICKER (e.g., AAPL, MSFT)."""
    try:
        analyze_earnings(ticker)
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled.[/dim]")
    except Exception as e:
        console.print(f"[red]Error analyzing {ticker.upper()}: {e}[/red]")
        raise click.Abort()


@main.command("news")
@click.option(
    "--config",
    "config_path",
    default=None,
    type=click.Path(exists=False),
    help="Path to news_config.json (optional).",
)
@click.option(
    "--output-dir",
    default=None,
    help="Directory to save the newsletter HTML (overrides config).",
)
@click.option(
    "--headlines",
    default=None,
    type=int,
    help="Number of Techmeme headlines to include.",
)
@click.option(
    "--open/--no-open",
    "open_browser",
    default=False,
    help="Open the newsletter in a browser after generation.",
)
def daily_news(
    config_path: str | None,
    output_dir: str | None,
    headlines: int | None,
    open_browser: bool,
) -> None:
    """Generate today's daily news summary as an HTML newsletter.

    Pulls headlines from Techmeme and provides curated links to
    X, Financial Times, and Spotify podcasts.

    Customize sources by creating a news_config.json file or
    passing --config.
    """
    from earnings_analyzer.news_config import NewsConfig
    from earnings_analyzer.news_sources import gather_daily_news
    from earnings_analyzer.newsletter import save_newsletter

    try:
        cfg = NewsConfig.load(config_path)

        if output_dir is not None:
            cfg.output_dir = output_dir
        if headlines is not None:
            cfg.techmeme_count = headlines

        console.print("[bold cyan]Gathering daily news...[/bold cyan]")
        news = gather_daily_news(
            techmeme_count=cfg.techmeme_count,
            x_topics=cfg.x_topics,
            ft_sections=cfg.ft_sections,
            spotify_podcasts=cfg.spotify_podcasts,
        )

        filepath = save_newsletter(news, output_dir=cfg.output_dir)

        n_tech = len(news.techmeme_headlines)
        console.print(
            f"[green]Newsletter saved:[/green] {filepath}\n"
            f"  [dim]{n_tech} Techmeme headlines, "
            f"{len(news.x_links)} X links, "
            f"{len(news.ft_links)} FT links, "
            f"{len(news.spotify_links)} podcasts[/dim]"
        )

        if open_browser:
            import webbrowser

            webbrowser.open(filepath.resolve().as_uri())

    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled.[/dim]")
    except Exception as e:
        console.print(f"[red]Error generating news summary: {e}[/red]")
        raise click.Abort()


if __name__ == "__main__":
    main()
