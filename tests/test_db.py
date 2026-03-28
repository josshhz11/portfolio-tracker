"""Tests for db.py — database creation, CRUD, and constraint enforcement."""

import sqlite3
from pathlib import Path

import pytest

from src.db import (
    get_all_holdings,
    get_currency_rate,
    get_daily_prices_by_date,
    get_holding_by_id,
    initialize_database,
    insert_currency_rate,
    insert_daily_price,
    insert_holding,
    update_holding,
)


@pytest.fixture()
def db(tmp_path: Path) -> sqlite3.Connection:
    """Return an open, fully-initialised in-memory-like database."""
    conn = initialize_database(tmp_path / "test.db")
    yield conn
    conn.close()


# ── Schema ────────────────────────────────────────────────────────────────────


def test_tables_created(db: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"holdings", "daily_prices", "currencies"} <= tables


def test_double_initialize_is_idempotent(tmp_path: Path) -> None:
    """Calling initialize_database twice must not raise or duplicate tables."""
    p = tmp_path / "idempotent.db"
    c1 = initialize_database(p)
    c1.close()
    c2 = initialize_database(p)
    c2.close()  # No exception means pass


# ── Holdings ─────────────────────────────────────────────────────────────────


def test_insert_and_get_holding(db: sqlite3.Connection) -> None:
    hid = insert_holding(db, "AAPL", 10, 150.0, "USD", "Moomoo")
    assert hid == 1

    holding = get_holding_by_id(db, hid)
    assert holding is not None
    assert holding.ticker == "AAPL"
    assert holding.shares_owned == 10
    assert holding.cost_per_share == 150.0
    assert holding.currency == "USD"
    assert holding.platform == "Moomoo"


def test_get_all_holdings_returns_all(db: sqlite3.Connection) -> None:
    insert_holding(db, "AAPL", 10, 150.0, "USD", "Moomoo")
    insert_holding(db, "D05.SI", 100, 35.0, "SGD", "Tiger")
    holdings = get_all_holdings(db)
    assert len(holdings) == 2
    tickers = {h.ticker for h in holdings}
    assert tickers == {"AAPL", "D05.SI"}


def test_same_ticker_multiple_platforms(db: sqlite3.Connection) -> None:
    insert_holding(db, "D05.SI", 600, 35.827, "SGD", "Tiger")
    insert_holding(db, "D05.SI", 200, 54.0, "SGD", "IBKR")
    holdings = get_all_holdings(db)
    assert len(holdings) == 2


def test_get_holding_by_id_missing_returns_none(db: sqlite3.Connection) -> None:
    assert get_holding_by_id(db, 9999) is None


def test_update_holding(db: sqlite3.Connection) -> None:
    hid = insert_holding(db, "SNAP", 500, 8.5, "USD", "Moomoo")
    update_holding(db, hid, shares_owned=1000, cost_per_share=9.0)
    h = get_holding_by_id(db, hid)
    assert h is not None
    assert h.shares_owned == 1000
    assert h.cost_per_share == 9.0


# ── Currency rates ─────────────────────────────────────────────────────────────


def test_insert_and_get_currency_rate(db: sqlite3.Connection) -> None:
    insert_currency_rate(db, "USD", 1.35, "2024-01-15")
    rate = get_currency_rate(db, "USD", "2024-01-15")
    assert rate == pytest.approx(1.35)


def test_duplicate_currency_rate_ignored(db: sqlite3.Connection) -> None:
    """UNIQUE(currency, date) — second insert must be silently ignored."""
    insert_currency_rate(db, "USD", 1.35, "2024-01-15")
    insert_currency_rate(db, "USD", 1.99, "2024-01-15")  # duplicate
    rate = get_currency_rate(db, "USD", "2024-01-15")
    assert rate == pytest.approx(1.35)  # original value kept


def test_get_currency_rate_missing_returns_none(db: sqlite3.Connection) -> None:
    assert get_currency_rate(db, "EUR", "2024-01-15") is None


# ── Daily prices ──────────────────────────────────────────────────────────────


def test_insert_and_get_daily_price(db: sqlite3.Connection) -> None:
    hid = insert_holding(db, "AAPL", 10, 150.0, "USD", "Moomoo")
    inserted = insert_daily_price(
        db, hid, "AAPL", 200.0, "2024-01-15",
        market_value=2000.0,
        profit=500.0,
        market_value_sgd=2700.0,
        profit_sgd=675.0,
    )
    assert inserted is True

    rows = get_daily_prices_by_date(db, "2024-01-15")
    assert len(rows) == 1
    assert rows[0].price_per_share == pytest.approx(200.0)
    assert rows[0].market_value == pytest.approx(2000.0)


def test_duplicate_daily_price_ignored(db: sqlite3.Connection) -> None:
    """UNIQUE(holding_id, date) — duplicate insert returns False."""
    hid = insert_holding(db, "AAPL", 10, 150.0, "USD", "Moomoo")
    first = insert_daily_price(db, hid, "AAPL", 200.0, "2024-01-15", 2000.0, 500.0, 2700.0, 675.0)
    second = insert_daily_price(db, hid, "AAPL", 210.0, "2024-01-15", 2100.0, 600.0, 2835.0, 810.0)
    assert first is True
    assert second is False

    # Only one row in the database, original values preserved
    rows = get_daily_prices_by_date(db, "2024-01-15")
    assert len(rows) == 1
    assert rows[0].price_per_share == pytest.approx(200.0)


def test_different_holdings_same_ticker_same_date(db: sqlite3.Connection) -> None:
    """Same ticker from two platforms must produce separate daily rows."""
    h1 = insert_holding(db, "D05.SI", 600, 35.827, "SGD", "Tiger")
    h2 = insert_holding(db, "D05.SI", 200, 54.0, "SGD", "IBKR")
    insert_daily_price(db, h1, "D05.SI", 40.0, "2024-01-15", 24000.0, 2503.8, 24000.0, 2503.8)
    insert_daily_price(db, h2, "D05.SI", 40.0, "2024-01-15", 8000.0, -2800.0, 8000.0, -2800.0)
    rows = get_daily_prices_by_date(db, "2024-01-15")
    assert len(rows) == 2


def test_get_daily_prices_empty_date(db: sqlite3.Connection) -> None:
    assert get_daily_prices_by_date(db, "2000-01-01") == []
