# portfolio-tracker

A Python-based portfolio tracker that stores holdings in SQLite, pulls latest daily stock prices and FX rates, and calculates market value and profit/loss in both native currency and SGD.

---

## Features

- Stores current portfolio positions in a local SQLite database
- Fetches latest daily close prices via **yfinance** (US & SGX tickers)
- Fetches daily FX rates (USD → SGD, extensible to more currencies)
- Calculates market value, unrealised P&L in native currency and SGD
- Inserts immutable daily snapshots (no history overwritten)
- Clean CLI interface for all operations
- Structured for future extensions: Streamlit dashboard, Telegram/email alerts, GitHub Actions scheduling

---

## Project structure

```
portfolio-tracker/
├── data/
│   └── .gitkeep           # database lives here (git-ignored)
├── scripts/
│   ├── init_db.py         # bootstrap the database
│   ├── seed_holdings.py   # seed sample positions
│   └── run_daily_update.py# fetch prices & store daily snapshot
├── src/
│   ├── config.py          # central config (paths, constants)
│   ├── db.py              # all SQLite operations
│   ├── models.py          # Holding, DailyPrice, CurrencyRate dataclasses
│   ├── main.py            # argparse CLI entry-point
│   ├── services/
│   │   ├── fx_data.py     # FX rate fetching & caching
│   │   ├── market_data.py # stock price fetching (yfinance)
│   │   └── updater.py     # daily update orchestrator
│   └── utils/
│       ├── dates.py       # date helpers
│       └── logging_config.py
├── tests/
│   ├── test_calculations.py
│   ├── test_db.py
│   └── test_updater.py
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Clone & create a virtual environment

```bash
git clone https://github.com/josshhz11/portfolio-tracker.git
cd portfolio-tracker
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Usage

All commands are available via the CLI (`python -m src.main`) or via the standalone scripts in `scripts/`.

### Initialise the database

```bash
python -m src.main init-db
# or
python scripts/init_db.py
```

### Seed sample holdings

```bash
python -m src.main seed-holdings
# Use --force to truncate and re-seed if holdings already exist
python -m src.main seed-holdings --force
# or
python scripts/seed_holdings.py [--force]
```

Sample holdings seeded (fictional data by default):

| Ticker | Shares | Cost/share | Currency | Platform |
|--------|-------:|----------:|----------|----------|
| NVDA   | 60     | 92.455    | USD      | Moomoo   |
| BBAI   | 2000   | 2.45      | USD      | Moomoo   |
| SNDK   | 100    | 499.55    | USD      | Moomoo   |
| GOOG   | 50     | 49.99     | USD      | Moomoo   |
| CRWV   | 11     | 75.056    | USD      | Moomoo   |
| D05.SI | 600    | 45.82     | SGD      | Tiger    |
| D05.SI | 200    | 54.00     | SGD      | IBKR     |

Use a private CSV for real seeds (preferred)

- Place a CSV at `data/seed_holdings.csv` (git-ignored). Headers must be: `ticker,shares_owned,cost_per_share,currency,platform`.
- Example row: `AAPL,10,150.25,USD,IBKR`
- Run with a custom path if needed: `python scripts/seed_holdings.py --seed-csv /path/to/my_seeds.csv`.
- If the CSV is missing, the script falls back to the fictional table above.

### Run the daily update

```bash
python -m src.main update-daily
# Override date (useful for backfills or testing):
python -m src.main update-daily --date 2024-01-15
# or
python scripts/run_daily_update.py [--date YYYY-MM-DD]
```

### Automated daily run (GitHub Actions)

- A scheduled workflow runs daily at 00:05 UTC: see [.github/workflows/daily-update.yml](.github/workflows/daily-update.yml).
- It initialises a fresh DB, seeds the demo holdings, runs the daily updater, and uploads `data/portfolio.db` as an artifact (7-day retention). Update the workflow if you want to persist elsewhere.

### Show all holdings

```bash
python -m src.main show-holdings
```

### Show daily snapshot

```bash
python -m src.main show-daily             # today
python -m src.main show-daily --date 2024-01-15
```

### Custom database path

All commands accept `--db PATH`:

```bash
python -m src.main --db /path/to/my.db show-holdings
```

---

## Running tests

```bash
pytest tests/ -v
```

### Dashboard (Streamlit)

- Install deps (`pip install -r requirements.txt`), then run: `streamlit run streamlit_app.py`.
- Uses `data/portfolio.db` by default; override with `PORTFOLIO_DB_PATH=/path/to/db streamlit run streamlit_app.py`.
- Shows a portfolio value line chart (SGD) and a filterable table of the latest daily snapshot (filters are in-memory for speed).

All tests run fully offline (no network calls — market data and FX fetching is mocked).

---

## Database schema

### `holdings`
Stores current portfolio positions. A ticker can appear multiple times across different platforms.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | auto-increment |
| ticker | TEXT | e.g. `AAPL`, `D05.SI` |
| shares_owned | REAL | |
| cost_per_share | REAL | average cost basis (native currency) |
| currency | TEXT | ISO code, e.g. `USD`, `SGD` |
| platform | TEXT | brokerage name |
| created_at | TEXT | UTC timestamp |
| updated_at | TEXT | UTC timestamp |

### `daily_prices`
Immutable daily snapshots; `UNIQUE(holding_id, date)` prevents duplicates.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| holding_id | INTEGER FK | → holdings.id |
| ticker | TEXT | |
| price_per_share | REAL | latest close (native currency) |
| date | TEXT | YYYY-MM-DD |
| market_value | REAL | shares × price |
| profit | REAL | unrealised P&L (native currency) |
| market_value_sgd | REAL | market_value × fx_rate |
| profit_sgd | REAL | profit × fx_rate |
| created_at | TEXT | |

### `currencies`
Daily FX rates versus SGD; `UNIQUE(currency, date)` prevents duplicates.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| currency | TEXT | ISO code |
| rate | REAL | 1 unit of currency in SGD |
| date | TEXT | YYYY-MM-DD |
| created_at | TEXT | |

---

## Configuration

Edit `src/config.py` to:

- Change the database path (`DB_PATH`)
- Add new FX currency pairs (`FX_TICKER_MAP`)
- Adjust price lookback window (`PRICE_LOOKBACK_DAYS`)

---

## Future roadmap

- [ ] Streamlit / React dashboard
- [ ] Telegram / email daily summary
- [ ] GitHub Actions scheduled workflow (daily cron)
- [ ] Additional FX currencies (GBP, HKD, …)
- [ ] Transaction history table (buy/sell tracking)
- [ ] Realised P&L calculation
- [ ] Benchmark comparison (e.g. vs STI, S&P 500)
- [ ] Platform-level and ticker-level analytics

