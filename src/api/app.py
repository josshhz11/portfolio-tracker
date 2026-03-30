"""FastAPI backend exposing portfolio-tracker operations as REST endpoints."""

from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from scripts.seed_holdings import load_seed_rows
from src.api.auth import require_request_user, require_user_scope
from src.db import (
    get_all_holdings,
    get_connection,
    get_currency_rate,
    get_daily_prices_by_date,
    get_daily_snapshot_by_date,
    get_holding_by_id,
    initialize_database,
    insert_holding,
    resolve_default_user_id,
    update_holding,
)
from src.services.fx_data import get_fx_rate_to_sgd
from src.services.market_data import get_latest_prices
from src.services.updater import run_daily_update
from src.utils.dates import is_valid_date_str, today_str


class HoldingCreate(BaseModel):
    ticker: str = Field(..., min_length=1)
    shares_owned: float = Field(..., ge=0)
    invested_amount: float = Field(..., ge=0)
    currency: str = Field(..., min_length=1)
    platform: str = Field(..., min_length=1)


class HoldingUpdate(BaseModel):
    shares_owned: float | None = Field(default=None, ge=0)
    invested_amount: float | None = Field(default=None, ge=0)
    platform: str | None = Field(default=None, min_length=1)


class HoldingResponse(BaseModel):
    id: int
    user_id: str
    ticker: str
    shares_owned: float
    invested_amount: float
    cost_per_share: float
    currency: str
    platform: str
    created_at: str | None = None
    updated_at: str | None = None


class DailyUpdateRequest(BaseModel):
    date: str | None = None


class SeedRequest(BaseModel):
    force: bool = False
    user_id: str | None = None
    seed_csv: str = "data/seed_holdings.csv"


class SeedResponse(BaseModel):
    seeded_rows: int
    affected_user_ids: list[str]


class PriceResponse(BaseModel):
    ticker: str
    price_per_share: float


class FxRateResponse(BaseModel):
    currency: str
    date: str
    rate_to_sgd: float


class PaginatedHoldingsResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[HoldingResponse]


class DailySnapshotResponse(BaseModel):
    holding_id: int
    ticker: str
    shares_owned: float
    invested_amount: float
    cost_per_share: float
    price_per_share: float
    currency: str
    platform: str
    market_value: float
    profit: float
    fx_rate: float
    market_value_sgd: float
    profit_sgd: float


class PaginatedSnapshotResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[DailySnapshotResponse]


app = FastAPI(
    title="Portfolio Tracker API",
    version="1.0.0",
    description="REST API for holdings management, daily updates, and market/FX data.",
)

_cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "API_CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _validate_date_or_400(date_str: str) -> None:
    if not is_valid_date_str(date_str):
        raise HTTPException(status_code=400, detail="Invalid date format; expected YYYY-MM-DD")


def _holding_to_response(holding) -> HoldingResponse:
    return HoldingResponse(
        id=holding.id,
        user_id=holding.user_id,
        ticker=holding.ticker,
        shares_owned=holding.shares_owned,
        invested_amount=holding.invested_amount,
        cost_per_share=holding.cost_per_share,
        currency=holding.currency,
        platform=holding.platform,
        created_at=holding.created_at,
        updated_at=holding.updated_at,
    )


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Portfolio Tracker API", "docs": "/docs"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/admin/init-db")
def init_db() -> dict[str, str]:
    conn = initialize_database()
    conn.close()
    return {"message": "Database initialised against Supabase/Postgres"}


@app.post("/admin/seed-holdings", response_model=SeedResponse)
def seed_holdings(payload: SeedRequest) -> SeedResponse:
    fallback_user_id = payload.user_id or resolve_default_user_id()
    try:
        seeds = load_seed_rows(Path(payload.seed_csv), fallback_user_id=fallback_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user_ids = sorted({row[0] for row in seeds})

    conn = initialize_database()
    try:
        if payload.force:
            with conn.cursor() as cur:
                for uid in user_ids:
                    cur.execute("DELETE FROM public.holdings WHERE user_id = %s", (uid,))
            conn.commit()
        else:
            for uid in user_ids:
                existing = get_all_holdings(conn, user_id=uid)
                if existing:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Holdings already exist for user {uid} ({len(existing)} rows). "
                            "Pass force=true to overwrite."
                        ),
                    )

        for user_id, ticker, shares, invested_amount, currency, platform in seeds:
            insert_holding(
                conn=conn,
                user_id=user_id,
                ticker=ticker,
                shares_owned=shares,
                invested_amount=invested_amount,
                currency=currency,
                platform=platform,
            )

        return SeedResponse(seeded_rows=len(seeds), affected_user_ids=user_ids)
    finally:
        conn.close()


@app.get("/users/{user_id}/holdings", response_model=PaginatedHoldingsResponse)
def list_holdings(
    user_id: str,
    _scope_user_id: str = Depends(require_user_scope),
    ticker: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    currency: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedHoldingsResponse:
    conn = get_connection()
    try:
        rows = get_all_holdings(conn, user_id=user_id)
        if ticker:
            ticker_upper = ticker.upper()
            rows = [h for h in rows if h.ticker.upper() == ticker_upper]
        if platform:
            platform_lower = platform.lower()
            rows = [h for h in rows if h.platform.lower() == platform_lower]
        if currency:
            currency_upper = currency.upper()
            rows = [h for h in rows if h.currency.upper() == currency_upper]

        total = len(rows)
        paged = rows[offset : offset + limit]
        return PaginatedHoldingsResponse(
            total=total,
            limit=limit,
            offset=offset,
            items=[_holding_to_response(h) for h in paged],
        )
    finally:
        conn.close()


@app.get("/holdings/{holding_id}", response_model=HoldingResponse)
def get_holding(
    holding_id: int,
    request_user_id: str = Depends(require_request_user),
) -> HoldingResponse:
    conn = get_connection()
    try:
        row = get_holding_by_id(conn, holding_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Holding not found")
        if row.user_id != request_user_id:
            raise HTTPException(status_code=403, detail="Forbidden for this user")
        return _holding_to_response(row)
    finally:
        conn.close()


@app.post("/users/{user_id}/holdings", response_model=HoldingResponse, status_code=201)
def create_holding(
    user_id: str,
    payload: HoldingCreate,
    _scope_user_id: str = Depends(require_user_scope),
) -> HoldingResponse:
    conn = get_connection()
    try:
        row_id = insert_holding(
            conn=conn,
            user_id=user_id,
            ticker=payload.ticker,
            shares_owned=payload.shares_owned,
            invested_amount=payload.invested_amount,
            currency=payload.currency,
            platform=payload.platform,
        )
        row = get_holding_by_id(conn, row_id)
        if row is None:
            raise HTTPException(status_code=500, detail="Inserted holding could not be reloaded")
        return _holding_to_response(row)
    finally:
        conn.close()


@app.patch("/holdings/{holding_id}", response_model=HoldingResponse)
def patch_holding(
    holding_id: int,
    payload: HoldingUpdate,
    request_user_id: str = Depends(require_request_user),
) -> HoldingResponse:
    if payload.shares_owned is None and payload.invested_amount is None and payload.platform is None:
        raise HTTPException(status_code=400, detail="At least one field must be provided")

    conn = get_connection()
    try:
        existing = get_holding_by_id(conn, holding_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Holding not found")
        if existing.user_id != request_user_id:
            raise HTTPException(status_code=403, detail="Forbidden for this user")

        update_holding(
            conn,
            holding_id=holding_id,
            shares_owned=payload.shares_owned,
            invested_amount=payload.invested_amount,
            platform=payload.platform,
        )

        updated = get_holding_by_id(conn, holding_id)
        if updated is None:
            raise HTTPException(status_code=500, detail="Updated holding could not be reloaded")
        return _holding_to_response(updated)
    finally:
        conn.close()


@app.delete("/users/{user_id}/holdings/{holding_id}")
def delete_holding(
    user_id: str,
    holding_id: int,
    _scope_user_id: str = Depends(require_user_scope),
) -> dict[str, Any]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.holdings WHERE id = %s AND user_id = %s RETURNING id",
                (holding_id, user_id),
            )
            deleted = cur.fetchone()
        conn.commit()

        if deleted is None:
            raise HTTPException(status_code=404, detail="Holding not found for this user")

        return {"deleted": True, "holding_id": holding_id, "user_id": user_id}
    finally:
        conn.close()


@app.post("/users/{user_id}/daily/update")
def update_daily(
    user_id: str,
    payload: DailyUpdateRequest,
    _scope_user_id: str = Depends(require_user_scope),
) -> dict[str, Any]:
    if payload.date:
        _validate_date_or_400(payload.date)

    summary = run_daily_update(user_id=user_id, date=payload.date)
    return asdict(summary)


@app.get("/users/{user_id}/daily/snapshot", response_model=PaginatedSnapshotResponse)
def get_daily_snapshot(
    user_id: str,
    _scope_user_id: str = Depends(require_user_scope),
    date: str | None = Query(default=None),
    ticker: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    currency: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedSnapshotResponse:
    date = date or today_str()
    _validate_date_or_400(date)

    conn = get_connection()
    try:
        rows = get_daily_snapshot_by_date(conn, date=date, user_id=user_id)
        if ticker:
            ticker_upper = ticker.upper()
            rows = [r for r in rows if r.ticker.upper() == ticker_upper]
        if platform:
            platform_lower = platform.lower()
            rows = [r for r in rows if r.platform.lower() == platform_lower]
        if currency:
            currency_upper = currency.upper()
            rows = [r for r in rows if r.currency.upper() == currency_upper]

        total = len(rows)
        paged = rows[offset : offset + limit]
        return PaginatedSnapshotResponse(
            total=total,
            limit=limit,
            offset=offset,
            items=[DailySnapshotResponse(**asdict(r)) for r in paged],
        )
    finally:
        conn.close()


@app.get("/daily/prices")
def get_daily_prices(date: str | None = Query(default=None)) -> list[dict[str, Any]]:
    date = date or today_str()
    _validate_date_or_400(date)

    conn = get_connection()
    try:
        rows = get_daily_prices_by_date(conn, date)
        return [asdict(r) for r in rows]
    finally:
        conn.close()


@app.get("/market/prices", response_model=list[PriceResponse])
def market_prices(tickers: str = Query(..., description="Comma-separated tickers, e.g. AAPL,MSFT")) -> list[PriceResponse]:
    parsed = [t.strip() for t in tickers.split(",") if t.strip()]
    if not parsed:
        raise HTTPException(status_code=400, detail="At least one ticker is required")

    prices = get_latest_prices(parsed)
    return [PriceResponse(ticker=t, price_per_share=p) for t, p in prices.items()]


@app.get("/fx/rate", response_model=FxRateResponse)
def fx_rate(
    currency: str,
    date: str | None = Query(default=None),
) -> FxRateResponse:
    date = date or today_str()
    _validate_date_or_400(date)

    conn = get_connection()
    try:
        # get_fx_rate_to_sgd handles SGD fast-path and DB cache storage
        rate = get_fx_rate_to_sgd(currency=currency, date=date, conn=conn)
        return FxRateResponse(currency=currency.upper(), date=date, rate_to_sgd=rate)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@app.get("/fx/rate/cached", response_model=FxRateResponse)
def fx_rate_cached(currency: str, date: str | None = Query(default=None)) -> FxRateResponse:
    date = date or today_str()
    _validate_date_or_400(date)

    conn = get_connection()
    try:
        rate = get_currency_rate(conn, currency.upper(), date)
        if rate is None:
            raise HTTPException(status_code=404, detail="No cached FX rate found for this date")
        return FxRateResponse(currency=currency.upper(), date=date, rate_to_sgd=rate)
    finally:
        conn.close()
