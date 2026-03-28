#!/usr/bin/env python3
"""Run the daily portfolio update.

Fetches latest stock prices and FX rates, computes market values and P&L,
and inserts daily snapshots into the database.

Usage
-----
    python scripts/run_daily_update.py [--user-id UUID] [--date YYYY-MM-DD]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DEFAULT_USER_ID
from src.db import resolve_default_user_id
from src.services.updater import run_daily_update
from src.utils.logging_config import setup_logging


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Run the daily portfolio price/FX update.")
    parser.add_argument(
        "--user-id",
        default=DEFAULT_USER_ID or None,
        metavar="UUID",
        help="Portfolio user id (or set PORTFOLIO_USER_ID).",
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Override the update date (default: today in UTC).",
    )
    args = parser.parse_args()

    summary = run_daily_update(user_id=args.user_id or resolve_default_user_id(), date=args.date)

    print("\n" + "=" * 60)
    print("DAILY UPDATE COMPLETE")
    print("=" * 60)
    print(f"  Date             : {summary.date}")
    print(f"  Total holdings   : {summary.total_holdings}")
    print(f"  Successful       : {summary.successful}")
    print(f"  Skipped (dup)    : {summary.skipped}")
    print(f"  Failed           : {summary.failed}")
    print(f"  Portfolio SGD    : {summary.total_market_value_sgd:,.2f}")
    print(f"  Total P&L SGD    : {summary.total_profit_sgd:+,.2f}")
    if summary.errors:
        print("\nErrors:")
        for err in summary.errors:
            print(f"  - {err}")
    print("=" * 60)

    sys.exit(0 if summary.failed == 0 else 1)


if __name__ == "__main__":
    main()
