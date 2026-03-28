"""Daily update orchestrator.

Workflow
--------
1. Read all holdings from the database.
2. Determine today's date.
3. Fetch all required FX rates.
4. Fetch all required ticker prices.
5. Compute market values and P&L.
6. Insert daily_prices rows (skipping duplicates).
7. Return a summary object.
"""

from dataclasses import dataclass, field
from typing import Optional

from src.db import get_all_holdings, initialize_database, insert_daily_price
from src.db import (
    resolve_default_user_id,
)
from src.models import Holding
from src.services.fx_data import get_fx_rate_to_sgd, get_supported_currencies_from_holdings
from src.services.market_data import get_latest_prices
from src.utils.dates import today_str
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class UpdateSummary:
    """Result object returned by :func:`run_daily_update`."""

    date: str
    total_holdings: int = 0
    successful: int = 0
    skipped: int = 0
    failed: int = 0
    total_market_value_sgd: float = 0.0
    total_profit_sgd: float = 0.0
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"Date: {self.date} | Holdings: {self.total_holdings} | "
            f"OK: {self.successful} | Skipped: {self.skipped} | "
            f"Failed: {self.failed} | "
            f"Portfolio SGD: {self.total_market_value_sgd:,.2f} | "
            f"P&L SGD: {self.total_profit_sgd:+,.2f}"
        )


def run_daily_update(
    user_id: Optional[str] = None,
    date: Optional[str] = None,
) -> UpdateSummary:
    """Run the full daily portfolio update workflow.

    Args:
        user_id: Optional user id filter for holdings.
        date:    Override the update date (``YYYY-MM-DD``). Defaults to today.

    Returns:
        An :class:`UpdateSummary` describing what happened.
    """
    update_date = date or today_str()
    summary = UpdateSummary(date=update_date)

    conn = initialize_database()
    try:
        effective_user_id = user_id or resolve_default_user_id()
        holdings: list[Holding] = get_all_holdings(conn, user_id=effective_user_id)
        summary.total_holdings = len(holdings)

        if not holdings:
            logger.warning("No holdings found in the database. Nothing to update.")
            return summary

        logger.info(
            "Starting daily update for %s with %d holdings.",
            update_date,
            len(holdings),
        )

        # ── Step 1: Fetch FX rates ──────────────────────────────────────────
        fx_rates: dict[str, float] = {"SGD": 1.0}
        currencies_needed = get_supported_currencies_from_holdings(holdings)
        for currency in currencies_needed:
            try:
                rate = get_fx_rate_to_sgd(currency, update_date, conn)
                fx_rates[currency] = rate
                logger.info("FX rate fetched: 1 %s = %.6f SGD", currency, rate)
            except ValueError as exc:
                logger.error("FX rate unavailable for %s: %s", currency, exc)
                summary.errors.append(str(exc))

        # ── Step 2: Fetch stock prices ──────────────────────────────────────
        unique_tickers = list({h.ticker for h in holdings})
        prices: dict[str, float] = get_latest_prices(unique_tickers)

        for ticker in unique_tickers:
            if ticker not in prices:
                logger.warning("No price available for ticker '%s'. Affected holdings will be skipped.", ticker)

        # ── Step 3: Store ticker prices once per day ───────────────────────
        for ticker, price in prices.items():
            inserted = insert_daily_price(
                conn=conn,
                ticker=ticker,
                price_per_share=price,
                date=update_date,
            )
            if inserted:
                summary.successful += 1
            else:
                summary.skipped += 1

        # ── Step 4: Compute portfolio totals for summary ───────────────────
        for holding in holdings:
            try:
                price = prices.get(holding.ticker)
                if price is None:
                    logger.error(
                        "Skipping holding id=%d (%s) — price not available.",
                        holding.id,
                        holding.ticker,
                    )
                    summary.failed += 1
                    summary.errors.append(
                        f"No price for ticker '{holding.ticker}' (holding id={holding.id})"
                    )
                    continue

                fx_rate = fx_rates.get(holding.currency.upper())
                if fx_rate is None:
                    logger.error(
                        "Skipping holding id=%d (%s) — FX rate for '%s' not available.",
                        holding.id,
                        holding.ticker,
                        holding.currency,
                    )
                    summary.failed += 1
                    summary.errors.append(
                        f"No FX rate for '{holding.currency}' (holding id={holding.id})"
                    )
                    continue

                market_value = holding.shares_owned * price
                profit = market_value - holding.invested_amount
                market_value_sgd = market_value * fx_rate
                profit_sgd = profit * fx_rate
                summary.total_market_value_sgd += market_value_sgd
                summary.total_profit_sgd += profit_sgd

            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Unexpected error processing holding id=%d (%s): %s",
                    holding.id,
                    holding.ticker,
                    exc,
                )
                summary.failed += 1
                summary.errors.append(
                    f"Unexpected error for holding id={holding.id}: {exc}"
                )

        logger.info("Daily update complete. %s", summary)
        return summary

    finally:
        conn.close()
