"""FX service: fetches and caches daily exchange rates versus SGD."""

import sqlite3
from typing import Optional

import yfinance as yf

from src.config import BASE_CURRENCY, FX_TICKER_MAP, PRICE_LOOKBACK_DAYS
from src.db import get_currency_rate, insert_currency_rate
from src.models import Holding
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


def get_fx_rate_to_sgd(
    currency: str,
    date: str,
    conn: Optional[sqlite3.Connection] = None,
) -> float:
    """Return the exchange rate: 1 unit of *currency* in SGD.

    The function first checks the local database cache. If not cached it
    fetches from yfinance and stores the result.

    SGD always returns ``1.0`` without a network call.

    Args:
        currency: ISO currency code (e.g. ``"USD"``).
        date:     ISO-8601 date string ``YYYY-MM-DD`` to key the cache entry.
        conn:     Open database connection for cache read/write. When ``None``
                  the rate is fetched but **not** persisted.

    Returns:
        Exchange rate as a float (≥ 0).

    Raises:
        ValueError: If the currency is unsupported and no FX data is available.
    """
    currency = currency.upper()

    if currency == BASE_CURRENCY:
        return 1.0

    # Check DB cache first
    if conn is not None:
        cached = get_currency_rate(conn, currency, date)
        if cached is not None:
            logger.debug("Cache hit for %s on %s: %.6f", currency, date, cached)
            return cached

    rate = _fetch_rate_from_yfinance(currency)
    if rate is None:
        raise ValueError(
            f"Unable to fetch FX rate for '{currency}'. "
            "Please add it to FX_TICKER_MAP or check your internet connection."
        )

    if conn is not None:
        insert_currency_rate(conn, currency, rate, date)

    return rate


def _fetch_rate_from_yfinance(currency: str) -> Optional[float]:
    """Use yfinance to fetch the latest rate for *currency* → SGD.

    Args:
        currency: ISO currency code.

    Returns:
        Rate as a float, or ``None`` on failure.
    """
    yf_ticker = FX_TICKER_MAP.get(currency.upper())
    if not yf_ticker:
        logger.error(
            "Currency '%s' is not in FX_TICKER_MAP. Cannot fetch rate.", currency
        )
        return None

    try:
        hist = yf.Ticker(yf_ticker).history(period=f"{PRICE_LOOKBACK_DAYS}d")
        if hist.empty:
            logger.warning("No FX data returned for ticker '%s'.", yf_ticker)
            return None
        rate = float(hist["Close"].dropna().iloc[-1])
        logger.debug("Fetched FX %s (via %s): %.6f", currency, yf_ticker, rate)
        return rate
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch FX rate for '%s': %s", yf_ticker, exc)
        return None


def get_supported_currencies_from_holdings(holdings: list[Holding]) -> list[str]:
    """Return the unique non-SGD currencies present in *holdings*.

    Args:
        holdings: List of :class:`~src.models.Holding` objects.

    Returns:
        Sorted list of unique currency codes excluding ``"SGD"``.
    """
    return sorted(
        {h.currency.upper() for h in holdings if h.currency.upper() != BASE_CURRENCY}
    )
