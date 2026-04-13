"use client";

import { useEffect, useMemo, useState } from "react";
import { format, parseISO, startOfYear, subMonths, subYears } from "date-fns";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CheckCircle2, LogOut, Plus, RefreshCw, Upload, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { getSupabaseClient } from "@/lib/supabase";


type HoldingRow = {
  id: number;
  user_id: string;
  ticker: string;
  shares_owned: number;
  invested_amount: number;
  currency: string;
  platform: string;
  updated_at: string;
};

type DailyPriceRow = {
  ticker: string;
  price_per_share: number;
  price_date: string;
};

type SnapshotRow = {
  holding_id: number;
  snapshot_date: string;
  market_value_sgd: number;
  unrealized_profit_sgd: number;
};

type TradeRow = {
  id: number;
  ticker: string;
  trade_type: "BUY" | "SELL";
  shares: number;
  cash_amount: number;
  currency: string;
  platform: string;
  traded_at: string;
};

type RangeKey = "3M" | "6M" | "YTD" | "1Y" | "ALL";
type MetricKey = "value" | "pct";

type TradeFormState = {
  ticker: string;
  tradeType: "BUY" | "SELL";
  currency: string;
  price: string;
  shares: string;
  platform: string;
};

type HoldingFormState = {
  ticker: string;
  sharesOwned: string;
  investedAmount: string;
  currency: string;
  platform: string;
};

type CsvHoldingInput = {
  ticker: string;
  shares_owned: number;
  invested_amount: number;
  currency: string;
  platform: string;
};

const chartPalette = [
  "#e76f51",
  "#2a9d8f",
  "#264653",
  "#f4a261",
  "#457b9d",
  "#6d597a",
  "#8ab17d",
  "#e63946",
];

function getRangeStart(range: RangeKey): Date | null {
  const now = new Date();
  if (range === "3M") return subMonths(now, 3);
  if (range === "6M") return subMonths(now, 6);
  if (range === "YTD") return startOfYear(now);
  if (range === "1Y") return subYears(now, 1);
  return null;
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat("en-SG", {
    style: "currency",
    currency: "SGD",
    maximumFractionDigits: 2,
  }).format(value || 0);
}

function formatPct(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export function DashboardPage() {
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [userId, setUserId] = useState<string>("");
  const [holdings, setHoldings] = useState<HoldingRow[]>([]);
  const [latestPrices, setLatestPrices] = useState<Record<string, DailyPriceRow>>({});
  const [snapshots, setSnapshots] = useState<SnapshotRow[]>([]);
  const [trades, setTrades] = useState<TradeRow[]>([]);

  const [range, setRange] = useState<RangeKey>("6M");
  const [metric, setMetric] = useState<MetricKey>("value");
  const [selectedTickers, setSelectedTickers] = useState<string[]>([]);
  const [tradeModalOpen, setTradeModalOpen] = useState(false);
  const [tradeSubmitting, setTradeSubmitting] = useState(false);
  const [tradeError, setTradeError] = useState<string | null>(null);
  const [showTradeSuccess, setShowTradeSuccess] = useState(false);
  const [holdingModalOpen, setHoldingModalOpen] = useState(false);
  const [holdingSubmitting, setHoldingSubmitting] = useState(false);
  const [holdingError, setHoldingError] = useState<string | null>(null);
  const [showHoldingSuccess, setShowHoldingSuccess] = useState(false);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvUploading, setCsvUploading] = useState(false);
  const [csvError, setCsvError] = useState<string | null>(null);

  const [tradeForm, setTradeForm] = useState<TradeFormState>({
    ticker: "",
    tradeType: "BUY",
    currency: "USD",
    price: "",
    shares: "",
    platform: "",
  });

  const [holdingForm, setHoldingForm] = useState<HoldingFormState>({
    ticker: "",
    sharesOwned: "",
    investedAmount: "",
    currency: "USD",
    platform: "",
  });

  const liveTradeAmount = useMemo(() => {
    const price = Number(tradeForm.price || 0);
    const shares = Number(tradeForm.shares || 0);
    return Number.isFinite(price * shares) ? price * shares : 0;
  }, [tradeForm.price, tradeForm.shares]);

  const tickerByHoldingId = useMemo(() => {
    const map = new Map<number, string>();
    for (const h of holdings) map.set(h.id, h.ticker);
    return map;
  }, [holdings]);

  const allTickers = useMemo(() => {
    return Array.from(new Set(holdings.map((h) => h.ticker))).sort();
  }, [holdings]);

  useEffect(() => {
    if (allTickers.length > 0 && selectedTickers.length === 0) {
      setSelectedTickers(allTickers);
    }
  }, [allTickers, selectedTickers.length]);

  const filteredSnapshots = useMemo(() => {
    const start = getRangeStart(range);
    if (!start) return snapshots;
    return snapshots.filter((s) => parseISO(s.snapshot_date) >= start);
  }, [snapshots, range]);

  const portfolioSeries = useMemo(() => {
    const byDate = new Map<string, number>();
    for (const row of filteredSnapshots) {
      byDate.set(
        row.snapshot_date,
        (byDate.get(row.snapshot_date) || 0) + Number(row.market_value_sgd),
      );
    }

    const points = Array.from(byDate.entries())
      .map(([date, value]) => ({ date, value }))
      .sort((a, b) => (a.date < b.date ? -1 : 1));

    if (metric === "value") {
      return points;
    }

    const baseline = points[0]?.value || 0;
    return points.map((p) => ({
      ...p,
      value: baseline > 0 ? ((p.value - baseline) / baseline) * 100 : 0,
    }));
  }, [filteredSnapshots, metric]);

  const holdingsSeries = useMemo(() => {
    const byDateTicker = new Map<string, Record<string, number>>();

    for (const row of filteredSnapshots) {
      const ticker = tickerByHoldingId.get(row.holding_id);
      if (!ticker || !selectedTickers.includes(ticker)) continue;

      const entry = byDateTicker.get(row.snapshot_date) || {};
      entry[ticker] = (entry[ticker] || 0) + Number(row.market_value_sgd);
      byDateTicker.set(row.snapshot_date, entry);
    }

    const points = Array.from(byDateTicker.entries())
      .map(([date, values]) => ({ date, ...values }))
      .sort((a, b) => ((a.date as string) < (b.date as string) ? -1 : 1));

    if (metric === "value") return points;

    const baselines: Record<string, number> = {};
    for (const ticker of selectedTickers) {
      for (const point of points) {
        const v = Number((point as Record<string, unknown>)[ticker] || 0);
        if (v > 0) {
          baselines[ticker] = v;
          break;
        }
      }
    }

    return points.map((point) => {
      const clone: Record<string, unknown> = { ...point };
      for (const ticker of selectedTickers) {
        const base = baselines[ticker] || 0;
        const cur = Number(clone[ticker] || 0);
        clone[ticker] = base > 0 ? ((cur - base) / base) * 100 : 0;
      }
      return clone;
    });
  }, [filteredSnapshots, selectedTickers, tickerByHoldingId, metric]);

  const holdingsTableRows = useMemo(() => {
    const latestSnapshotByHolding = new Map<number, SnapshotRow>();
    for (const row of snapshots) {
      const prev = latestSnapshotByHolding.get(row.holding_id);
      if (!prev || prev.snapshot_date < row.snapshot_date) {
        latestSnapshotByHolding.set(row.holding_id, row);
      }
    }

    return holdings.map((h) => {
      const latestPrice = latestPrices[h.ticker];
      const latestSnapshot = latestSnapshotByHolding.get(h.id);
      const costPerShare = h.shares_owned > 0 ? Number(h.invested_amount) / Number(h.shares_owned) : 0;
      return {
        ...h,
        costPerShare,
        latestPrice: latestPrice?.price_per_share ?? null,
        latestPriceDate: latestPrice?.price_date ?? null,
        currentValueSgd: latestSnapshot?.market_value_sgd ?? null,
      };
    });
  }, [holdings, latestPrices, snapshots]);

  async function loadAllData() {
    setError(null);
    const supabase = getSupabaseClient();

    const { data: authData, error: authError } = await supabase.auth.getUser();
    if (authError || !authData.user) {
      router.push("/login");
      return;
    }

    const uid = authData.user.id;
    setUserId(uid);

    const holdingsQuery = supabase
      .from("holdings")
      .select("id,user_id,ticker,shares_owned,invested_amount,currency,platform,updated_at")
      .eq("user_id", uid)
      .order("ticker", { ascending: true });

    const snapshotsQuery = supabase
      .from("portfolio_snapshots")
      .select("holding_id,snapshot_date,market_value_sgd,unrealized_profit_sgd")
      .eq("user_id", uid)
      .order("snapshot_date", { ascending: true });

    const tradesQuery = supabase
      .from("trades")
      .select("id,ticker,trade_type,shares,cash_amount,currency,platform,traded_at")
      .eq("user_id", uid)
      .order("traded_at", { ascending: false })
      .limit(200);

    const [holdingsRes, snapshotsRes, tradesRes] = await Promise.all([
      holdingsQuery,
      snapshotsQuery,
      tradesQuery,
    ]);

    if (holdingsRes.error) throw holdingsRes.error;
    if (snapshotsRes.error) throw snapshotsRes.error;
    if (tradesRes.error) throw tradesRes.error;

    const loadedHoldings = (holdingsRes.data || []) as HoldingRow[];
    setHoldings(loadedHoldings);
    setSnapshots((snapshotsRes.data || []) as SnapshotRow[]);
    setTrades((tradesRes.data || []) as TradeRow[]);

    const tickers = Array.from(new Set(loadedHoldings.map((h) => h.ticker)));
    if (tickers.length === 0) {
      setLatestPrices({});
      return;
    }

    const pricesRes = await supabase
      .from("daily_prices")
      .select("ticker,price_per_share,price_date")
      .in("ticker", tickers)
      .order("price_date", { ascending: false });

    if (pricesRes.error) throw pricesRes.error;

    const latestMap: Record<string, DailyPriceRow> = {};
    for (const p of (pricesRes.data || []) as DailyPriceRow[]) {
      if (!latestMap[p.ticker]) {
        latestMap[p.ticker] = p;
      }
    }
    setLatestPrices(latestMap);
  }

  async function refreshData() {
    setRefreshing(true);
    try {
      await loadAllData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data");
    } finally {
      setRefreshing(false);
    }
  }

  async function signOut() {
    const supabase = getSupabaseClient();
    await supabase.auth.signOut();
    router.push("/login");
  }

  function parseHoldingsCsv(csvText: string): CsvHoldingInput[] {
    const lines = csvText
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line.length > 0);

    if (lines.length < 2) {
      throw new Error("CSV must include a header row and at least one data row.");
    }

    const header = lines[0]
      .split(",")
      .map((h) => h.trim().toLowerCase());
    const required = ["ticker", "shares_owned", "invested_amount", "currency", "platform"];
    const missing = required.filter((key) => !header.includes(key));
    if (missing.length > 0) {
      throw new Error(`Missing required CSV header(s): ${missing.join(", ")}`);
    }

    const idx = (name: string) => header.indexOf(name);
    const parsed: CsvHoldingInput[] = [];

    for (let i = 1; i < lines.length; i++) {
      const cols = lines[i].split(",").map((c) => c.trim());
      const ticker = cols[idx("ticker")]?.toUpperCase();
      const sharesOwned = Number(cols[idx("shares_owned")]);
      const investedAmount = Number(cols[idx("invested_amount")]);
      const currency = cols[idx("currency")]?.toUpperCase();
      const platform = cols[idx("platform")];

      if (!ticker || !currency || !platform || !Number.isFinite(sharesOwned) || !Number.isFinite(investedAmount)) {
        throw new Error(`Invalid data at CSV line ${i + 1}.`);
      }
      if (sharesOwned < 0 || investedAmount < 0) {
        throw new Error(`Negative values are not allowed at CSV line ${i + 1}.`);
      }

      parsed.push({
        ticker,
        shares_owned: sharesOwned,
        invested_amount: investedAmount,
        currency,
        platform,
      });
    }

    return parsed;
  }

  async function handleSeedUpload() {
    if (holdings.length > 0) {
      setCsvError("CSV upload is only enabled for first-time users with zero holdings.");
      return;
    }
    if (!csvFile) {
      setCsvError("Please choose a CSV file first.");
      return;
    }

    setCsvUploading(true);
    setCsvError(null);
    try {
      const text = await csvFile.text();
      const parsedRows = parseHoldingsCsv(text);
      if (parsedRows.length === 0) {
        throw new Error("No valid rows found in CSV file.");
      }

      const supabase = getSupabaseClient();
      const payload = parsedRows.map((row) => ({
        ...row,
        user_id: userId,
      }));

      const { error: insertError } = await (supabase.from("holdings") as any).insert(payload);
      if (insertError) throw insertError;

      setCsvFile(null);
      await refreshData();
    } catch (err) {
      setCsvError(err instanceof Error ? err.message : "Failed to upload holdings CSV.");
    } finally {
      setCsvUploading(false);
    }
  }

  async function handleTradeSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setTradeError(null);

    const ticker = tradeForm.ticker.trim().toUpperCase();
    const platform = tradeForm.platform.trim();
    const currency = tradeForm.currency.trim().toUpperCase();
    const price = Number(tradeForm.price);
    const shares = Number(tradeForm.shares);
    const cashAmount = price * shares;

    if (!ticker || !platform || !currency) {
      setTradeError("Ticker, currency, and platform are required.");
      return;
    }
    if (!Number.isFinite(price) || !Number.isFinite(shares) || price <= 0 || shares <= 0) {
      setTradeError("Price and shares must be positive numbers.");
      return;
    }

    setTradeSubmitting(true);
    try {
      const supabase = getSupabaseClient();
      const { error: insertError } = await (supabase.from("trades") as any).insert({
        user_id: userId,
        ticker,
        trade_type: tradeForm.tradeType,
        currency,
        cash_amount: cashAmount,
        shares,
        platform,
        traded_at: new Date().toISOString(),
      });

      if (insertError) throw insertError;

      setTradeModalOpen(false);
      setTradeForm({
        ticker: "",
        tradeType: "BUY",
        currency: "USD",
        price: "",
        shares: "",
        platform: "",
      });
      setShowTradeSuccess(true);
      window.setTimeout(() => setShowTradeSuccess(false), 2200);
      await refreshData();
    } catch (err) {
      setTradeError(err instanceof Error ? err.message : "Failed to submit trade.");
    } finally {
      setTradeSubmitting(false);
    }
  }

  async function handleHoldingSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setHoldingError(null);

    const ticker = holdingForm.ticker.trim().toUpperCase();
    const platform = holdingForm.platform.trim();
    const currency = holdingForm.currency.trim().toUpperCase();
    const sharesOwned = Number(holdingForm.sharesOwned);
    const investedAmount = Number(holdingForm.investedAmount);

    if (!ticker || !platform || !currency) {
      setHoldingError("Ticker, currency, and platform are required.");
      return;
    }
    if (!Number.isFinite(sharesOwned) || sharesOwned <= 0) {
      setHoldingError("Shares owned must be a positive number.");
      return;
    }
    if (!Number.isFinite(investedAmount) || investedAmount < 0) {
      setHoldingError("Invested amount must be zero or greater.");
      return;
    }

    setHoldingSubmitting(true);
    try {
      const supabase = getSupabaseClient();
      const { error: insertError } = await (supabase.from("holdings") as any).insert({
        user_id: userId,
        ticker,
        shares_owned: sharesOwned,
        invested_amount: investedAmount,
        currency,
        platform,
      });

      if (insertError) throw insertError;

      setHoldingModalOpen(false);
      setHoldingForm({
        ticker: "",
        sharesOwned: "",
        investedAmount: "",
        currency: "USD",
        platform: "",
      });
      setShowHoldingSuccess(true);
      window.setTimeout(() => setShowHoldingSuccess(false), 2200);
      await refreshData();
    } catch (err) {
      setHoldingError(err instanceof Error ? err.message : "Failed to add holding.");
    } finally {
      setHoldingSubmitting(false);
    }
  }

  useEffect(() => {
    const run = async () => {
      try {
        await loadAllData();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load dashboard data");
      } finally {
        setLoading(false);
      }
    };
    run();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-100 text-slate-800 flex items-center justify-center">
        <div className="rounded-2xl bg-white shadow-xl px-6 py-5">Loading dashboard...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_20%_0%,#e0f2fe,transparent_35%),radial-gradient(circle_at_80%_0%,#fde68a,transparent_30%),#f8fafc] text-slate-900">
      <div className="max-w-[1500px] mx-auto px-4 py-6 lg:px-8">
        <header className="mb-6 rounded-3xl border border-slate-200 bg-white/80 backdrop-blur px-6 py-4 shadow-sm flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Portfolio Command Center</h1>
            <p className="text-sm text-slate-600">Signed in user: {userId}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={refreshData}
              className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 transition"
            >
              <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
              Refresh
            </button>
            <button
              onClick={signOut}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-100 transition"
            >
              <LogOut size={16} />
              Sign out
            </button>
          </div>
        </header>

        {error ? (
          <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
        ) : null}

        <section className="grid grid-cols-1 xl:grid-cols-12 gap-6">
          <div className="xl:col-span-7 space-y-6">
            <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                <h2 className="text-lg font-semibold">Overall Portfolio Trend</h2>
                <div className="flex items-center gap-2 flex-wrap">
                  {(["3M", "6M", "YTD", "1Y", "ALL"] as RangeKey[]).map((r) => (
                    <button
                      key={r}
                      onClick={() => setRange(r)}
                      className={`rounded-lg px-3 py-1 text-xs font-medium transition ${
                        range === r ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                      }`}
                    >
                      {r}
                    </button>
                  ))}
                  <button
                    onClick={() => setMetric((m) => (m === "value" ? "pct" : "value"))}
                    className="rounded-lg bg-indigo-600 text-white text-xs px-3 py-1 font-medium hover:bg-indigo-500"
                  >
                    {metric === "value" ? "Show %" : "Show SGD"}
                  </button>
                </div>
              </div>
              <div className="h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={portfolioSeries}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="date" tickFormatter={(d) => format(parseISO(d), "dd MMM")} />
                    <YAxis
                      tickFormatter={(v) => (metric === "value" ? `${Math.round(v / 1000)}k` : `${v.toFixed(0)}%`)}
                    />
                    <Tooltip
                      formatter={(value: unknown) =>
                        metric === "value"
                          ? formatMoney(Number(value || 0))
                          : formatPct(Number(value || 0))
                      }
                      labelFormatter={(label) => format(parseISO(label), "dd MMM yyyy")}
                    />
                    <Line type="monotone" dataKey="value" stroke="#0f172a" strokeWidth={3} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-4">
                <h2 className="text-lg font-semibold mb-3">Individual Holdings Trend</h2>
                <div className="flex flex-wrap gap-2">
                  {allTickers.map((ticker) => {
                    const selected = selectedTickers.includes(ticker);
                    return (
                      <button
                        key={ticker}
                        onClick={() => {
                          setSelectedTickers((prev) =>
                            prev.includes(ticker)
                              ? prev.filter((t) => t !== ticker)
                              : [...prev, ticker],
                          );
                        }}
                        className={`rounded-full px-3 py-1 text-xs font-medium border transition ${
                          selected
                            ? "bg-slate-900 text-white border-slate-900"
                            : "bg-white text-slate-600 border-slate-300 hover:bg-slate-100"
                        }`}
                      >
                        {ticker}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="h-[340px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={holdingsSeries}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="date" tickFormatter={(d) => format(parseISO(d), "dd MMM")} />
                    <YAxis
                      tickFormatter={(v) => (metric === "value" ? `${Math.round(v / 1000)}k` : `${v.toFixed(0)}%`)}
                    />
                    <Tooltip
                      formatter={(value: unknown) =>
                        metric === "value"
                          ? formatMoney(Number(value || 0))
                          : formatPct(Number(value || 0))
                      }
                      labelFormatter={(label) => format(parseISO(label), "dd MMM yyyy")}
                    />
                    <Legend />
                    {selectedTickers.map((ticker, index) => (
                      <Line
                        key={ticker}
                        type="monotone"
                        dataKey={ticker}
                        stroke={chartPalette[index % chartPalette.length]}
                        strokeWidth={2.5}
                        dot={false}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="xl:col-span-5 space-y-6">
            <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h2 className="text-lg font-semibold">Current Holdings</h2>
                <button
                  onClick={() => {
                    setHoldingError(null);
                    setHoldingModalOpen(true);
                  }}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700"
                >
                  <Plus size={14} />
                  Add Holding
                </button>
              </div>
              {holdings.length === 0 ? (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 mb-4">
                  <p className="text-sm text-amber-900 font-medium mb-2">First-time setup: upload your holdings CSV</p>
                  <p className="text-xs text-amber-700 mb-3">
                    Required headers: ticker,shares_owned,invested_amount,currency,platform
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      type="file"
                      accept=".csv,text/csv"
                      onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
                      className="block w-full text-xs text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-900 file:px-3 file:py-2 file:text-white"
                    />
                    <button
                      onClick={handleSeedUpload}
                      disabled={csvUploading || !csvFile}
                      className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-xs font-medium text-white disabled:opacity-60"
                    >
                      <Upload size={14} />
                      {csvUploading ? "Uploading..." : "Seed Holdings"}
                    </button>
                  </div>
                  {csvError ? <p className="text-xs text-rose-600 mt-2">{csvError}</p> : null}
                </div>
              ) : null}
              <div className="overflow-auto max-h-[360px]">
                <table className="w-full text-sm">
                  <thead className="text-left text-slate-500">
                    <tr>
                      <th className="py-2">Ticker</th>
                      <th className="py-2">Shares</th>
                      <th className="py-2">Cost/share</th>
                      <th className="py-2">Currency</th>
                      <th className="py-2">Price</th>
                      <th className="py-2">Last Price</th>
                    </tr>
                  </thead>
                  <tbody>
                    {holdingsTableRows.map((row) => (
                      <tr key={row.id} className="border-t border-slate-100">
                        <td className="py-2 font-medium">{row.ticker}</td>
                        <td className="py-2">{Number(row.shares_owned).toFixed(3)}</td>
                        <td className="py-2">{row.costPerShare.toFixed(2)}</td>
                        <td className="py-2">{row.currency}</td>
                        <td className="py-2">
                          {row.latestPrice != null ? Number(row.latestPrice).toFixed(2) : "-"}
                        </td>
                        <td className="py-2 text-xs text-slate-500">{row.latestPriceDate || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h2 className="text-lg font-semibold">Trades</h2>
                <button
                  onClick={() => {
                    setTradeError(null);
                    setTradeModalOpen(true);
                  }}
                  className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700"
                >
                  Add Trade
                </button>
              </div>
              {trades.length === 0 ? (
                <p className="text-sm text-slate-500">No trades have been made so far.</p>
              ) : (
                <div className="overflow-auto max-h-[360px]">
                  <table className="w-full text-sm">
                    <thead className="text-left text-slate-500">
                      <tr>
                        <th className="py-2">Date</th>
                        <th className="py-2">Ticker</th>
                        <th className="py-2">Type</th>
                        <th className="py-2">Shares</th>
                        <th className="py-2">Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trades.map((t) => (
                        <tr key={t.id} className="border-t border-slate-100">
                          <td className="py-2 text-xs text-slate-500">{format(parseISO(t.traded_at), "dd MMM yy")}</td>
                          <td className="py-2 font-medium">{t.ticker}</td>
                          <td className={`py-2 ${t.trade_type === "BUY" ? "text-emerald-600" : "text-rose-600"}`}>
                            {t.trade_type}
                          </td>
                          <td className="py-2">{Number(t.shares).toFixed(3)}</td>
                          <td className="py-2">{Number(t.cash_amount).toFixed(2)} {t.currency}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </section>
      </div>

      {tradeModalOpen ? (
        <div className="fixed inset-0 z-40 bg-slate-900/45 backdrop-blur-[1px] flex items-center justify-center px-4">
          <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl border border-slate-200 p-5">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold">Add Trade</h3>
              <button
                onClick={() => setTradeModalOpen(false)}
                className="rounded-md p-1 text-slate-500 hover:bg-slate-100"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleTradeSubmit} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-600 mb-1">Ticker</label>
                  <input
                    value={tradeForm.ticker}
                    onChange={(e) => setTradeForm((prev) => ({ ...prev, ticker: e.target.value }))}
                    placeholder="AAPL"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-600 mb-1">Trade Type</label>
                  <select
                    value={tradeForm.tradeType}
                    onChange={(e) =>
                      setTradeForm((prev) => ({ ...prev, tradeType: e.target.value as "BUY" | "SELL" }))
                    }
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  >
                    <option value="BUY">BUY</option>
                    <option value="SELL">SELL</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-600 mb-1">Currency</label>
                  <input
                    value={tradeForm.currency}
                    onChange={(e) => setTradeForm((prev) => ({ ...prev, currency: e.target.value }))}
                    placeholder="USD"
                    maxLength={3}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm uppercase"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-600 mb-1">Platform</label>
                  <input
                    value={tradeForm.platform}
                    onChange={(e) => setTradeForm((prev) => ({ ...prev, platform: e.target.value }))}
                    placeholder="IBKR"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-600 mb-1">Price</label>
                  <input
                    type="number"
                    step="0.0001"
                    min="0"
                    value={tradeForm.price}
                    onChange={(e) => setTradeForm((prev) => ({ ...prev, price: e.target.value }))}
                    placeholder="101.95"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-600 mb-1">Shares</label>
                  <input
                    type="number"
                    step="0.000001"
                    min="0"
                    value={tradeForm.shares}
                    onChange={(e) => setTradeForm((prev) => ({ ...prev, shares: e.target.value }))}
                    placeholder="10"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    required
                  />
                </div>
              </div>

              <div className="rounded-lg bg-slate-50 border border-slate-200 px-3 py-2 text-sm text-slate-700">
                Amount: {liveTradeAmount.toFixed(2)} {tradeForm.currency.trim().toUpperCase() || "USD"}
              </div>

              {tradeError ? <p className="text-xs text-rose-600">{tradeError}</p> : null}

              <div className="pt-1 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setTradeModalOpen(false)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={tradeSubmitting}
                  className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
                >
                  {tradeSubmitting ? "Submitting..." : "Submit Trade"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {holdingModalOpen ? (
        <div className="fixed inset-0 z-40 bg-slate-900/45 backdrop-blur-[1px] flex items-center justify-center px-4">
          <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl border border-slate-200 p-5">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold">Add Holding</h3>
              <button
                onClick={() => setHoldingModalOpen(false)}
                className="rounded-md p-1 text-slate-500 hover:bg-slate-100"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleHoldingSubmit} className="space-y-3">
              <div>
                <label className="block text-xs text-slate-600 mb-1">Ticker</label>
                <input
                  value={holdingForm.ticker}
                  onChange={(e) => setHoldingForm((prev) => ({ ...prev, ticker: e.target.value }))}
                  placeholder="AAPL"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-600 mb-1">Shares Owned</label>
                  <input
                    type="number"
                    step="0.000001"
                    min="0"
                    value={holdingForm.sharesOwned}
                    onChange={(e) => setHoldingForm((prev) => ({ ...prev, sharesOwned: e.target.value }))}
                    placeholder="10"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-600 mb-1">Invested Amount</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={holdingForm.investedAmount}
                    onChange={(e) => setHoldingForm((prev) => ({ ...prev, investedAmount: e.target.value }))}
                    placeholder="1500.00"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-600 mb-1">Currency</label>
                  <input
                    value={holdingForm.currency}
                    onChange={(e) => setHoldingForm((prev) => ({ ...prev, currency: e.target.value }))}
                    placeholder="USD"
                    maxLength={3}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm uppercase"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-600 mb-1">Platform</label>
                  <input
                    value={holdingForm.platform}
                    onChange={(e) => setHoldingForm((prev) => ({ ...prev, platform: e.target.value }))}
                    placeholder="IBKR"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    required
                  />
                </div>
              </div>

              {holdingError ? <p className="text-xs text-rose-600">{holdingError}</p> : null}

              <div className="pt-1 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setHoldingModalOpen(false)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={holdingSubmitting}
                  className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
                >
                  {holdingSubmitting ? "Saving..." : "Save Holding"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {showTradeSuccess ? (
        <div className="fixed bottom-6 right-6 z-50 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 shadow-lg text-emerald-800 animate-in fade-in slide-in-from-bottom-2 duration-300">
          <div className="flex items-center gap-2 text-sm font-medium">
            <CheckCircle2 size={18} />
            Trade successfully submitted
          </div>
        </div>
      ) : null}

      {showHoldingSuccess ? (
        <div className="fixed bottom-6 right-6 z-50 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 shadow-lg text-emerald-800 animate-in fade-in slide-in-from-bottom-2 duration-300">
          <div className="flex items-center gap-2 text-sm font-medium">
            <CheckCircle2 size={18} />
            Holding successfully added
          </div>
        </div>
      ) : null}
    </div>
  );
}
