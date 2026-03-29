# portfolio-tracker

A Python-based portfolio tracker that stores holdings in Supabase Postgres, pulls latest daily stock prices and FX rates, and calculates market value and profit/loss in both native currency and SGD.

---

## Features

- Stores current portfolio positions in Supabase Postgres
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
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── daily-update.yml
├── data/
│   ├── .gitkeep
│   └── schema.sql         # Supabase/Postgres schema
├── scripts/
│   ├── check_supabase_connection.py
│   ├── init_db.py
│   ├── run_daily_update.py
│   └── seed_holdings.py
├── src/
│   ├── api/
│   │   ├── __init__.py
│   │   └── app.py         # FastAPI backend routes
│   ├── config.py
│   ├── db.py
│   ├── main.py
│   ├── models.py
│   ├── services/
│   │   ├── fx_data.py
│   │   ├── market_data.py
│   │   ├── snapshots.py   # daily portfolio snapshot capture
│   │   └── updater.py
│   └── utils/
│       ├── dates.py
│       └── logging_config.py
├── streamlit_app.py       # dashboard app
├── tests/
│   ├── test_calculations.py
│   ├── test_db.py
│   ├── test_market_fx_data.py
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

### 3. Configure environment variables

Set these before running CLI/scripts/dashboard:

```bash
export SUPABASE_DB_URL="postgresql://..."
export PORTFOLIO_USER_ID="your-supabase-auth-user-uuid"
# Windows PowerShell:
# $env:SUPABASE_DB_URL="postgresql://..."
# $env:PORTFOLIO_USER_ID="your-supabase-auth-user-uuid"
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

- Place a CSV at `data/seed_holdings.csv` (git-ignored). Headers must be: `user_id,ticker,shares_owned,invested_amount,currency,platform`.
- Example row: `your-user-uuid,AAPL,10,1502.50,USD,IBKR`
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

### Capture daily portfolio snapshots

```bash
python -m src.main snapshot-daily
# Override date:
python -m src.main snapshot-daily --date 2024-01-15
```

- This command reads holdings + that day's `daily_prices` + that day's `currencies` and writes one row per holding into `portfolio_snapshots`.
- Snapshot insert uses upsert behavior on `(holding_id, snapshot_date)` so reruns for the same day remain idempotent.

### Automated daily run (GitHub Actions)

- A scheduled workflow runs daily at 00:05 UTC: see [.github/workflows/daily-update.yml](.github/workflows/daily-update.yml).
- The workflow runs two sequential commands:
	1. `update-daily --all-users --exclude-user-id "$PORTFOLIO_USER_ID"`
	2. `snapshot-daily --all-users --exclude-user-id "$PORTFOLIO_USER_ID"`
- `PORTFOLIO_USER_ID` is used as an excluded test user id so fictional test holdings are skipped in daily market fetches.
- Required GitHub Actions secrets: `SUPABASE_DB_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `PORTFOLIO_USER_ID`.

### Show all holdings

```bash
python -m src.main show-holdings
```

### Show daily snapshot

```bash
python -m src.main show-daily             # today
python -m src.main show-daily --date 2024-01-15
```

### User scoping

All commands accept `--user-id UUID` (or use `PORTFOLIO_USER_ID` env var).

---

## Running tests

```bash
pytest tests/ -v
```

### Dashboard (Streamlit)

- Install deps (`pip install -r requirements.txt`), then run: `streamlit run streamlit_app.py`.
- Uses `SUPABASE_DB_URL` and `PORTFOLIO_USER_ID` from environment.
- Shows a portfolio value line chart (SGD) and a filterable table of the latest daily snapshot (filters are in-memory for speed).

All tests run fully offline (no network calls — market data and FX fetching is mocked).

---

## Database schema

### `holdings`
Stores current portfolio positions with user ownership. A ticker can appear across different platforms.

| Column | Type | Notes |
|---|---|---|
| id | BIGINT PK | generated identity |
| user_id | UUID | references `auth.users(id)` |
| ticker | TEXT | e.g. `AAPL`, `D05.SI` |
| shares_owned | NUMERIC | |
| invested_amount | NUMERIC | total invested amount in native currency |
| currency | TEXT | ISO code, e.g. `USD`, `SGD` |
| platform | TEXT | brokerage name |
| created_at | TIMESTAMPTZ | UTC timestamp |
| updated_at | TIMESTAMPTZ | UTC timestamp |

### `daily_prices`
Daily ticker prices; `UNIQUE(ticker, price_date)` prevents duplicates.

| Column | Type | Notes |
|---|---|---|
| id | BIGINT PK | |
| ticker | TEXT | |
| price_per_share | NUMERIC | latest close (native currency) |
| price_date | DATE | YYYY-MM-DD |
| created_at | TIMESTAMPTZ | |

### `currencies`
Daily FX rates versus SGD; `UNIQUE(currency, rate_date)` prevents duplicates.

| Column | Type | Notes |
|---|---|---|
| id | BIGINT PK | |
| currency | TEXT | ISO code |
| rate | NUMERIC | 1 unit of currency in SGD |
| rate_date | DATE | YYYY-MM-DD |
| created_at | TIMESTAMPTZ | |

---

## Configuration

Edit `src/config.py` / environment variables to:

- Set `SUPABASE_DB_URL` and `PORTFOLIO_USER_ID`
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

