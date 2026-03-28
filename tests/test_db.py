"""Tests for src.db using Supabase/Postgres-compatible paths."""

import os
import uuid
from datetime import date

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

SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
PORTFOLIO_USER_ID = os.getenv("PORTFOLIO_USER_ID")

if not SUPABASE_DB_URL or not PORTFOLIO_USER_ID:
    pytest.skip(
        "Supabase integration tests require SUPABASE_DB_URL and PORTFOLIO_USER_ID",
        allow_module_level=True,
    )


@pytest.fixture()
def db_conn():
    conn = initialize_database()
    yield conn
    conn.close()


@pytest.fixture()
def test_ticker() -> str:
    return f"TST_{uuid.uuid4().hex[:8]}"


@pytest.fixture()
def test_date() -> str:
    # Stable valid date format with low chance of clashes across concurrent jobs
    return f"2099-12-{(uuid.uuid4().int % 27) + 1:02d}"


def _cleanup(conn, ticker_prefix: str = "TST_") -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM public.daily_prices WHERE ticker LIKE %s", (f"{ticker_prefix}%",))
        cur.execute(
            "DELETE FROM public.holdings WHERE user_id = %s AND ticker LIKE %s",
            (PORTFOLIO_USER_ID, f"{ticker_prefix}%"),
        )
    conn.commit()


def test_insert_and_get_holding(db_conn, test_ticker: str) -> None:
    _cleanup(db_conn)
    hid = insert_holding(
        db_conn,
        user_id=PORTFOLIO_USER_ID,
        ticker=test_ticker,
        shares_owned=10,
        invested_amount=1500.0,
        currency="USD",
        platform="Moomoo",
    )
    assert hid > 0

    holding = get_holding_by_id(db_conn, hid)
    assert holding is not None
    assert holding.ticker == test_ticker
    assert holding.shares_owned == pytest.approx(10)
    assert holding.invested_amount == pytest.approx(1500.0)
    assert holding.cost_per_share == pytest.approx(150.0)


def test_get_all_holdings_returns_user_rows(db_conn, test_ticker: str) -> None:
    _cleanup(db_conn)
    t2 = f"{test_ticker}_B"
    insert_holding(
        db_conn,
        user_id=PORTFOLIO_USER_ID,
        ticker=test_ticker,
        shares_owned=10,
        invested_amount=1500.0,
        currency="USD",
        platform="Moomoo",
    )
    insert_holding(
        db_conn,
        user_id=PORTFOLIO_USER_ID,
        ticker=t2,
        shares_owned=20,
        invested_amount=3000.0,
        currency="USD",
        platform="IBKR",
    )
    rows = [h for h in get_all_holdings(db_conn, user_id=PORTFOLIO_USER_ID) if h.ticker in {test_ticker, t2}]
    assert len(rows) == 2


def test_update_holding(db_conn, test_ticker: str) -> None:
    _cleanup(db_conn)
    hid = insert_holding(
        db_conn,
        user_id=PORTFOLIO_USER_ID,
        ticker=test_ticker,
        shares_owned=5,
        invested_amount=500.0,
        currency="USD",
        platform="Moomoo",
    )

    update_holding(db_conn, hid, shares_owned=10, invested_amount=1200.0)
    h = get_holding_by_id(db_conn, hid)
    assert h is not None
    assert h.shares_owned == pytest.approx(10)
    assert h.invested_amount == pytest.approx(1200.0)


def test_insert_and_get_currency_rate(db_conn, test_date: str) -> None:
    insert_currency_rate(db_conn, "USD", 1.35, test_date)
    rate = get_currency_rate(db_conn, "USD", test_date)
    assert rate == pytest.approx(1.35)


def test_duplicate_currency_rate_ignored(db_conn, test_date: str) -> None:
    insert_currency_rate(db_conn, "USD", 1.35, test_date)
    insert_currency_rate(db_conn, "USD", 1.99, test_date)
    rate = get_currency_rate(db_conn, "USD", test_date)
    assert rate == pytest.approx(1.35)


def test_insert_and_get_daily_price(db_conn, test_ticker: str, test_date: str) -> None:
    inserted = insert_daily_price(db_conn, test_ticker, 200.0, test_date)
    assert inserted is True

    rows = [r for r in get_daily_prices_by_date(db_conn, test_date) if r.ticker == test_ticker]
    assert len(rows) == 1
    assert rows[0].price_per_share == pytest.approx(200.0)


def test_duplicate_daily_price_ignored(db_conn, test_ticker: str, test_date: str) -> None:
    first = insert_daily_price(db_conn, test_ticker, 200.0, test_date)
    second = insert_daily_price(db_conn, test_ticker, 210.0, test_date)
    assert first is True
    assert second is False

    rows = [r for r in get_daily_prices_by_date(db_conn, test_date) if r.ticker == test_ticker]
    assert len(rows) == 1
    assert rows[0].price_per_share == pytest.approx(200.0)


def test_get_daily_prices_empty_date(db_conn) -> None:
    empty_day = date(1999, 1, 1).isoformat()
    rows = [r for r in get_daily_prices_by_date(db_conn, empty_day) if r.ticker.startswith("TST_")]
    assert rows == []
