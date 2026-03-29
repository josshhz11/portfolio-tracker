"""PostgreSQL database layer for the portfolio tracker (Supabase compatible)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import psycopg
from psycopg.rows import dict_row

from src.config import BASE_DIR, DEFAULT_USER_ID, SUPABASE_DB_URL
from src.models import DailyPrice, DailySnapshot, Holding
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


def _require_db_url() -> str:
    if not SUPABASE_DB_URL:
        raise ValueError(
            "SUPABASE_DB_URL is not set. Configure it in your environment or GitHub Actions secrets."
        )
    return SUPABASE_DB_URL


def get_connection(_db_path: Optional[Path] = None) -> psycopg.Connection:
    """Open a Postgres connection (db path is ignored for compatibility)."""
    conn = psycopg.connect(_require_db_url(), row_factory=dict_row)
    return conn


def create_tables(conn: psycopg.Connection) -> None:
    """Create tables using the SQL schema file in data/schema.sql."""
    schema_path = BASE_DIR / "data" / "schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    schema_sql = schema_path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()


def initialize_database(_db_path: Optional[Path] = None) -> psycopg.Connection:
    """Connect and ensure required tables exist."""
    conn = get_connection(None)
    create_tables(conn)
    logger.info("Database connection initialised against Supabase/Postgres")
    return conn


def insert_holding(
    conn: psycopg.Connection,
    user_id: str,
    ticker: str,
    shares_owned: float,
    invested_amount: float,
    currency: str,
    platform: str,
) -> int:
    """Insert/update a holding and return its id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.holdings
                (user_id, ticker, shares_owned, invested_amount, currency, platform)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, ticker, platform, currency)
            DO UPDATE SET
                shares_owned = EXCLUDED.shares_owned,
                invested_amount = EXCLUDED.invested_amount,
                updated_at = NOW()
            RETURNING id
            """,
            (user_id, ticker, shares_owned, invested_amount, currency, platform),
        )
        row = cur.fetchone()
    conn.commit()
    return int(row["id"])  # type: ignore[index]


def get_all_holdings(conn: psycopg.Connection, user_id: Optional[str] = None) -> list[Holding]:
    """Return all holdings, optionally filtered by user_id."""
    with conn.cursor() as cur:
        if user_id:
            cur.execute(
                """
                SELECT id, user_id::text AS user_id, ticker, shares_owned, invested_amount,
                       currency, platform, created_at::text AS created_at, updated_at::text AS updated_at
                FROM public.holdings
                WHERE user_id = %s
                ORDER BY id
                """,
                (user_id,),
            )
        else:
            cur.execute(
                """
                SELECT id, user_id::text AS user_id, ticker, shares_owned, invested_amount,
                       currency, platform, created_at::text AS created_at, updated_at::text AS updated_at
                FROM public.holdings
                ORDER BY id
                """
            )
        rows = cur.fetchall()

    return [
        Holding(
            id=int(row["id"]),
            user_id=row["user_id"],
            ticker=row["ticker"],
            shares_owned=float(row["shares_owned"]),
            invested_amount=float(row["invested_amount"]),
            currency=row["currency"],
            platform=row["platform"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def get_holding_by_id(conn: psycopg.Connection, holding_id: int) -> Optional[Holding]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, user_id::text AS user_id, ticker, shares_owned, invested_amount,
                   currency, platform, created_at::text AS created_at, updated_at::text AS updated_at
            FROM public.holdings
            WHERE id = %s
            """,
            (holding_id,),
        )
        row = cur.fetchone()

    if row is None:
        return None

    return Holding(
        id=int(row["id"]),
        user_id=row["user_id"],
        ticker=row["ticker"],
        shares_owned=float(row["shares_owned"]),
        invested_amount=float(row["invested_amount"]),
        currency=row["currency"],
        platform=row["platform"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def update_holding(
    conn: psycopg.Connection,
    holding_id: int,
    shares_owned: Optional[float] = None,
    invested_amount: Optional[float] = None,
    platform: Optional[str] = None,
) -> None:
    updates: list[str] = ["updated_at = NOW()"]
    params: list[object] = []
    if shares_owned is not None:
        updates.append("shares_owned = %s")
        params.append(shares_owned)
    if invested_amount is not None:
        updates.append("invested_amount = %s")
        params.append(invested_amount)
    if platform is not None:
        updates.append("platform = %s")
        params.append(platform)
    params.append(holding_id)

    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE public.holdings SET {', '.join(updates)} WHERE id = %s",
            params,
        )
    conn.commit()


def insert_currency_rate(conn: psycopg.Connection, currency: str, rate: float, date: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.currencies (currency, rate, rate_date)
            VALUES (%s, %s, %s)
            ON CONFLICT (currency, rate_date) DO NOTHING
            """,
            (currency, rate, date),
        )
    conn.commit()


def get_currency_rate(conn: psycopg.Connection, currency: str, date: str) -> Optional[float]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT rate FROM public.currencies WHERE currency = %s AND rate_date = %s",
            (currency, date),
        )
        row = cur.fetchone()
    return float(row["rate"]) if row else None


def insert_daily_price(
    conn: psycopg.Connection,
    ticker: str,
    price_per_share: float,
    date: str,
) -> bool:
    """Insert daily ticker price if missing; returns True when inserted."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.daily_prices (ticker, price_per_share, price_date)
            VALUES (%s, %s, %s)
            ON CONFLICT (ticker, price_date) DO NOTHING
            """,
            (ticker, price_per_share, date),
        )
        inserted = cur.rowcount == 1
    conn.commit()
    return inserted


def get_daily_prices_by_date(conn: psycopg.Connection, date: str) -> list[DailyPrice]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, ticker, price_per_share, price_date::text AS date, created_at::text AS created_at
            FROM public.daily_prices
            WHERE price_date = %s
            ORDER BY ticker
            """,
            (date,),
        )
        rows = cur.fetchall()

    return [
        DailyPrice(
            id=int(row["id"]),
            ticker=row["ticker"],
            price_per_share=float(row["price_per_share"]),
            date=row["date"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_daily_snapshot_by_date(
    conn: psycopg.Connection,
    date: str,
    user_id: Optional[str] = None,
    exclude_user_id: Optional[str] = None,
) -> list[DailySnapshot]:
    """Compute per-holding snapshot from holdings + daily_prices + currencies for a date."""
    sql = """
        SELECT
            h.id AS holding_id,
            h.ticker,
            h.shares_owned,
            h.invested_amount,
            h.currency,
            h.platform,
            dp.price_per_share,
            COALESCE(c.rate, 1) AS fx_rate
        FROM public.holdings h
        JOIN public.daily_prices dp
          ON dp.ticker = h.ticker
         AND dp.price_date = %s
        LEFT JOIN public.currencies c
          ON c.currency = h.currency
         AND c.rate_date = %s
        {where_clause}
        ORDER BY h.id
    """
    params: list[object] = [date, date]
    conditions: list[str] = []
    if user_id:
        conditions.append("h.user_id = %s")
        params.append(user_id)
    if exclude_user_id:
        conditions.append("h.user_id <> %s")
        params.append(exclude_user_id)

    where_clause = ""
    if conditions:
        where_clause = f"WHERE {' AND '.join(conditions)}"

    with conn.cursor() as cur:
        cur.execute(sql.format(where_clause=where_clause), tuple(params))
        rows = cur.fetchall()

    snapshots: list[DailySnapshot] = []
    for row in rows:
        shares = float(row["shares_owned"])
        invested = float(row["invested_amount"])
        price = float(row["price_per_share"])
        fx_rate = float(row["fx_rate"])
        market_value = shares * price
        profit = market_value - invested
        snapshots.append(
            DailySnapshot(
                holding_id=int(row["holding_id"]),
                ticker=row["ticker"],
                shares_owned=shares,
                invested_amount=invested,
                cost_per_share=(invested / shares) if shares > 0 else 0.0,
                price_per_share=price,
                currency=row["currency"],
                platform=row["platform"],
                market_value=market_value,
                profit=profit,
                fx_rate=fx_rate,
                market_value_sgd=market_value * fx_rate,
                profit_sgd=profit * fx_rate,
            )
        )
    return snapshots


def upsert_portfolio_snapshot(
    conn: psycopg.Connection,
    user_id: str,
    snapshot: DailySnapshot,
    date: str,
) -> None:
    """Insert or update a portfolio snapshot row for a holding/date."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.portfolio_snapshots (
                user_id,
                holding_id,
                snapshot_date,
                shares_owned,
                invested_amount,
                price_per_share,
                fx_rate,
                market_value,
                market_value_sgd,
                unrealized_profit,
                unrealized_profit_sgd
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (holding_id, snapshot_date)
            DO UPDATE SET
                shares_owned = EXCLUDED.shares_owned,
                invested_amount = EXCLUDED.invested_amount,
                price_per_share = EXCLUDED.price_per_share,
                fx_rate = EXCLUDED.fx_rate,
                market_value = EXCLUDED.market_value,
                market_value_sgd = EXCLUDED.market_value_sgd,
                unrealized_profit = EXCLUDED.unrealized_profit,
                unrealized_profit_sgd = EXCLUDED.unrealized_profit_sgd
            """,
            (
                user_id,
                snapshot.holding_id,
                date,
                snapshot.shares_owned,
                snapshot.invested_amount,
                snapshot.price_per_share,
                snapshot.fx_rate,
                snapshot.market_value,
                snapshot.market_value_sgd,
                snapshot.profit,
                snapshot.profit_sgd,
            ),
        )


def resolve_default_user_id() -> str:
    """Return configured default user id or fail with a clear message."""
    if not DEFAULT_USER_ID:
        raise ValueError(
            "PORTFOLIO_USER_ID is not set. Set it in your environment for seed/show commands."
        )
    return DEFAULT_USER_ID
