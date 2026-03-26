"""Tests for the daily updater service (offline — no network calls)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.db import (
    get_all_holdings,
    get_daily_prices_by_date,
    initialize_database,
    insert_holding,
)
from src.services.updater import UpdateSummary, run_daily_update


FAKE_DATE = "2024-01-15"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Return path to a pre-seeded test database."""
    path = tmp_path / "test_updater.db"
    conn = initialize_database(path)
    insert_holding(conn, "AAPL", 10, 150.0, "USD", "Moomoo")
    insert_holding(conn, "D05.SI", 100, 35.0, "SGD", "Tiger")
    conn.close()
    return path


def _make_price_patch(prices: dict) -> MagicMock:
    """Return a mock for get_latest_prices that returns *prices*."""
    m = MagicMock(return_value=prices)
    return m


def _make_fx_patch(rate: float = 1.35) -> MagicMock:
    """Return a mock for get_fx_rate_to_sgd.

    SGD always returns 1.0; USD returns *rate*.
    """
    def _fx(currency: str, date: str, conn=None) -> float:
        return 1.0 if currency.upper() == "SGD" else rate

    return MagicMock(side_effect=_fx)


# ── Basic update ──────────────────────────────────────────────────────────────


@patch("src.services.updater.get_fx_rate_to_sgd")
@patch("src.services.updater.get_latest_prices")
def test_successful_update(mock_prices: MagicMock, mock_fx: MagicMock, db_path: Path) -> None:
    mock_prices.side_effect = _make_price_patch({"AAPL": 200.0, "D05.SI": 40.0})
    mock_fx.side_effect = _make_fx_patch(1.35)

    summary = run_daily_update(db_path=db_path, date=FAKE_DATE)

    assert summary.total_holdings == 2
    assert summary.successful == 2
    assert summary.skipped == 0
    assert summary.failed == 0
    assert summary.total_market_value_sgd > 0


@patch("src.services.updater.get_fx_rate_to_sgd")
@patch("src.services.updater.get_latest_prices")
def test_duplicate_update_skipped(mock_prices: MagicMock, mock_fx: MagicMock, db_path: Path) -> None:
    """Running the updater twice on the same date should skip the second time."""
    mock_prices.side_effect = _make_price_patch({"AAPL": 200.0, "D05.SI": 40.0})
    mock_fx.side_effect = _make_fx_patch(1.35)

    run_daily_update(db_path=db_path, date=FAKE_DATE)

    # Reset mocks and run again
    mock_prices.side_effect = _make_price_patch({"AAPL": 210.0, "D05.SI": 42.0})
    mock_fx.side_effect = _make_fx_patch(1.36)
    summary2 = run_daily_update(db_path=db_path, date=FAKE_DATE)

    assert summary2.skipped == 2
    assert summary2.successful == 0

    # Stored prices must still reflect first run
    conn = initialize_database(db_path)
    rows = get_daily_prices_by_date(conn, FAKE_DATE)
    conn.close()
    aapl_rows = [r for r in rows if r.ticker == "AAPL"]
    assert aapl_rows[0].price_per_share == pytest.approx(200.0)


# ── Missing price ─────────────────────────────────────────────────────────────


@patch("src.services.updater.get_fx_rate_to_sgd")
@patch("src.services.updater.get_latest_prices")
def test_missing_price_counted_as_failed(
    mock_prices: MagicMock, mock_fx: MagicMock, db_path: Path
) -> None:
    """A holding whose ticker has no price data should count as failed."""
    mock_prices.side_effect = _make_price_patch({"D05.SI": 40.0})  # AAPL missing
    mock_fx.side_effect = _make_fx_patch(1.35)

    summary = run_daily_update(db_path=db_path, date=FAKE_DATE)

    assert summary.failed == 1
    assert summary.successful == 1


# ── No holdings ──────────────────────────────────────────────────────────────


@patch("src.services.updater.get_latest_prices")
def test_no_holdings_returns_empty_summary(mock_prices: MagicMock, tmp_path: Path) -> None:
    empty_db = tmp_path / "empty.db"
    conn = initialize_database(empty_db)
    conn.close()

    summary = run_daily_update(db_path=empty_db, date=FAKE_DATE)

    assert summary.total_holdings == 0
    assert summary.successful == 0
    mock_prices.assert_not_called()


# ── SGD FX rate ───────────────────────────────────────────────────────────────


@patch("src.services.updater.get_fx_rate_to_sgd")
@patch("src.services.updater.get_latest_prices")
def test_sgd_holding_uses_fx_rate_one(
    mock_prices: MagicMock, mock_fx: MagicMock, tmp_path: Path
) -> None:
    """SGD holdings should have market_value_sgd == market_value (fx = 1.0)."""
    db = tmp_path / "sgd.db"
    conn = initialize_database(db)
    insert_holding(conn, "D05.SI", 100, 35.0, "SGD", "Tiger")
    conn.close()

    mock_prices.side_effect = _make_price_patch({"D05.SI": 40.0})
    mock_fx.side_effect = _make_fx_patch(1.35)  # only called for non-SGD

    summary = run_daily_update(db_path=db, date=FAKE_DATE)

    assert summary.successful == 1
    # Market value in SGD: 100 * 40.0 * 1.0 = 4000
    assert summary.total_market_value_sgd == pytest.approx(4000.0)


# ── UpdateSummary __str__ ─────────────────────────────────────────────────────


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
