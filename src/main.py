"""CLI entry-point for the portfolio tracker.

Usage
-----
    python -m src.main <command> [options]

Commands
--------
    init-db         Initialise the SQLite database and create tables.
    seed-holdings   Seed sample holdings into the database.
    update-daily    Fetch latest prices/FX and insert daily snapshots.
    show-holdings   Print all holdings stored in the database.
    show-daily      Print daily price snapshots for a given date.
"""

import argparse
import sys
from pathlib import Path

from src.config import DB_PATH
from src.db import get_all_holdings, get_daily_prices_by_date, initialize_database
from src.services.updater import run_daily_update
from src.utils.dates import is_valid_date_str, today_str
from src.utils.logging_config import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

# ── Seed data ─────────────────────────────────────────────────────────────────

SEED_HOLDINGS = [
    ("NBIS", 62, 92.455, "USD", "Moomoo"),
    ("SNAP", 2000, 8.68, "USD", "Moomoo"),
    ("STAI", 21, 61.355, "USD", "Moomoo"),
    ("VOYG", 50, 49.99, "USD", "Moomoo"),
    ("WOK", 11, 210.056, "USD", "Moomoo"),
    ("D05.SI", 600, 35.827, "SGD", "Tiger"),
    ("D05.SI", 200, 54.0, "SGD", "IBKR"),
]


# ── Command handlers ──────────────────────────────────────────────────────────


def cmd_init_db(args: argparse.Namespace) -> int:
    """Initialise the database and create tables."""
    db_path = Path(args.db)
    conn = initialize_database(db_path)
    conn.close()
    print(f"Database initialised at {db_path}")
    return 0


def cmd_seed_holdings(args: argparse.Namespace) -> int:
    """Seed sample holdings (idempotent: clears and re-inserts)."""
    from src.db import get_connection, insert_holding

    db_path = Path(args.db)
    conn = initialize_database(db_path)
    try:
        if not args.force:
            existing = get_all_holdings(conn)
            if existing:
                print(
                    f"Holdings table already has {len(existing)} row(s). "
                    "Use --force to truncate and re-seed."
                )
                return 1
        # Truncate existing data (cascade handled manually because SQLite
        # TRUNCATE is not supported; DELETE is used instead)
        conn.execute("DELETE FROM daily_prices")
        conn.execute("DELETE FROM holdings")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('holdings', 'daily_prices')")
        conn.commit()

        for ticker, shares, cost, currency, platform in SEED_HOLDINGS:
            insert_holding(conn, ticker, shares, cost, currency, platform)
        print(f"Seeded {len(SEED_HOLDINGS)} holdings.")
        return 0
    finally:
        conn.close()


def cmd_update_daily(args: argparse.Namespace) -> int:
    """Run the daily price/FX update."""
    date_override = args.date if hasattr(args, "date") and args.date else None
    if date_override and not is_valid_date_str(date_override):
        print(f"Invalid date format: '{date_override}'. Expected YYYY-MM-DD.", file=sys.stderr)
        return 2
    summary = run_daily_update(db_path=Path(args.db), date=date_override)
    print(summary)
    return 0 if summary.failed == 0 else 1


def cmd_show_holdings(args: argparse.Namespace) -> int:
    """Print all holdings."""
    from src.db import get_connection

    conn = get_connection(Path(args.db))
    try:
        holdings = get_all_holdings(conn)
        if not holdings:
            print("No holdings found.")
            return 0
        header = f"{'ID':>4}  {'Ticker':<10}  {'Shares':>10}  {'Cost':>10}  {'CCY':>4}  Platform"
        print(header)
        print("-" * len(header))
        for h in holdings:
            print(
                f"{h.id:>4}  {h.ticker:<10}  {h.shares_owned:>10.4f}  "
                f"{h.cost_per_share:>10.4f}  {h.currency:>4}  {h.platform}"
            )
        return 0
    finally:
        conn.close()


def cmd_show_daily(args: argparse.Namespace) -> int:
    """Print daily price snapshots for the given date."""
    from src.db import get_connection

    date_str = args.date if args.date else today_str()
    if not is_valid_date_str(date_str):
        print(f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD.", file=sys.stderr)
        return 2

    conn = get_connection(Path(args.db))
    try:
        rows = get_daily_prices_by_date(conn, date_str)
        if not rows:
            print(f"No daily data found for {date_str}.")
            return 0
        print(f"\nDaily snapshot for {date_str}")
        header = (
            f"{'ID':>4}  {'H-ID':>5}  {'Ticker':<10}  {'Price':>10}  "
            f"{'Mkt Val':>12}  {'P&L':>12}  {'Mkt SGD':>12}  {'P&L SGD':>12}"
        )
        print(header)
        print("-" * len(header))
        for r in rows:
            print(
                f"{r.id:>4}  {r.holding_id:>5}  {r.ticker:<10}  "
                f"{r.price_per_share:>10.4f}  {r.market_value:>12,.2f}  "
                f"{r.profit:>+12,.2f}  {r.market_value_sgd:>12,.2f}  "
                f"{r.profit_sgd:>+12,.2f}"
            )
        total_mv = sum(r.market_value_sgd for r in rows)
        total_pl = sum(r.profit_sgd for r in rows)
        print(f"\nTotal portfolio (SGD): {total_mv:,.2f}  |  P&L (SGD): {total_pl:+,.2f}")
        return 0
    finally:
        conn.close()


# ── Argument parser ───────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="portfolio-tracker",
        description="Stock portfolio consolidation and daily database updater.",
    )
    parser.add_argument(
        "--db",
        default=str(DB_PATH),
        metavar="PATH",
        help="Path to the SQLite database file (default: %(default)s).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: %(default)s).",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # init-db
    sub.add_parser("init-db", help="Initialise the database and create tables.")

    # seed-holdings
    p_seed = sub.add_parser("seed-holdings", help="Seed sample holdings into the database.")
    p_seed.add_argument(
        "--force",
        action="store_true",
        help="Truncate existing holdings and daily_prices before seeding.",
    )

    # update-daily
    p_upd = sub.add_parser("update-daily", help="Fetch latest prices/FX and insert daily snapshots.")
    p_upd.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Override the update date (default: today).",
    )

    # show-holdings
    sub.add_parser("show-holdings", help="Display all holdings in the database.")

    # show-daily
    p_show = sub.add_parser("show-daily", help="Display daily snapshots for a specific date.")
    p_show.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Date to display (default: today).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate command handler.

    Args:
        argv: Override ``sys.argv[1:]`` for testing.

    Returns:
        Exit code (0 = success).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(level=args.log_level)

    dispatch = {
        "init-db": cmd_init_db,
        "seed-holdings": cmd_seed_holdings,
        "update-daily": cmd_update_daily,
        "show-holdings": cmd_show_holdings,
        "show-daily": cmd_show_daily,
    }
    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 2
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
