#!/usr/bin/env python3
"""Quick connectivity check for Supabase Postgres."""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # noqa: BLE001
    load_dotenv = None

import psycopg


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    if load_dotenv is not None:
        load_dotenv(root / ".env", override=False)

    db_url = os.getenv("SUPABASE_DB_URL", "")
    if not db_url:
        print("SUPABASE_DB_URL is not set.")
        print("Set it in .env or your shell, then re-run this script.")
        return 2

    print("Testing connection to SUPABASE_DB_URL...")
    try:
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute("select current_database(), current_user, now()")
                db_name, user_name, now_ts = cur.fetchone()
                print("Connection successful.")
                print(f"Database: {db_name}")
                print(f"User: {user_name}")
                print(f"Time: {now_ts}")

                cur.execute("select to_regclass('public.holdings'), to_regclass('public.daily_prices'), to_regclass('public.currencies')")
                h, d, c = cur.fetchone()
                print("Tables:")
                print(f"  holdings: {h}")
                print(f"  daily_prices: {d}")
                print(f"  currencies: {c}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Connection failed: {exc}")
        print("Tips:")
        print("1) Prefer Supabase Pooler connection string from Dashboard > Settings > Database > Connection string.")
        print("2) Use the exact URI Supabase gives (host/port/user differ from direct host).")
        print("3) Include sslmode=require in the URI if missing.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
