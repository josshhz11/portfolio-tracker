"""Lightweight dataclasses representing the core domain objects."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Holding:
    """Represents a single portfolio position."""

    ticker: str
    shares_owned: float
    cost_per_share: float
    currency: str
    platform: str
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def total_cost(self) -> float:
        """Total amount invested in this holding (native currency)."""
        return self.shares_owned * self.cost_per_share


@dataclass
class DailyPrice:
    """Represents a daily price snapshot for one holding."""

    holding_id: int
    ticker: str
    price_per_share: float
    date: str
    market_value: float
    profit: float
    market_value_sgd: float
    profit_sgd: float
    id: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class CurrencyRate:
    """Represents a daily FX rate versus SGD."""

    currency: str
    rate: float
    date: str
    id: Optional[int] = None
    created_at: Optional[str] = None
