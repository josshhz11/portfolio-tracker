#!/usr/bin/env python3
"""Seed sample holdings into the portfolio tracker database.

This script is **idempotent by default**: it will refuse to insert holdings if
the table already contains rows. Pass ``--force`` to truncate and re-seed.

Usage
-----
    python scripts/seed_holdings.py [--db PATH] [--force]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DB_PATH
from src.db import get_all_holdings, initialize_database, insert_holding
from src.utils.logging_config import setup_logging

SEED_HOLDINGS: list[tuple] = [
    # (ticker, shares_owned, cost_per_share, currency, platform)
    ("NBIS", 62, 92.455, "USD", "Moomoo"),
    ("SNAP", 2000, 8.68, "USD", "Moomoo"),
    ("STAI", 21, 61.355, "USD", "Moomoo"),
    ("VOYG", 50, 49.99, "USD", "Moomoo"),
    ("WOK", 11, 210.056, "USD", "Moomoo"),
    ("D05.SI", 600, 35.827, "SGD", "Tiger"),
    ("D05.SI", 200, 54.0, "SGD", "IBKR"),
]


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Seed sample holdings into the database.")
    parser.add_argument(
        "--db",
        default=str(DB_PATH),
        metavar="PATH",
        help="Path to the SQLite database file (default: %(default)s).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Truncate existing holdings (and daily_prices) before seeding.",
    )
    args = parser.parse_args()

    conn = initialize_database(Path(args.db))
    try:
        existing = get_all_holdings(conn)
        if existing and not args.force:
            print(
                f"Holdings table already has {len(existing)} row(s). "
                "Use --force to truncate and re-seed."
            )
            sys.exit(1)

        if args.force:
            conn.execute("DELETE FROM daily_prices")
            conn.execute("DELETE FROM holdings")
            conn.execute(
                "DELETE FROM sqlite_sequence WHERE name IN ('holdings', 'daily_prices')"
            )
            conn.commit()
            print("Existing holdings and daily_prices cleared.")

        for ticker, shares, cost, currency, platform in SEED_HOLDINGS:
            row_id = insert_holding(conn, ticker, shares, cost, currency, platform)
            print(f"  Inserted holding id={row_id}: {shares} x {ticker} @ {cost} {currency} ({platform})")

        print(f"\nSeeded {len(SEED_HOLDINGS)} holdings into {args.db}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
