"""Daily portfolio snapshot capture service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.db import (
    get_cash_accounts,
    get_currency_rate,
    get_daily_snapshot_by_date,
    initialize_database,
    upsert_cash_snapshot,
    upsert_portfolio_snapshot,
)
from src.models import CashSnapshot
from src.config import BASE_CURRENCY
from src.utils.dates import today_str
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class SnapshotCaptureSummary:
    """Result summary for daily portfolio snapshot capture."""

    date: str
    portfolio_processed: int = 0
    cash_processed: int = 0

    @property
    def processed(self) -> int:
        return self.portfolio_processed + self.cash_processed

    def __str__(self) -> str:
        return (
            f"Date: {self.date} | Portfolio snapshots: {self.portfolio_processed} | "
            f"Cash snapshots: {self.cash_processed} | Total: {self.processed}"
        )


def run_daily_snapshot_capture(
    user_id: Optional[str] = None,
    date: Optional[str] = None,
    exclude_user_id: Optional[str] = None,
) -> SnapshotCaptureSummary:
    """Capture daily snapshots for holdings and cash accounts."""
    snapshot_date = date or today_str()
    summary = SnapshotCaptureSummary(date=snapshot_date)

    conn = initialize_database()
    try:
        rows = get_daily_snapshot_by_date(
            conn=conn,
            date=snapshot_date,
            user_id=user_id,
            exclude_user_id=exclude_user_id,
        )

        if not rows:
            logger.warning("No eligible daily snapshot rows found for %s.", snapshot_date)
            return summary

        # Load a user map once to avoid querying per-row.
        with conn.cursor() as cur:
            cur.execute("SELECT id, user_id::text AS user_id FROM public.holdings")
            user_map = {int(r["id"]): r["user_id"] for r in cur.fetchall()}

        for row in rows:
            owner_user_id = user_map.get(row.holding_id)
            if owner_user_id is None:
                logger.warning("Holding id=%d missing owner mapping; skipping snapshot row.", row.holding_id)
                continue

            upsert_portfolio_snapshot(
                conn=conn,
                user_id=owner_user_id,
                snapshot=row,
                date=snapshot_date,
            )
            summary.portfolio_processed += 1

        cash_accounts = get_cash_accounts(
            conn=conn,
            user_id=user_id,
            exclude_user_id=exclude_user_id,
        )

        for cash_account in cash_accounts:
            if cash_account.currency.upper() == BASE_CURRENCY:
                fx_rate = 1.0
            else:
                fx_rate = get_currency_rate(conn, cash_account.currency.upper(), snapshot_date)
                if fx_rate is None:
                    logger.warning(
                        "FX rate unavailable for cash account id=%d (%s/%s) on %s; skipping.",
                        cash_account.id or 0,
                        cash_account.platform,
                        cash_account.currency,
                        snapshot_date,
                    )
                    continue

            balance = float(cash_account.balance)
            cash_snapshot = CashSnapshot(
                cash_account_id=int(cash_account.id or 0),
                snapshot_date=snapshot_date,
                platform=cash_account.platform,
                currency=cash_account.currency,
                balance=balance,
                fx_rate=fx_rate,
                balance_sgd=balance * fx_rate,
            )
            upsert_cash_snapshot(
                conn=conn,
                user_id=cash_account.user_id,
                cash_snapshot=cash_snapshot,
            )
            summary.cash_processed += 1

        conn.commit()
        logger.info("Daily snapshot capture complete. %s", summary)
        return summary
    finally:
        conn.close()
