"""Central configuration for the portfolio tracker."""

from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
# Root of the repository (two levels up from this file: src/ -> repo root)
BASE_DIR: Path = Path(__file__).resolve().parent.parent

DATA_DIR: Path = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH: Path = DATA_DIR / "portfolio.db"

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
