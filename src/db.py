"""SQLite database layer for the portfolio tracker.

All SQL uses parameterised queries; no string interpolation of user data.
"""

import sqlite3
from pathlib import Path
from typing import Optional

from src.config import DB_PATH
from src.models import DailyPrice, Holding
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


# ── Connection ────────────────────────────────────────────────────────────────


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open (or create) the SQLite database and return a connection.

    Foreign-key enforcement is enabled on every connection.

    Args:
        db_path: Filesystem path to the SQLite file.

    Returns:
        An open :class:`sqlite3.Connection`.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── Schema ────────────────────────────────────────────────────────────────────


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all required tables if they do not already exist.

    Args:
        conn: An open database connection.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS holdings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT    NOT NULL,
            shares_owned    REAL    NOT NULL,
            cost_per_share  REAL    NOT NULL,
            currency        TEXT    NOT NULL,
            platform        TEXT    NOT NULL,
            created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS daily_prices (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            holding_id          INTEGER NOT NULL,
            ticker              TEXT    NOT NULL,
            price_per_share     REAL    NOT NULL,
            date                TEXT    NOT NULL,
            market_value        REAL    NOT NULL,
            profit              REAL    NOT NULL,
            market_value_sgd    REAL    NOT NULL,
            profit_sgd          REAL    NOT NULL,
            created_at          TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (holding_id) REFERENCES holdings(id),
            UNIQUE (holding_id, date)
        );

        CREATE TABLE IF NOT EXISTS currencies (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            currency    TEXT    NOT NULL,
            rate        REAL    NOT NULL,
            date        TEXT    NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (currency, date)
        );
        """
    )
    conn.commit()
    logger.debug("Tables verified / created.")


def initialize_database(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open the database, create tables, and return the connection.

    This is the standard entry-point for bootstrapping the database.

    Args:
        db_path: Path to the SQLite file (created if absent).

    Returns:
        An open :class:`sqlite3.Connection` ready for use.
    """
    logger.info("Initialising database at %s", db_path)
    conn = get_connection(db_path)
    create_tables(conn)
    return conn


# ── Holdings ─────────────────────────────────────────────────────────────────


def insert_holding(
    conn: sqlite3.Connection,
    ticker: str,
    shares_owned: float,
    cost_per_share: float,
    currency: str,
    platform: str,
) -> int:
    """Insert a new holding and return its auto-assigned *id*.

    Args:
        conn:           Open database connection.
        ticker:         Stock ticker symbol (e.g. ``"AAPL"``).
        shares_owned:   Number of shares held.
        cost_per_share: Average cost basis per share (native currency).
        currency:       ISO currency code (e.g. ``"USD"``).
        platform:       Brokerage / platform name (e.g. ``"Moomoo"``).

    Returns:
        The ``id`` of the newly inserted row.
    """
    cursor = conn.execute(
        """
        INSERT INTO holdings (ticker, shares_owned, cost_per_share, currency, platform)
        VALUES (?, ?, ?, ?, ?)
        """,
        (ticker, shares_owned, cost_per_share, currency, platform),
    )
    conn.commit()
    row_id: int = cursor.lastrowid  # type: ignore[assignment]
    logger.debug("Inserted holding id=%d (%s @ %s)", row_id, ticker, platform)
    return row_id


def get_all_holdings(conn: sqlite3.Connection) -> list[Holding]:
    """Return all holdings ordered by id.

    Args:
        conn: Open database connection.

    Returns:
        List of :class:`~src.models.Holding` instances.
    """
    rows = conn.execute(
        "SELECT id, ticker, shares_owned, cost_per_share, currency, platform, "
        "created_at, updated_at FROM holdings ORDER BY id"
    ).fetchall()
    return [
        Holding(
            id=row["id"],
            ticker=row["ticker"],
            shares_owned=row["shares_owned"],
            cost_per_share=row["cost_per_share"],
            currency=row["currency"],
            platform=row["platform"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def get_holding_by_id(conn: sqlite3.Connection, holding_id: int) -> Optional[Holding]:
    """Fetch a single holding by primary key.

    Args:
        conn:       Open database connection.
        holding_id: Primary key of the holding to retrieve.

    Returns:
        A :class:`~src.models.Holding` if found, otherwise ``None``.
    """
    row = conn.execute(
        "SELECT id, ticker, shares_owned, cost_per_share, currency, platform, "
        "created_at, updated_at FROM holdings WHERE id = ?",
        (holding_id,),
    ).fetchone()
    if row is None:
        return None
    return Holding(
        id=row["id"],
        ticker=row["ticker"],
        shares_owned=row["shares_owned"],
        cost_per_share=row["cost_per_share"],
        currency=row["currency"],
        platform=row["platform"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def update_holding(
    conn: sqlite3.Connection,
    holding_id: int,
    shares_owned: Optional[float] = None,
    cost_per_share: Optional[float] = None,
    platform: Optional[str] = None,
) -> None:
    """Update mutable fields of an existing holding.

    Only fields passed as non-``None`` are updated. ``updated_at`` is always
    refreshed to the current timestamp.

    Args:
        conn:           Open database connection.
        holding_id:     Primary key of the holding to update.
        shares_owned:   New share count, or ``None`` to leave unchanged.
        cost_per_share: New cost basis, or ``None`` to leave unchanged.
        platform:       New platform name, or ``None`` to leave unchanged.
    """
    updates: list[str] = ["updated_at = CURRENT_TIMESTAMP"]
    params: list[object] = []
    if shares_owned is not None:
        updates.append("shares_owned = ?")
        params.append(shares_owned)
    if cost_per_share is not None:
        updates.append("cost_per_share = ?")
        params.append(cost_per_share)
    if platform is not None:
        updates.append("platform = ?")
        params.append(platform)
    params.append(holding_id)
    conn.execute(
        f"UPDATE holdings SET {', '.join(updates)} WHERE id = ?",  # noqa: S608
        params,
    )
    conn.commit()
    logger.debug("Updated holding id=%d", holding_id)


# ── Currency rates ─────────────────────────────────────────────────────────────


def insert_currency_rate(
    conn: sqlite3.Connection,
    currency: str,
    rate: float,
    date: str,
) -> None:
    """Insert a daily FX rate; silently ignores duplicate (currency, date) pairs.

    Args:
        conn:     Open database connection.
        currency: ISO currency code (e.g. ``"USD"``).
        rate:     Exchange rate: how much 1 unit of *currency* is worth in SGD.
        date:     ISO-8601 date string ``YYYY-MM-DD``.
    """
    conn.execute(
        "INSERT OR IGNORE INTO currencies (currency, rate, date) VALUES (?, ?, ?)",
        (currency, rate, date),
    )
    conn.commit()
    logger.debug("Currency rate stored: %s = %.6f SGD on %s", currency, rate, date)


def get_currency_rate(
    conn: sqlite3.Connection,
    currency: str,
    date: str,
) -> Optional[float]:
    """Look up a stored FX rate for a given currency and date.

    Args:
        conn:     Open database connection.
        currency: ISO currency code.
        date:     ISO-8601 date string ``YYYY-MM-DD``.

    Returns:
        The rate as a float, or ``None`` if no record exists.
    """
    row = conn.execute(
        "SELECT rate FROM currencies WHERE currency = ? AND date = ?",
        (currency, date),
    ).fetchone()
    return float(row["rate"]) if row else None


# ── Daily prices ──────────────────────────────────────────────────────────────


def insert_daily_price(
    conn: sqlite3.Connection,
    holding_id: int,
    ticker: str,
    price_per_share: float,
    date: str,
    market_value: float,
    profit: float,
    market_value_sgd: float,
    profit_sgd: float,
) -> bool:
    """Insert a daily price snapshot.

    The ``UNIQUE(holding_id, date)`` constraint prevents duplicates. If a row
    already exists for the same holding and date the insert is skipped and
    ``False`` is returned.

    Args:
        conn:             Open database connection.
        holding_id:       FK reference to the holdings table.
        ticker:           Stock ticker symbol.
        price_per_share:  Latest close price (native currency).
        date:             ISO-8601 date string ``YYYY-MM-DD``.
        market_value:     shares × price (native currency).
        profit:           Unrealised P&L (native currency).
        market_value_sgd: *market_value* converted to SGD.
        profit_sgd:       *profit* converted to SGD.

    Returns:
        ``True`` if a new row was inserted, ``False`` if it already existed.
    """
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO daily_prices
            (holding_id, ticker, price_per_share, date,
             market_value, profit, market_value_sgd, profit_sgd)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            holding_id,
            ticker,
            price_per_share,
            date,
            market_value,
            profit,
            market_value_sgd,
            profit_sgd,
        ),
    )
    conn.commit()
    inserted = cursor.rowcount == 1
    if inserted:
        logger.debug(
            "Daily price inserted: holding_id=%d %s on %s", holding_id, ticker, date
        )
    else:
        logger.debug(
            "Daily price skipped (duplicate): holding_id=%d %s on %s",
            holding_id,
            ticker,
            date,
        )
    return inserted


def get_daily_prices_by_date(
    conn: sqlite3.Connection,
    date: str,
) -> list[DailyPrice]:
    """Return all daily price rows for a given date.

    Args:
        conn: Open database connection.
        date: ISO-8601 date string ``YYYY-MM-DD``.

    Returns:
        List of :class:`~src.models.DailyPrice` objects.
    """
    rows = conn.execute(
        "SELECT id, holding_id, ticker, price_per_share, date, "
        "market_value, profit, market_value_sgd, profit_sgd, created_at "
        "FROM daily_prices WHERE date = ? ORDER BY id",
        (date,),
    ).fetchall()
    return [
        DailyPrice(
            id=row["id"],
            holding_id=row["holding_id"],
            ticker=row["ticker"],
            price_per_share=row["price_per_share"],
            date=row["date"],
            market_value=row["market_value"],
            profit=row["profit"],
            market_value_sgd=row["market_value_sgd"],
            profit_sgd=row["profit_sgd"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
