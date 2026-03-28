"""Central configuration for the portfolio tracker."""

import os
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
# Root of the repository (two levels up from this file: src/ -> repo root)
BASE_DIR: Path = Path(__file__).resolve().parent.parent

DATA_DIR: Path = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH: Path = DATA_DIR / "portfolio.db"

# Primary DB connection for Supabase/Postgres deployments.
# Example: postgresql://postgres:<password>@<host>:5432/postgres
SUPABASE_DB_URL: str = os.getenv("SUPABASE_DB_URL", "")

# Optional default user id for CLI seed/update flows in a single-user setup.
DEFAULT_USER_ID: str = os.getenv("PORTFOLIO_USER_ID", "")

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = "INFO"

# ── Market data ───────────────────────────────────────────────────────────────
# Number of trading days to look back when the latest close is unavailable
PRICE_LOOKBACK_DAYS: int = 5

# ── FX ────────────────────────────────────────────────────────────────────────
# Base currency for all SGD conversions
BASE_CURRENCY: str = "SGD"

# Mapping from currency code to the yfinance ticker used for FX lookup.
# Add new currencies here as the portfolio grows.
FX_TICKER_MAP: dict[str, str] = {
    "USD": "USDSGD=X",
    # "GBP": "GBPSGD=X",
    # "HKD": "HKDSGD=X",
}
