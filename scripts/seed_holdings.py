#!/usr/bin/env python3
"""Seed sample holdings into the portfolio tracker database.

This script is **idempotent by default**: it will refuse to insert holdings if
the table already contains rows. Pass ``--force`` to truncate and re-seed.

Usage
-----
    python scripts/seed_holdings.py [--db PATH] [--force]
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DB_PATH
from src.db import get_all_holdings, initialize_database, insert_holding
from src.utils.logging_config import setup_logging

SEED_HOLDINGS: list[tuple] = [
    # (ticker, shares_owned, cost_per_share, currency, platform)
    ("NVDA", 60, 92.455, "USD", "Moomoo"),
    ("BBAI", 2000, 2.45, "USD", "Moomoo"),
    ("SNDK", 100, 499.55, "USD", "Moomoo"),
    ("GOOG", 50, 49.99, "USD", "Moomoo"),
    ("CRWV", 11, 75.056, "USD", "Moomoo"),
    ("D05.SI", 600, 45.82, "SGD", "Tiger"),
    ("D05.SI", 200, 54.0, "SGD", "IBKR"),
]

def load_seed_rows(seed_csv: Path) -> list[tuple]:
    """Load holdings from CSV if present; fall back to bundled demo data."""

    if not seed_csv.exists():
        return SEED_HOLDINGS

    required_headers = {
        "ticker",
        "shares_owned",
        "cost_per_share",
        "currency",
        "platform",
    }

    rows: list[tuple] = []
    with seed_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if set(reader.fieldnames or []) != required_headers:
            raise ValueError(
                "Seed CSV must include headers: ticker, shares_owned, cost_per_share, currency, platform"
            )

        for idx, row in enumerate(reader, start=1):
            try:
                rows.append(
                    (
                        row["ticker"].strip(),
                        float(row["shares_owned"]),
                        float(row["cost_per_share"]),
                        row["currency"].strip(),
                        row["platform"].strip(),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"Invalid row {idx}: {row}") from exc

    if not rows:
        raise ValueError("Seed CSV is empty; add at least one holding or remove the file to use defaults.")

    return rows


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
    parser.add_argument(
        "--seed-csv",
        default="data/seed_holdings.csv",
        metavar="PATH",
        help=(
            "Path to a CSV of holdings to seed. Falls back to built-in demo data if the file is missing. "
            "CSV headers: ticker, shares_owned, cost_per_share, currency, platform."
        ),
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

        try:
            seeds = load_seed_rows(Path(args.seed_csv))
        except ValueError as exc:
            print(f"Error loading seed data: {exc}")
            sys.exit(1)

        for ticker, shares, cost, currency, platform in seeds:
            row_id = insert_holding(conn, ticker, shares, cost, currency, platform)
            print(f"  Inserted holding id={row_id}: {shares} x {ticker} @ {cost} {currency} ({platform})")

        print(f"\nSeeded {len(seeds)} holdings into {args.db}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
