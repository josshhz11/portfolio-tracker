"""Tests for src.db using Supabase/Postgres-compatible paths."""

import os
import uuid
from datetime import date

import pytest

from src.db import (
    get_all_holdings,
    get_cash_accounts,
    get_currency_rate,
    get_daily_prices_by_date,
    get_holding_by_id,
    initialize_database,
    insert_currency_rate,
    insert_daily_price,
    insert_holding,
    upsert_cash_snapshot,
    update_holding,
)
from src.models import CashSnapshot

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


def _cleanup_cash_and_trade_artifacts(
    conn,
    user_id: str,
    platform_prefix: str,
    ticker_prefix: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM public.cash_snapshots WHERE user_id = %s AND platform LIKE %s",
            (user_id, f"{platform_prefix}%"),
        )
        cur.execute(
            "DELETE FROM public.cash_ledger WHERE user_id = %s AND platform LIKE %s",
            (user_id, f"{platform_prefix}%"),
        )
        cur.execute(
            "DELETE FROM public.trades WHERE user_id = %s AND platform LIKE %s",
            (user_id, f"{platform_prefix}%"),
        )
        cur.execute(
            "DELETE FROM public.cash_accounts WHERE user_id = %s AND platform LIKE %s",
            (user_id, f"{platform_prefix}%"),
        )
        cur.execute(
            "DELETE FROM public.holdings WHERE user_id = %s AND ticker LIKE %s",
            (user_id, f"{ticker_prefix}%"),
        )
    conn.commit()


def _get_cash_balance(conn, user_id: str, platform: str, currency: str) -> float | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT balance
            FROM public.cash_accounts
            WHERE user_id = %s AND platform = %s AND currency = %s
            """,
            (user_id, platform, currency),
        )
        row = cur.fetchone()
    return float(row["balance"]) if row else None


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


def test_cash_ledger_deposit_auto_creates_account_and_updates_balance(db_conn) -> None:
    key = uuid.uuid4().hex[:8].upper()
    platform = f"TCASH_{key}"
    ticker_prefix = f"TCA_{key}"
    _cleanup_cash_and_trade_artifacts(db_conn, PORTFOLIO_USER_ID, platform, ticker_prefix)

    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.cash_ledger (user_id, platform, entry_type, currency, amount, note)
            VALUES (%s, %s, 'DEPOSIT', 'USD', %s, %s)
            """,
            (PORTFOLIO_USER_ID, platform, 1000.0, "test deposit"),
        )
    db_conn.commit()

    balance = _get_cash_balance(db_conn, PORTFOLIO_USER_ID, platform, "USD")
    assert balance == pytest.approx(1000.0)

    accounts = [
        a
        for a in get_cash_accounts(db_conn, user_id=PORTFOLIO_USER_ID)
        if a.platform == platform and a.currency == "USD"
    ]
    assert len(accounts) == 1


def test_cash_ledger_withdrawal_fails_without_sufficient_balance(db_conn) -> None:
    key = uuid.uuid4().hex[:8].upper()
    platform = f"TCASH_{key}"
    ticker_prefix = f"TCA_{key}"
    _cleanup_cash_and_trade_artifacts(db_conn, PORTFOLIO_USER_ID, platform, ticker_prefix)

    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.cash_accounts (user_id, platform, currency, balance)
            VALUES (%s, %s, 'USD', %s)
            """,
            (PORTFOLIO_USER_ID, platform, 100.0),
        )
    db_conn.commit()

    with pytest.raises(Exception, match="Insufficient cash balance"):
        with db_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.cash_ledger (user_id, platform, entry_type, currency, amount, note)
                VALUES (%s, %s, 'WITHDRAWAL', 'USD', %s, %s)
                """,
                (PORTFOLIO_USER_ID, platform, 150.0, "test withdrawal"),
            )
    db_conn.rollback()

    balance = _get_cash_balance(db_conn, PORTFOLIO_USER_ID, platform, "USD")
    assert balance == pytest.approx(100.0)


def test_cash_ledger_fx_exchange_moves_balances(db_conn) -> None:
    key = uuid.uuid4().hex[:8].upper()
    platform = f"TCASH_{key}"
    ticker_prefix = f"TCA_{key}"
    _cleanup_cash_and_trade_artifacts(db_conn, PORTFOLIO_USER_ID, platform, ticker_prefix)

    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.cash_accounts (user_id, platform, currency, balance)
            VALUES (%s, %s, 'SGD', %s)
            """,
            (PORTFOLIO_USER_ID, platform, 1000.0),
        )
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.cash_ledger (
                user_id,
                platform,
                entry_type,
                currency,
                amount,
                counter_currency,
                counter_amount,
                fx_rate,
                note
            )
            VALUES (%s, %s, 'FX_EXCHANGE', 'SGD', %s, 'USD', %s, %s, %s)
            """,
            (PORTFOLIO_USER_ID, platform, 100.0, 75.0, 0.75, "test fx exchange"),
        )
    db_conn.commit()

    sgd_balance = _get_cash_balance(db_conn, PORTFOLIO_USER_ID, platform, "SGD")
    usd_balance = _get_cash_balance(db_conn, PORTFOLIO_USER_ID, platform, "USD")
    assert sgd_balance == pytest.approx(900.0)
    assert usd_balance == pytest.approx(75.0)


def test_cash_ledger_rejects_invalid_fields_for_deposit(db_conn) -> None:
    key = uuid.uuid4().hex[:8].upper()
    platform = f"TCASH_{key}"
    ticker_prefix = f"TCA_{key}"
    _cleanup_cash_and_trade_artifacts(db_conn, PORTFOLIO_USER_ID, platform, ticker_prefix)

    with pytest.raises(Exception, match="chk_cash_ledger_fx_fields"):
        with db_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.cash_ledger (
                    user_id,
                    platform,
                    entry_type,
                    currency,
                    amount,
                    counter_currency,
                    counter_amount,
                    fx_rate,
                    note
                )
                VALUES (%s, %s, 'DEPOSIT', 'USD', %s, 'SGD', %s, %s, %s)
                """,
                (PORTFOLIO_USER_ID, platform, 100.0, 140.0, 1.4, "invalid deposit fields"),
            )
    db_conn.rollback()


def test_trade_buy_updates_holding_posts_ledger_and_debits_cash(db_conn) -> None:
    key = uuid.uuid4().hex[:8].upper()
    platform = f"TCASH_{key}"
    ticker = f"TCA_{key}_BUY"
    _cleanup_cash_and_trade_artifacts(db_conn, PORTFOLIO_USER_ID, platform, ticker)

    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.cash_accounts (user_id, platform, currency, balance)
            VALUES (%s, %s, 'USD', %s)
            """,
            (PORTFOLIO_USER_ID, platform, 1000.0),
        )
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.trades (
                user_id,
                ticker,
                trade_type,
                currency,
                cash_amount,
                shares,
                platform,
                traded_at
            )
            VALUES (%s, %s, 'BUY', 'USD', %s, %s, %s, NOW())
            RETURNING id, holding_id
            """,
            (PORTFOLIO_USER_ID, ticker, 200.0, 2.0, platform),
        )
        trade_row = cur.fetchone()
    db_conn.commit()

    assert trade_row is not None
    trade_id = int(trade_row["id"])
    holding_id = int(trade_row["holding_id"])

    holding = get_holding_by_id(db_conn, holding_id)
    assert holding is not None
    assert holding.ticker == ticker
    assert holding.shares_owned == pytest.approx(2.0)
    assert holding.invested_amount == pytest.approx(200.0)

    balance = _get_cash_balance(db_conn, PORTFOLIO_USER_ID, platform, "USD")
    assert balance == pytest.approx(800.0)

    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT entry_type, amount
            FROM public.cash_ledger
            WHERE trade_id = %s
            """,
            (trade_id,),
        )
        ledger_row = cur.fetchone()

    assert ledger_row is not None
    assert ledger_row["entry_type"] == "TRADE_BUY"
    assert float(ledger_row["amount"]) == pytest.approx(200.0)


def test_trade_buy_fails_without_cash_account(db_conn) -> None:
    key = uuid.uuid4().hex[:8].upper()
    platform = f"TCASH_{key}"
    ticker = f"TCA_{key}_NO_CASH"
    _cleanup_cash_and_trade_artifacts(db_conn, PORTFOLIO_USER_ID, platform, ticker)

    with pytest.raises(Exception, match="No cash account found"):
        with db_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.trades (
                    user_id,
                    ticker,
                    trade_type,
                    currency,
                    cash_amount,
                    shares,
                    platform,
                    traded_at
                )
                VALUES (%s, %s, 'BUY', 'USD', %s, %s, %s, NOW())
                """,
                (PORTFOLIO_USER_ID, ticker, 100.0, 1.0, platform),
            )
    db_conn.rollback()

    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM public.holdings
            WHERE user_id = %s AND ticker = %s AND platform = %s AND currency = 'USD'
            """,
            (PORTFOLIO_USER_ID, ticker, platform),
        )
        row = cur.fetchone()

    assert int(row["cnt"]) == 0


def test_trade_sell_reduces_holding_and_credits_cash(db_conn) -> None:
    key = uuid.uuid4().hex[:8].upper()
    platform = f"TCASH_{key}"
    ticker = f"TCA_{key}_SELL"
    _cleanup_cash_and_trade_artifacts(db_conn, PORTFOLIO_USER_ID, platform, ticker)

    holding_id = insert_holding(
        db_conn,
        user_id=PORTFOLIO_USER_ID,
        ticker=ticker,
        shares_owned=10.0,
        invested_amount=1000.0,
        currency="USD",
        platform=platform,
    )

    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.cash_accounts (user_id, platform, currency, balance)
            VALUES (%s, %s, 'USD', %s)
            """,
            (PORTFOLIO_USER_ID, platform, 100.0),
        )
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.trades (
                user_id,
                holding_id,
                ticker,
                trade_type,
                currency,
                cash_amount,
                shares,
                platform,
                traded_at
            )
            VALUES (%s, %s, %s, 'SELL', 'USD', %s, %s, %s, NOW())
            """,
            (PORTFOLIO_USER_ID, holding_id, ticker, 300.0, 2.0, platform),
        )
    db_conn.commit()

    holding = get_holding_by_id(db_conn, holding_id)
    assert holding is not None
    assert holding.shares_owned == pytest.approx(8.0)
    assert holding.invested_amount == pytest.approx(800.0)

    balance = _get_cash_balance(db_conn, PORTFOLIO_USER_ID, platform, "USD")
    assert balance == pytest.approx(400.0)


def test_trade_sell_fails_when_shares_insufficient(db_conn) -> None:
    key = uuid.uuid4().hex[:8].upper()
    platform = f"TCASH_{key}"
    ticker = f"TCA_{key}_SELL_FAIL"
    _cleanup_cash_and_trade_artifacts(db_conn, PORTFOLIO_USER_ID, platform, ticker)

    holding_id = insert_holding(
        db_conn,
        user_id=PORTFOLIO_USER_ID,
        ticker=ticker,
        shares_owned=1.0,
        invested_amount=100.0,
        currency="USD",
        platform=platform,
    )

    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.cash_accounts (user_id, platform, currency, balance)
            VALUES (%s, %s, 'USD', %s)
            """,
            (PORTFOLIO_USER_ID, platform, 50.0),
        )
    db_conn.commit()

    with pytest.raises(Exception, match="Cannot SELL"):
        with db_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.trades (
                    user_id,
                    holding_id,
                    ticker,
                    trade_type,
                    currency,
                    cash_amount,
                    shares,
                    platform,
                    traded_at
                )
                VALUES (%s, %s, %s, 'SELL', 'USD', %s, %s, %s, NOW())
                """,
                (PORTFOLIO_USER_ID, holding_id, ticker, 200.0, 2.0, platform),
            )
    db_conn.rollback()

    holding = get_holding_by_id(db_conn, holding_id)
    assert holding is not None
    assert holding.shares_owned == pytest.approx(1.0)
    assert holding.invested_amount == pytest.approx(100.0)

    balance = _get_cash_balance(db_conn, PORTFOLIO_USER_ID, platform, "USD")
    assert balance == pytest.approx(50.0)


def test_upsert_cash_snapshot_insert_then_update(db_conn) -> None:
    key = uuid.uuid4().hex[:8].upper()
    platform = f"TCASH_{key}"
    ticker_prefix = f"TCA_{key}"
    _cleanup_cash_and_trade_artifacts(db_conn, PORTFOLIO_USER_ID, platform, ticker_prefix)

    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.cash_accounts (user_id, platform, currency, balance)
            VALUES (%s, %s, 'USD', %s)
            RETURNING id
            """,
            (PORTFOLIO_USER_ID, platform, 500.0),
        )
        account_row = cur.fetchone()
    db_conn.commit()

    assert account_row is not None
    account_id = int(account_row["id"])

    upsert_cash_snapshot(
        db_conn,
        PORTFOLIO_USER_ID,
        CashSnapshot(
            cash_account_id=account_id,
            snapshot_date="2099-12-30",
            platform=platform,
            currency="USD",
            balance=500.0,
            fx_rate=1.35,
            balance_sgd=675.0,
        ),
    )
    db_conn.commit()

    upsert_cash_snapshot(
        db_conn,
        PORTFOLIO_USER_ID,
        CashSnapshot(
            cash_account_id=account_id,
            snapshot_date="2099-12-30",
            platform=platform,
            currency="USD",
            balance=650.0,
            fx_rate=1.36,
            balance_sgd=884.0,
        ),
    )
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT balance, fx_rate, balance_sgd
            FROM public.cash_snapshots
            WHERE user_id = %s
              AND cash_account_id = %s
              AND snapshot_date = %s
            """,
            (PORTFOLIO_USER_ID, account_id, "2099-12-30"),
        )
        row = cur.fetchone()

    assert row is not None
    assert float(row["balance"]) == pytest.approx(650.0)
    assert float(row["fx_rate"]) == pytest.approx(1.36)
    assert float(row["balance_sgd"]) == pytest.approx(884.0)
