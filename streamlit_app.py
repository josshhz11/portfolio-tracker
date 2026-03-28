"""Streamlit dashboard for the portfolio tracker (Supabase/Postgres)."""

from __future__ import annotations

import os

import pandas as pd
import psycopg
import streamlit as st

DB_URL = os.environ.get("SUPABASE_DB_URL", "")
DEFAULT_USER_ID = os.environ.get("PORTFOLIO_USER_ID", "")


def _conn() -> psycopg.Connection:
    if not DB_URL:
        raise ValueError("SUPABASE_DB_URL is not set")
    return psycopg.connect(DB_URL)


def _read_df(query: str, params: tuple | None = None) -> pd.DataFrame:
    with _conn() as conn:
        return pd.read_sql_query(query, conn, params=params)


@st.cache_data(show_spinner=False)
def load_data(user_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    holdings = _read_df(
        """
        SELECT id, ticker, shares_owned, invested_amount, currency, platform
        FROM public.holdings
        WHERE user_id = %s
        ORDER BY id
        """,
        params=(user_id,),
    )

    history = _read_df(
        """
        SELECT
            dp.price_date,
            SUM(h.shares_owned * dp.price_per_share * COALESCE(c.rate, 1)) AS portfolio_sgd
        FROM public.holdings h
        JOIN public.daily_prices dp
          ON dp.ticker = h.ticker
        LEFT JOIN public.currencies c
          ON c.currency = h.currency
         AND c.rate_date = dp.price_date
        WHERE h.user_id = %s
        GROUP BY dp.price_date
        ORDER BY dp.price_date
        """,
        params=(user_id,),
    )
    return holdings, history


@st.cache_data(show_spinner=False)
def load_latest_snapshot(user_id: str) -> tuple[str | None, pd.DataFrame]:
    latest_date_df = _read_df(
        """
        SELECT MAX(dp.price_date)::text AS latest_date
        FROM public.daily_prices dp
        JOIN public.holdings h ON h.ticker = dp.ticker
        WHERE h.user_id = %s
        """,
        params=(user_id,),
    )
    latest_date = latest_date_df.iloc[0]["latest_date"] if not latest_date_df.empty else None
    if not latest_date:
        return None, pd.DataFrame()

    latest = _read_df(
        """
        SELECT
            h.id AS holding_id,
            h.ticker,
            h.platform,
            h.currency,
            h.shares_owned,
            h.invested_amount,
            dp.price_per_share,
            COALESCE(c.rate, 1) AS fx_rate,
            (h.shares_owned * dp.price_per_share) AS market_value,
            ((h.shares_owned * dp.price_per_share) - h.invested_amount) AS profit,
            (h.shares_owned * dp.price_per_share * COALESCE(c.rate, 1)) AS market_value_sgd,
            (((h.shares_owned * dp.price_per_share) - h.invested_amount) * COALESCE(c.rate, 1)) AS profit_sgd
        FROM public.holdings h
        JOIN public.daily_prices dp
          ON dp.ticker = h.ticker
         AND dp.price_date = %s
        LEFT JOIN public.currencies c
          ON c.currency = h.currency
         AND c.rate_date = dp.price_date
        WHERE h.user_id = %s
        ORDER BY h.id
        """,
        params=(latest_date, user_id),
    )
    return latest_date, latest


def render_line_chart(history: pd.DataFrame) -> None:
    st.subheader("Portfolio value over time (SGD)")
    if history.empty:
        st.info("No daily snapshots yet. Run the daily updater to populate data.")
        return
    st.line_chart(history, x="price_date", y="portfolio_sgd")


def render_snapshot_table(latest_date: str | None, latest: pd.DataFrame) -> None:
    st.subheader("Latest daily snapshot")
    if latest_date is None or latest.empty:
        st.info("No daily data available yet.")
        return

    st.caption(f"As of {latest_date}")

    tickers = sorted(latest["ticker"].unique())
    currencies = sorted(latest["currency"].unique())
    platforms = sorted(latest["platform"].unique())

    c1, c2, c3 = st.columns(3)
    selected_tickers = c1.multiselect("Tickers", tickers, default=tickers)
    selected_currencies = c2.multiselect("Currencies", currencies, default=currencies)
    selected_platforms = c3.multiselect("Platforms", platforms, default=platforms)

    filtered = latest[
        latest["ticker"].isin(selected_tickers)
        & latest["currency"].isin(selected_currencies)
        & latest["platform"].isin(selected_platforms)
    ]

    if filtered.empty:
        st.warning("No rows match the selected filters.")
        return

    filtered = filtered.copy()
    filtered["cost_per_share"] = filtered.apply(
        lambda row: (row["invested_amount"] / row["shares_owned"]) if row["shares_owned"] > 0 else 0,
        axis=1,
    )

    display_cols = [
        "ticker",
        "platform",
        "currency",
        "shares_owned",
        "invested_amount",
        "cost_per_share",
        "price_per_share",
        "market_value",
        "profit",
        "market_value_sgd",
        "profit_sgd",
    ]
    st.dataframe(
        filtered[display_cols].rename(
            columns={
                "shares_owned": "shares",
                "invested_amount": "invested",
                "cost_per_share": "cost/share",
                "price_per_share": "price/share",
                "market_value": "mkt value",
                "profit": "p&l",
                "market_value_sgd": "mkt value (SGD)",
                "profit_sgd": "p&l (SGD)",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


def main() -> None:
    st.title("Portfolio Tracker Dashboard")
    st.caption("Powered by Supabase Postgres.")

    user_id = st.sidebar.text_input("User ID", value=DEFAULT_USER_ID)
    if not user_id:
        st.warning("Set PORTFOLIO_USER_ID or enter a user id in the sidebar.")
        return

    st.sidebar.markdown("**DB URL configured**")
    st.sidebar.write(bool(DB_URL))

    holdings, history = load_data(user_id)
    latest_date, latest = load_latest_snapshot(user_id)

    if holdings.empty:
        st.info("No holdings found for this user id.")
        return

    render_line_chart(history)
    st.divider()
    render_snapshot_table(latest_date, latest)
    st.divider()
    st.caption("Filters are applied in-memory after loading latest rows.")


if __name__ == "__main__":
    main()
