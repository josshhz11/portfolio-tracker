#!/usr/bin/env python3
"""Seed sample holdings into the portfolio tracker database (Supabase/Postgres)."""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DEFAULT_USER_ID
from src.db import get_all_holdings, initialize_database, insert_holding, resolve_default_user_id
from src.utils.logging_config import setup_logging

SEED_HOLDINGS: list[tuple] = [
    # (ticker, shares_owned, invested_amount, currency, platform)
    ("NVDA", 60, 5547.30, "USD", "Moomoo"),
    ("BBAI", 2000, 4900.00, "USD", "Moomoo"),
    ("SNDK", 100, 49955.00, "USD", "Moomoo"),
    ("GOOG", 50, 2499.50, "USD", "Moomoo"),
    ("CRWV", 11, 825.616, "USD", "Moomoo"),
    ("D05.SI", 600, 27492.00, "SGD", "Tiger"),
    ("D05.SI", 200, 10800.00, "SGD", "IBKR"),
]


def _coerce_seed_row(row: dict[str, str], idx: int) -> tuple[str, str, float, float, str, str]:
    try:
        return (
            row["user_id"].strip(),
            row["ticker"].strip(),
            float(row["shares_owned"]),
            float(row["invested_amount"]),
            row["currency"].strip(),
            row["platform"].strip(),
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid CSV row {idx}: {row}") from exc


def load_seed_rows(seed_csv: Path, fallback_user_id: str) -> list[tuple[str, str, float, float, str, str]]:
    """Load holdings from CSV if present; fall back to bundled demo data."""
    if not seed_csv.exists():
        return [(fallback_user_id, *row) for row in SEED_HOLDINGS]

    required_headers = {
        "user_id",
        "ticker",
        "shares_owned",
        "invested_amount",
        "currency",
        "platform",
    }

    rows: list[tuple[str, str, float, float, str, str]] = []
    with seed_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if set(reader.fieldnames or []) != required_headers:
            raise ValueError(
                "Seed CSV headers must be: user_id,ticker,shares_owned,invested_amount,currency,platform"
            )
        for idx, row in enumerate(reader, start=1):
            rows.append(_coerce_seed_row(row, idx))

    if not rows:
        raise ValueError("Seed CSV is empty; add at least one holding or remove the file to use defaults.")

    return rows


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Seed holdings into Supabase/Postgres.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete existing holdings for the selected user(s) before seeding.",
    )
    parser.add_argument(
        "--user-id",
        default=DEFAULT_USER_ID or None,
        metavar="UUID",
        help="Fallback user id when CSV is missing (or set PORTFOLIO_USER_ID).",
    )
    parser.add_argument(
        "--seed-csv",
        default="data/seed_holdings.csv",
        metavar="PATH",
        help="CSV path. If missing, falls back to built-in demo data.",
    )
    args = parser.parse_args()

    fallback_user_id = args.user_id or resolve_default_user_id()

    try:
        seeds = load_seed_rows(Path(args.seed_csv), fallback_user_id=fallback_user_id)
    except ValueError as exc:
        print(f"Error loading seed data: {exc}")
        sys.exit(1)

    user_ids = sorted({row[0] for row in seeds})

    conn = initialize_database()
    try:
        if args.force:
            with conn.cursor() as cur:
                for uid in user_ids:
                    cur.execute("DELETE FROM public.holdings WHERE user_id = %s", (uid,))
            conn.commit()
            print(f"Existing holdings cleared for user(s): {', '.join(user_ids)}")
        else:
            existing = get_all_holdings(conn, user_id=user_ids[0])
            if existing:
                print(
                    f"Holdings already exist for {user_ids[0]} ({len(existing)} row(s)). "
                    "Use --force to overwrite."
                )
                sys.exit(1)

        for user_id, ticker, shares, invested_amount, currency, platform in seeds:
            row_id = insert_holding(
                conn=conn,
                user_id=user_id,
                ticker=ticker,
                shares_owned=shares,
                invested_amount=invested_amount,
                currency=currency,
                platform=platform,
            )
            print(
                f"  Upserted holding id={row_id}: {shares} x {ticker} "
                f"(invested {invested_amount} {currency}) [{platform}] user={user_id}"
            )

        print(f"\nSeeded {len(seeds)} holdings into Supabase/Postgres")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
