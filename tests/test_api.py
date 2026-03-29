"""API contract tests for FastAPI routes (offline with mocked dependencies)."""

from __future__ import annotations

from types import SimpleNamespace

import jwt
import pytest
from fastapi.testclient import TestClient

from src.api import app as api_module
from src.models import DailySnapshot


class _FakeCursor:
    def __init__(self, fetchone_result=None):
        self._fetchone_result = fetchone_result
        self.executed: list[tuple[str, tuple | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query: str, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return self._fetchone_result


class _FakeConnection:
    def __init__(self, fetchone_result=None):
        self._cursor = _FakeCursor(fetchone_result=fetchone_result)
        self.closed = False
        self.committed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


@pytest.fixture()
def client() -> TestClient:
    return TestClient(api_module.app)


def _mock_holding(hid: int = 1, user_id: str = "user-1", ticker: str = "AAPL"):
    return SimpleNamespace(
        id=hid,
        user_id=user_id,
        ticker=ticker,
        shares_owned=10.0,
        invested_amount=1500.0,
        cost_per_share=150.0,
        currency="USD",
        platform="IBKR",
        created_at="2026-03-29T00:00:00+00:00",
        updated_at="2026-03-29T00:00:00+00:00",
    )


def test_root_and_health(client: TestClient) -> None:
    r1 = client.get("/")
    assert r1.status_code == 200
    assert r1.json()["docs"] == "/docs"

    r2 = client.get("/health")
    assert r2.status_code == 200
    assert r2.json() == {"status": "ok"}


def test_list_holdings_returns_contract(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(api_module, "get_connection", lambda: fake_conn)
    monkeypatch.setattr(api_module, "get_all_holdings", lambda conn, user_id: [_mock_holding(user_id=user_id)])

    resp = client.get("/users/abc-123/holdings", headers={"X-User-Id": "abc-123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["limit"] == 100
    assert isinstance(body["items"], list)
    assert body["items"][0]["user_id"] == "abc-123"
    assert body["items"][0]["ticker"] == "AAPL"


def test_list_holdings_requires_auth_header(client: TestClient) -> None:
    resp = client.get("/users/abc-123/holdings")
    assert resp.status_code == 401


def test_list_holdings_rejects_mismatched_user_scope(client: TestClient) -> None:
    resp = client.get("/users/abc-123/holdings", headers={"X-User-Id": "other-user"})
    assert resp.status_code == 403


def test_list_holdings_accepts_valid_jwt_in_jwt_mode(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    test_secret = "this-is-a-32-char-minimum-secret-key"
    monkeypatch.setenv("API_AUTH_MODE", "jwt")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", test_secret)
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    monkeypatch.setattr(api_module, "get_connection", lambda: fake_conn)
    monkeypatch.setattr(api_module, "get_all_holdings", lambda conn, user_id: [_mock_holding(user_id=user_id)])

    token = jwt.encode(
        {"sub": "abc-123", "aud": "authenticated"},
        test_secret,
        algorithm="HS256",
    )
    resp = client.get(
        "/users/abc-123/holdings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["items"][0]["user_id"] == "abc-123"


def test_list_holdings_rejects_missing_jwt_in_jwt_mode(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_AUTH_MODE", "jwt")
    resp = client.get("/users/abc-123/holdings")
    assert resp.status_code == 401


def test_get_holding_not_found(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(api_module, "get_connection", lambda: fake_conn)
    monkeypatch.setattr(api_module, "get_holding_by_id", lambda conn, hid: None)

    resp = client.get("/holdings/999", headers={"X-User-Id": "user-1"})
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_holding_rejects_mismatched_owner(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(api_module, "get_connection", lambda: fake_conn)
    monkeypatch.setattr(api_module, "get_holding_by_id", lambda conn, hid: _mock_holding(user_id="owner-1"))

    resp = client.get("/holdings/1", headers={"X-User-Id": "other-user"})
    assert resp.status_code == 403


def test_create_holding_201(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(api_module, "get_connection", lambda: fake_conn)
    monkeypatch.setattr(api_module, "insert_holding", lambda **kwargs: 77)
    monkeypatch.setattr(api_module, "get_holding_by_id", lambda conn, hid: _mock_holding(hid=hid, user_id="u-1"))

    payload = {
        "ticker": "MSFT",
        "shares_owned": 5,
        "invested_amount": 1000,
        "currency": "USD",
        "platform": "Moomoo",
    }
    resp = client.post("/users/u-1/holdings", json=payload, headers={"X-User-Id": "u-1"})
    assert resp.status_code == 201
    assert resp.json()["id"] == 77


def test_patch_holding_requires_at_least_one_field(client: TestClient) -> None:
    resp = client.patch("/holdings/1", json={}, headers={"X-User-Id": "u-1"})
    assert resp.status_code == 400
    assert "at least one field" in resp.json()["detail"].lower()


def test_delete_holding_not_found_for_user(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection(fetchone_result=None)
    monkeypatch.setattr(api_module, "get_connection", lambda: fake_conn)

    resp = client.delete("/users/u-1/holdings/9", headers={"X-User-Id": "u-1"})
    assert resp.status_code == 404


def test_delete_holding_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection(fetchone_result={"id": 9})
    monkeypatch.setattr(api_module, "get_connection", lambda: fake_conn)

    resp = client.delete("/users/u-1/holdings/9", headers={"X-User-Id": "u-1"})
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert fake_conn.committed is True


def test_update_daily_rejects_bad_date(client: TestClient) -> None:
    resp = client.post("/users/u-1/daily/update", json={"date": "2026/03/29"}, headers={"X-User-Id": "u-1"})
    assert resp.status_code == 400
    assert "yyyy-mm-dd" in resp.json()["detail"].lower()


def test_snapshot_endpoint_filter_and_pagination(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(api_module, "get_connection", lambda: fake_conn)
    monkeypatch.setattr(
        api_module,
        "get_daily_snapshot_by_date",
        lambda conn, date, user_id: [
            DailySnapshot(
                holding_id=1,
                ticker="AAPL",
                shares_owned=10,
                invested_amount=1500,
                cost_per_share=150,
                price_per_share=200,
                currency="USD",
                platform="IBKR",
                market_value=2000,
                profit=500,
                fx_rate=1.35,
                market_value_sgd=2700,
                profit_sgd=675,
            ),
            DailySnapshot(
                holding_id=2,
                ticker="D05.SI",
                shares_owned=100,
                invested_amount=3500,
                cost_per_share=35,
                price_per_share=40,
                currency="SGD",
                platform="Tiger",
                market_value=4000,
                profit=500,
                fx_rate=1.0,
                market_value_sgd=4000,
                profit_sgd=500,
            ),
        ],
    )

    resp = client.get(
        "/users/u-1/daily/snapshot",
        params={"date": "2026-03-29", "currency": "SGD", "limit": 1, "offset": 0},
        headers={"X-User-Id": "u-1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["currency"] == "SGD"


def test_market_prices_validation_and_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    resp_bad = client.get("/market/prices", params={"tickers": "  "})
    assert resp_bad.status_code == 400

    monkeypatch.setattr(api_module, "get_latest_prices", lambda tickers: {"AAPL": 210.0, "MSFT": 410.5})
    resp_ok = client.get("/market/prices", params={"tickers": "AAPL,MSFT"})
    assert resp_ok.status_code == 200
    assert len(resp_ok.json()) == 2


def test_fx_rate_cached_404_and_hit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(api_module, "get_connection", lambda: fake_conn)

    monkeypatch.setattr(api_module, "get_currency_rate", lambda conn, ccy, date: None)
    miss = client.get("/fx/rate/cached", params={"currency": "USD", "date": "2026-03-29"})
    assert miss.status_code == 404

    monkeypatch.setattr(api_module, "get_currency_rate", lambda conn, ccy, date: 1.35)
    hit = client.get("/fx/rate/cached", params={"currency": "USD", "date": "2026-03-29"})
    assert hit.status_code == 200
    assert hit.json()["rate_to_sgd"] == 1.35


def test_seed_holdings_invalid_csv_returns_400(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_module, "resolve_default_user_id", lambda: "u-1")

    def _raise(*args, **kwargs):
        raise ValueError("bad csv")

    monkeypatch.setattr(api_module, "load_seed_rows", _raise)

    resp = client.post("/admin/seed-holdings", json={"force": False, "seed_csv": "data/missing.csv"})
    assert resp.status_code == 400
    assert "bad csv" in resp.json()["detail"]
