"""Stock price reaction analysis around earnings dates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import yfinance as yf


@dataclass
class PriceReaction:
    """Share price reaction around an earnings event."""

    ticker: str
    earnings_date: date | None = None
    close_before: float | None = None
    close_after: float | None = None
    close_1w_after: float | None = None
    change_pct: float | None = None
    change_1w_pct: float | None = None
    high_after: float | None = None
    low_after: float | None = None
    volume_on_day: int | None = None
    avg_volume_prior: int | None = None
    volume_ratio: float | None = None
    current_price: float | None = None


def get_price_reaction(ticker: str, earnings_date: date | None = None) -> PriceReaction:
    """Analyze share price reaction around the most recent earnings date.

    If earnings_date is not provided, uses yfinance to find the last earnings date.
    """
    stock = yf.Ticker(ticker)
    result = PriceReaction(ticker=ticker)

    # Try to determine earnings date from the calendar
    if earnings_date is None:
        try:
            cal = stock.calendar
            if cal is not None and isinstance(cal, dict) and "Earnings Date" in cal:
                ed = cal["Earnings Date"]
                if isinstance(ed, list) and ed:
                    earnings_date = ed[0]
                elif isinstance(ed, date):
                    earnings_date = ed
        except Exception:
            pass

    # Fetch a wider window of historical data to work with
    end_date = date.today() + timedelta(days=1)
    start_date = end_date - timedelta(days=90)
    hist = stock.history(start=str(start_date), end=str(end_date), auto_adjust=True)

    if hist.empty:
        # Try current price from info
        try:
            info = stock.info
            result.current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        except Exception:
            pass
        return result

    # Current price
    result.current_price = float(hist["Close"].iloc[-1])

    if earnings_date is None:
        # Heuristic: find the trading day with the biggest single-day volume spike
        # in the last 60 days, as it's likely the earnings reaction day
        recent = hist.tail(60)
        if len(recent) > 5:
            vol_series = recent["Volume"]
            avg_vol = vol_series.rolling(20, min_periods=5).mean().shift(1)
            vol_ratio = vol_series / avg_vol.clip(lower=1)
            max_ratio_idx = vol_ratio.idxmax()
            if max_ratio_idx is not None:
                earnings_date = max_ratio_idx.date() if hasattr(max_ratio_idx, "date") else None

    if earnings_date is None:
        return result

    result.earnings_date = earnings_date

    # Convert index to dates for comparison
    trading_dates = [d.date() if hasattr(d, "date") else d for d in hist.index]

    # Find the closest trading day on or after the earnings date
    earn_idx = None
    for i, td in enumerate(trading_dates):
        if td >= earnings_date:
            earn_idx = i
            break

    if earn_idx is None:
        return result

    # Close before earnings (prior trading day)
    if earn_idx > 0:
        result.close_before = float(hist["Close"].iloc[earn_idx - 1])

    # Close on earnings day / day after
    result.close_after = float(hist["Close"].iloc[earn_idx])

    # 1 week after
    target_1w = earnings_date + timedelta(days=7)
    for i, td in enumerate(trading_dates):
        if td >= target_1w:
            result.close_1w_after = float(hist["Close"].iloc[i])
            break

    # Calculate percentage changes
    if result.close_before and result.close_after:
        result.change_pct = round(
            (result.close_after - result.close_before) / result.close_before * 100, 2
        )

    if result.close_before and result.close_1w_after:
        result.change_1w_pct = round(
            (result.close_1w_after - result.close_before) / result.close_before * 100,
            2,
        )

    # Volume analysis
    result.volume_on_day = int(hist["Volume"].iloc[earn_idx])
    if earn_idx >= 20:
        result.avg_volume_prior = int(
            hist["Volume"].iloc[earn_idx - 20 : earn_idx].mean()
        )
        if result.avg_volume_prior > 0:
            result.volume_ratio = round(
                result.volume_on_day / result.avg_volume_prior, 2
            )

    # High/low in the 5 days after earnings
    end_window = min(earn_idx + 5, len(hist))
    result.high_after = float(hist["High"].iloc[earn_idx:end_window].max())
    result.low_after = float(hist["Low"].iloc[earn_idx:end_window].min())

    return result
