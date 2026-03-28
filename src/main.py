"""CLI entry-point for the portfolio tracker."""

from __future__ import annotations

import argparse
import sys

from src.config import DEFAULT_USER_ID
from src.db import (
    get_all_holdings,
    get_connection,
    get_daily_snapshot_by_date,
    initialize_database,
    insert_holding,
    resolve_default_user_id,
)
from src.services.updater import run_daily_update
from src.utils.dates import is_valid_date_str, today_str
from src.utils.logging_config import setup_logging

setup_logging()

SEED_HOLDINGS = [
    ("NVDA", 60, 92.455, "USD", "Moomoo"),
    ("BBAI", 2000, 2.45, "USD", "Moomoo"),
    ("SNDK", 100, 499.55, "USD", "Moomoo"),
    ("GOOG", 50, 49.99, "USD", "Moomoo"),
    ("CRWV", 11, 75.056, "USD", "Moomoo"),
    ("D05.SI", 600, 45.82, "SGD", "Tiger"),
    ("D05.SI", 200, 54.0, "SGD", "IBKR"),
]


def _effective_user_id(arg_user_id: str | None) -> str:
    if arg_user_id:
        return arg_user_id
    return resolve_default_user_id()


def cmd_init_db(_args: argparse.Namespace) -> int:
    conn = initialize_database()
    conn.close()
    print("Database initialised against Supabase/Postgres.")
    return 0


def cmd_seed_holdings(args: argparse.Namespace) -> int:
    user_id = _effective_user_id(args.user_id)
    conn = initialize_database()
    try:
        if not args.force:
            existing = get_all_holdings(conn, user_id=user_id)
            if existing:
                print(
                    f"Holdings table already has {len(existing)} row(s) for this user. "
                    "Use --force to overwrite demo holdings for this user."
                )
                return 1

        if args.force:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM public.holdings WHERE user_id = %s", (user_id,))
            conn.commit()

        for ticker, shares, cost, currency, platform in SEED_HOLDINGS:
            invested_amount = shares * cost
            insert_holding(
                conn=conn,
                user_id=user_id,
                ticker=ticker,
                shares_owned=shares,
                invested_amount=invested_amount,
                currency=currency,
                platform=platform,
            )
        print(f"Seeded {len(SEED_HOLDINGS)} holdings for user {user_id}.")
        return 0
    finally:
        conn.close()


def cmd_update_daily(args: argparse.Namespace) -> int:
    date_override = args.date if args.date else None
    if date_override and not is_valid_date_str(date_override):
        print(f"Invalid date format: '{date_override}'. Expected YYYY-MM-DD.", file=sys.stderr)
        return 2

    summary = run_daily_update(user_id=_effective_user_id(args.user_id), date=date_override)
    print(summary)
    return 0 if summary.failed == 0 else 1


def cmd_show_holdings(args: argparse.Namespace) -> int:
    user_id = _effective_user_id(args.user_id)
    conn = get_connection()
    try:
        holdings = get_all_holdings(conn, user_id=user_id)
        if not holdings:
            print("No holdings found.")
            return 0
        header = f"{'ID':>4}  {'Ticker':<10}  {'Shares':>10}  {'Invested':>12}  {'Cost':>10}  {'CCY':>4}  Platform"
        print(header)
        print("-" * len(header))
        for h in holdings:
            print(
                f"{h.id:>4}  {h.ticker:<10}  {h.shares_owned:>10.4f}  "
                f"{h.invested_amount:>12.4f}  {h.cost_per_share:>10.4f}  {h.currency:>4}  {h.platform}"
            )
        return 0
    finally:
        conn.close()


def cmd_show_daily(args: argparse.Namespace) -> int:
    user_id = _effective_user_id(args.user_id)
    date_str = args.date if args.date else today_str()
    if not is_valid_date_str(date_str):
        print(f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD.", file=sys.stderr)
        return 2

    conn = get_connection()
    try:
        rows = get_daily_snapshot_by_date(conn, date_str, user_id=user_id)
        if not rows:
            print(f"No daily data found for {date_str}.")
            return 0

        print(f"\nDaily snapshot for {date_str}")
        header = (
            f"{'H-ID':>5}  {'Ticker':<10}  {'Price':>10}  {'Mkt Val':>12}  {'P&L':>12}  "
            f"{'Mkt SGD':>12}  {'P&L SGD':>12}"
        )
        print(header)
        print("-" * len(header))
        for r in rows:
            print(
                f"{r.holding_id:>5}  {r.ticker:<10}  {r.price_per_share:>10.4f}  "
                f"{r.market_value:>12,.2f}  {r.profit:>+12,.2f}  "
                f"{r.market_value_sgd:>12,.2f}  {r.profit_sgd:>+12,.2f}"
            )
        total_mv = sum(r.market_value_sgd for r in rows)
        total_pl = sum(r.profit_sgd for r in rows)
        print(f"\nTotal portfolio (SGD): {total_mv:,.2f}  |  P&L (SGD): {total_pl:+,.2f}")
        return 0
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="portfolio-tracker",
        description="Stock portfolio consolidation and daily database updater.",
    )
    parser.add_argument(
        "--db",
        default="",
        metavar="PATH",
        help="Deprecated (SQLite path). Ignored in Supabase mode.",
    )
    parser.add_argument(
        "--user-id",
        default=DEFAULT_USER_ID or None,
        metavar="UUID",
        help="Portfolio user id (or set PORTFOLIO_USER_ID env var).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: %(default)s).",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    sub.add_parser("init-db", help="Initialise required tables in the database.")

    p_seed = sub.add_parser("seed-holdings", help="Seed demo holdings into the database.")
    p_seed.add_argument(
        "--force",
        action="store_true",
        help="Delete existing holdings for this user before seeding.",
    )

    p_upd = sub.add_parser("update-daily", help="Fetch latest prices/FX and store daily market prices.")
    p_upd.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Override the update date (default: today).",
    )

    sub.add_parser("show-holdings", help="Display holdings for this user.")

    p_show = sub.add_parser("show-daily", help="Display computed daily snapshot for a specific date.")
    p_show.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Date to display (default: today).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
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
