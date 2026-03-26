"""Market data service: fetches latest stock prices via yfinance."""

import logging
from typing import Optional

import yfinance as yf

from src.config import PRICE_LOOKBACK_DAYS
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


def get_latest_price(ticker: str) -> Optional[float]:
    """Fetch the most recent closing price for *ticker*.

    Tries to retrieve the last ``PRICE_LOOKBACK_DAYS`` of daily history from
    yfinance and returns the most recent valid close.

    Args:
        ticker: Stock ticker symbol (e.g. ``"AAPL"`` or ``"D05.SI"``).

    Returns:
        Latest close price as a float, or ``None`` if data is unavailable.
    """
    try:
        hist = yf.Ticker(ticker).history(period=f"{PRICE_LOOKBACK_DAYS}d")
        if hist.empty:
            logger.warning("No price data returned for ticker '%s'.", ticker)
            return None
        price = float(hist["Close"].dropna().iloc[-1])
        logger.debug("Price for %s: %.4f", ticker, price)
        return price
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch price for '%s': %s", ticker, exc)
        return None


def get_latest_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch the latest closing prices for multiple tickers in a single batch.

    Individual failures are logged and the ticker is omitted from the result
    rather than raising an exception so that a single bad ticker does not abort
    the entire run.

    Args:
        tickers: List of ticker symbols.

    Returns:
        Dict mapping ticker → price for every ticker that returned valid data.
    """
    if not tickers:
        return {}

    prices: dict[str, float] = {}
    unique_tickers = list(dict.fromkeys(tickers))  # preserve order, deduplicate

    try:
        # yfinance can download multiple tickers in one call
        data = yf.download(
            tickers=unique_tickers,
            period=f"{PRICE_LOOKBACK_DAYS}d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        close = data.get("Close") if isinstance(data.columns, object) else None
        # yfinance returns a flat Series when only one ticker is requested
        if close is None:
            close = data

        if close is None or (hasattr(close, "empty") and close.empty):
            logger.warning("Batch download returned no data. Falling back to individual fetches.")
            return _fetch_individually(unique_tickers)

        for ticker in unique_tickers:
            try:
                if hasattr(close, "columns"):
                    # Multi-ticker DataFrame
                    if ticker in close.columns:
                        series = close[ticker].dropna()
                    else:
                        logger.warning("Ticker '%s' not found in batch result.", ticker)
                        continue
                else:
                    # Single-ticker Series
                    series = close.dropna()

                if series.empty:
                    logger.warning("No valid close prices in batch result for '%s'.", ticker)
                    continue
                prices[ticker] = float(series.iloc[-1])
                logger.debug("Batch price for %s: %.4f", ticker, prices[ticker])
            except Exception as exc:  # noqa: BLE001
                logger.error("Error extracting batch price for '%s': %s", ticker, exc)

    except Exception as exc:  # noqa: BLE001
        logger.warning("Batch download failed (%s). Falling back to individual fetches.", exc)
        return _fetch_individually(unique_tickers)

    # Fall back for any tickers that the batch missed
    missing = [t for t in unique_tickers if t not in prices]
    if missing:
        logger.debug("Fetching %d missing tickers individually: %s", len(missing), missing)
        for ticker, price in _fetch_individually(missing).items():
            prices[ticker] = price

    return prices


def _fetch_individually(tickers: list[str]) -> dict[str, float]:
    """Fetch prices one ticker at a time and return a dict of successful results."""
    result: dict[str, float] = {}
    for ticker in tickers:
        price = get_latest_price(ticker)
        if price is not None:
            result[ticker] = price
    return result
