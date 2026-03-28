"""Lightweight dataclasses representing the core domain objects."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Holding:
    """Represents a single portfolio position."""

    user_id: str
    ticker: str
    shares_owned: float
    invested_amount: float
    currency: str
    platform: str
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def total_cost(self) -> float:
        """Total amount invested in this holding (native currency)."""
        return self.invested_amount

    @property
    def cost_per_share(self) -> float:
        """Average cost basis per share in native currency."""
        if self.shares_owned <= 0:
            return 0.0
        return self.invested_amount / self.shares_owned


@dataclass
class DailyPrice:
    """Represents a daily market price row per ticker and date."""

    ticker: str
    price_per_share: float
    date: str
    id: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class DailySnapshot:
    """Computed per-holding snapshot for a given date."""

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


@dataclass
class CurrencyRate:
    """Represents a daily FX rate versus SGD."""

    currency: str
    rate: float
    date: str
    id: Optional[int] = None
    created_at: Optional[str] = None
