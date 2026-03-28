"""Unit tests for market_data and fx_data services (fully offline)."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.services.fx_data import get_fx_rate_to_sgd, get_supported_currencies_from_holdings
from src.services.market_data import get_latest_price, get_latest_prices


def _close_df_single(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"Close": values})


def _close_df_multi(data: dict[str, list[float]]) -> pd.DataFrame:
    cols = pd.MultiIndex.from_product([("Close",), list(data.keys())])
    rows = list(zip(*data.values()))
    return pd.DataFrame(rows, columns=cols)


@patch("src.services.market_data.yf.Ticker")
def test_get_latest_price_success(mock_ticker: MagicMock) -> None:
    mock_ticker.return_value.history.return_value = _close_df_single([100.0, 101.25])
    price = get_latest_price("AAPL")
    assert price == pytest.approx(101.25)


@patch("src.services.market_data.yf.Ticker")
def test_get_latest_price_empty_returns_none(mock_ticker: MagicMock) -> None:
    mock_ticker.return_value.history.return_value = pd.DataFrame()
    assert get_latest_price("AAPL") is None


@patch("src.services.market_data.yf.download")
def test_get_latest_prices_batch_multi_ticker(mock_download: MagicMock) -> None:
    mock_download.return_value = _close_df_multi({"AAPL": [100.0, 102.0], "MSFT": [200.0, 201.5]})
    out = get_latest_prices(["AAPL", "MSFT"])
    assert out["AAPL"] == pytest.approx(102.0)
    assert out["MSFT"] == pytest.approx(201.5)


@patch("src.services.market_data._fetch_individually")
@patch("src.services.market_data.yf.download")
def test_get_latest_prices_batch_failure_falls_back(mock_download: MagicMock, mock_fallback: MagicMock) -> None:
    mock_download.side_effect = RuntimeError("boom")
    mock_fallback.return_value = {"AAPL": 123.45}
    out = get_latest_prices(["AAPL"])
    assert out == {"AAPL": 123.45}
    mock_fallback.assert_called_once_with(["AAPL"])


def test_get_latest_prices_empty_input() -> None:
    assert get_latest_prices([]) == {}


def test_get_fx_rate_sgd_is_one() -> None:
    assert get_fx_rate_to_sgd("SGD", "2026-03-28", conn=None) == pytest.approx(1.0)


@patch("src.services.fx_data.get_currency_rate")
@patch("src.services.fx_data._fetch_rate_from_yfinance")
def test_get_fx_rate_uses_cache_when_available(mock_fetch: MagicMock, mock_get_rate: MagicMock) -> None:
    fake_conn = object()
    mock_get_rate.return_value = 1.3456
    rate = get_fx_rate_to_sgd("USD", "2026-03-28", conn=fake_conn)
    assert rate == pytest.approx(1.3456)
    mock_fetch.assert_not_called()


@patch("src.services.fx_data.insert_currency_rate")
@patch("src.services.fx_data.get_currency_rate")
@patch("src.services.fx_data._fetch_rate_from_yfinance")
def test_get_fx_rate_fetches_and_caches_when_missing(
    mock_fetch: MagicMock,
    mock_get_rate: MagicMock,
    mock_insert: MagicMock,
) -> None:
    fake_conn = object()
    mock_get_rate.return_value = None
    mock_fetch.return_value = 1.31

    rate = get_fx_rate_to_sgd("USD", "2026-03-28", conn=fake_conn)

    assert rate == pytest.approx(1.31)
    mock_insert.assert_called_once_with(fake_conn, "USD", 1.31, "2026-03-28")


@patch("src.services.fx_data._fetch_rate_from_yfinance")
def test_get_fx_rate_raises_when_unavailable(mock_fetch: MagicMock) -> None:
    mock_fetch.return_value = None
    with pytest.raises(ValueError):
        get_fx_rate_to_sgd("USD", "2026-03-28", conn=None)


def test_get_supported_currencies_from_holdings() -> None:
    class H:
        def __init__(self, ccy: str):
            self.currency = ccy

    holdings = [H("USD"), H("SGD"), H("usd"), H("HKD")]
    out = get_supported_currencies_from_holdings(holdings)
    assert out == ["HKD", "USD"]
