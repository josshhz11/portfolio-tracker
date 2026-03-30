"""Daily portfolio snapshot capture service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.db import get_daily_snapshot_by_date, initialize_database, upsert_portfolio_snapshot
from src.utils.dates import today_str
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class SnapshotCaptureSummary:
    """Result summary for daily portfolio snapshot capture."""

    date: str
    processed: int = 0

    def __str__(self) -> str:
        return f"Date: {self.date} | Snapshot rows upserted: {self.processed}"


def run_daily_snapshot_capture(
    user_id: Optional[str] = None,
    date: Optional[str] = None,
    exclude_user_id: Optional[str] = None,
) -> SnapshotCaptureSummary:
    """Capture per-holding snapshots for a given date into portfolio_snapshots."""
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
            summary.processed += 1

        conn.commit()
        logger.info("Daily snapshot capture complete. %s", summary)
        return summary
    finally:
        conn.close()
