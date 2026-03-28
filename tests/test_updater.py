"""Tests for the daily updater service (offline — no network calls)."""

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.db import get_daily_prices_by_date, initialize_database, insert_holding
from src.services.updater import UpdateSummary, run_daily_update

FAKE_DATE = "2099-11-15"
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
PORTFOLIO_USER_ID = os.getenv("PORTFOLIO_USER_ID")

if not SUPABASE_DB_URL or not PORTFOLIO_USER_ID:
    pytest.skip(
        "Supabase integration tests require SUPABASE_DB_URL and PORTFOLIO_USER_ID",
        allow_module_level=True,
    )


def _cleanup(conn, ticker_prefix: str = "TUP_") -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM public.daily_prices WHERE ticker LIKE %s", (f"{ticker_prefix}%",))
        cur.execute(
            "DELETE FROM public.holdings WHERE user_id = %s AND ticker LIKE %s",
            (PORTFOLIO_USER_ID, f"{ticker_prefix}%"),
        )
    conn.commit()


@pytest.fixture()
def seeded_conn():
    conn = initialize_database()
    _cleanup(conn)
    insert_holding(
        conn,
        user_id=PORTFOLIO_USER_ID,
        ticker="TUP_AAPL",
        shares_owned=10,
        invested_amount=1500.0,
        currency="USD",
        platform="Moomoo",
    )
    insert_holding(
        conn,
        user_id=PORTFOLIO_USER_ID,
        ticker="TUP_D05.SI",
        shares_owned=100,
        invested_amount=3500.0,
        currency="SGD",
        platform="Tiger",
    )
    yield conn
    _cleanup(conn)
    conn.close()


def _make_price_patch(prices: dict[str, float]) -> MagicMock:
    return MagicMock(return_value=prices)


def _make_fx_patch(rate: float = 1.35) -> MagicMock:
    def _fx(currency: str, date: str, conn=None) -> float:
        return 1.0 if currency.upper() == "SGD" else rate

    return MagicMock(side_effect=_fx)


@patch("src.services.updater.get_fx_rate_to_sgd")
@patch("src.services.updater.get_latest_prices")
def test_successful_update(mock_prices: MagicMock, mock_fx: MagicMock, seeded_conn) -> None:
    mock_prices.side_effect = _make_price_patch({"TUP_AAPL": 200.0, "TUP_D05.SI": 40.0})
    mock_fx.side_effect = _make_fx_patch(1.35)

    summary = run_daily_update(user_id=PORTFOLIO_USER_ID, date=FAKE_DATE)

    assert summary.total_holdings >= 2
    assert summary.successful >= 2
    assert summary.failed == 0
    assert summary.total_market_value_sgd > 0


@patch("src.services.updater.get_fx_rate_to_sgd")
@patch("src.services.updater.get_latest_prices")
def test_duplicate_update_skipped(mock_prices: MagicMock, mock_fx: MagicMock, seeded_conn) -> None:
    mock_prices.side_effect = _make_price_patch({"TUP_AAPL": 200.0, "TUP_D05.SI": 40.0})
    mock_fx.side_effect = _make_fx_patch(1.35)

    run_daily_update(user_id=PORTFOLIO_USER_ID, date=FAKE_DATE)

    mock_prices.side_effect = _make_price_patch({"TUP_AAPL": 210.0, "TUP_D05.SI": 42.0})
    mock_fx.side_effect = _make_fx_patch(1.36)
    summary2 = run_daily_update(user_id=PORTFOLIO_USER_ID, date=FAKE_DATE)

    assert summary2.skipped >= 2

    rows = [r for r in get_daily_prices_by_date(seeded_conn, FAKE_DATE) if r.ticker == "TUP_AAPL"]
    assert rows
    assert rows[0].price_per_share == pytest.approx(200.0)


@patch("src.services.updater.get_fx_rate_to_sgd")
@patch("src.services.updater.get_latest_prices")
def test_missing_price_counted_as_failed(mock_prices: MagicMock, mock_fx: MagicMock, seeded_conn) -> None:
    mock_prices.side_effect = _make_price_patch({"TUP_D05.SI": 40.0})
    mock_fx.side_effect = _make_fx_patch(1.35)

    summary = run_daily_update(user_id=PORTFOLIO_USER_ID, date=FAKE_DATE)
    assert summary.failed >= 1


@patch("src.services.updater.get_latest_prices")
def test_no_holdings_returns_empty_summary(mock_prices: MagicMock) -> None:
    empty_user_id = str(uuid.uuid4())
    summary = run_daily_update(user_id=empty_user_id, date=FAKE_DATE)

    assert summary.total_holdings == 0
    assert summary.successful == 0
    mock_prices.assert_not_called()


@patch("src.services.updater.get_fx_rate_to_sgd")
@patch("src.services.updater.get_latest_prices")
def test_sgd_holding_uses_fx_rate_one(mock_prices: MagicMock, mock_fx: MagicMock) -> None:
    conn = initialize_database()
    ticker = f"TUP_SGD_{uuid.uuid4().hex[:6]}"
    try:
        insert_holding(
            conn,
            user_id=PORTFOLIO_USER_ID,
            ticker=ticker,
            shares_owned=100,
            invested_amount=3500.0,
            currency="SGD",
            platform="Tiger",
        )
        mock_prices.side_effect = _make_price_patch({ticker: 40.0})
        mock_fx.side_effect = _make_fx_patch(1.35)

        summary = run_daily_update(user_id=PORTFOLIO_USER_ID, date="2099-11-16")

        assert summary.total_market_value_sgd >= 4000.0
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public.daily_prices WHERE ticker = %s", (ticker,))
            cur.execute(
                "DELETE FROM public.holdings WHERE user_id = %s AND ticker = %s",
                (PORTFOLIO_USER_ID, ticker),
            )
        conn.commit()
        conn.close()


def test_update_summary_str() -> None:
    s = UpdateSummary(
        date="2024-01-15",
        total_holdings=2,
        successful=2,
        skipped=0,
        failed=0,
        total_market_value_sgd=10000.0,
        total_profit_sgd=500.0,
    )
    text = str(s)
    assert "2024-01-15" in text
    assert "10,000.00" in text
