import { diagnosticSnapshot, researchAttempt } from "../researchDiagnostics.js";
import { Router } from "express";
import { cached, cacheGet, cacheStore, staleGet } from "../cache.js";
import { withFallback } from "../providers/registry.js";
import { historyResponse, historySeries } from "../historyStatus.js";
import { observedQuote, servedQuote, plainQuote, type ObservedQuote } from "../quoteStatus.js";
import * as yahoo from "../providers/yahoo.js";
import * as stooq from "../providers/stooq.js";
import * as nasdaq from "../providers/nasdaq.js";
import * as fred from "../providers/fred.js";
import * as ecb from "../providers/ecb.js";
import * as tradingview from "../providers/tradingview.js";
import * as coingecko from "../providers/coingecko.js";
import * as binance from "../providers/binance.js";
import * as news from "../providers/news.js";
import * as econcalendar from "../providers/econcalendar.js";
import * as finra from "../providers/finra.js";
import * as secedgar from "../providers/secedgar.js";

export const marketRouter = Router();

const QUOTE_TTL = 1_000;
const HISTORY_TTL = 20_000;
const NEWS_TTL = 60_000;

function fail(req: any, res: any, err: unknown) {
  const detail = err instanceof Error ? err.message : String(err);
  console.error("[market]", req.path, detail);
  res.status(502).json({ error: "All data providers are temporarily unavailable. Try again shortly." });
}

// VIX OHLC comes from candle providers. FRED is daily close only, never OHLC.

function isVix(symbol: string): boolean {
  return symbol.toUpperCase() === "^VIX" || symbol.toUpperCase() === "VIX";
}

async function vixQuote(symbol: string): Promise<yahoo.Quote> {
  const points = await fred.series("VIXCLS", 5);
  if (points.length === 0) throw new Error("fred: no VIX data");
  const last = points[points.length - 1];
  const prev = points.length > 1 ? points[points.length - 2] : null;
  const price = last.value;
  const previousClose = prev?.value ?? null;
  const change = previousClose !== null ? price - previousClose : null;
  const changePercent = previousClose ? (change! / previousClose) * 100 : null;
  return {
    symbol,
    name: "CBOE Volatility Index",
    price,
    change,
    changePercent,
    open: null,
    high: null,
    low: null,
    previousClose,
    bid: null,
    ask: null,
    volume: null,
    avgVolume: null,
    marketCap: null,
    pe: null,
    eps: null,
    dividendYield: null,
    week52High: null,
    week52Low: null,
    beta: null,
    sharesOutstanding: null,
    currency: "USD",
    exchange: "CBOE",
    marketState: null,
    time: null,
    source: "fred",
    providerClock:{value:last.date,basis:"daily_close_date"},
  };
}

// ---- quotes (per-symbol cache, so overlapping widgets share one fetch) ----

/**
 * Resolve quotes for a symbol list, reusing a per-symbol cache across every
 * caller (single quote widget, watchlist, screener, heatmap all share hits).
 * Nasdaq's public quote API is primary (no key, generous limits); Yahoo and
 * Stooq are fallbacks. A symbol that fails everywhere still falls back to
 * its last-known value instead of failing the whole batch.
 *
 * Fan-out bound: the /quotes route caps `symbols` at 150, so a single call
 * here does at most ~150 crypto lookups (only for recognized crypto symbols,
 * mutually exclusive with the stages below) + up to 300 Nasdaq calls (2 per
 * miss) + 1 batched Yahoo call + up to FALLBACK_PER_SYMBOL_CAP per-symbol
 * Yahoo chart calls + up to FALLBACK_PER_SYMBOL_CAP Stooq calls + 1 batched
 * TradingView call. Repetition beyond that is bounded by marketRouter's
 * per-IP rate limit (see index.ts).
 */
const FALLBACK_PER_SYMBOL_CAP = 20;
async function getQuotes(symbols: string[]): Promise<ObservedQuote[]> {
  const fresh = new Map<string, ObservedQuote>();
  const missing: string[] = [];
  for (const sym of symbols) {
    const hit = cacheGet<ObservedQuote>(`quote:${sym}`);
    if (hit) fresh.set(sym, servedQuote(hit,"cached"));
    else missing.push(sym);
  }
  if (missing.length === 0) return symbols.map((s) => fresh.get(s)!).filter(Boolean);

  const fetched = new Map<string, ObservedQuote>();
  let remaining = missing;

  const cryptoSymbols = remaining.filter((s) => binance.CRYPTO_SYMBOLS.has(s));
  if (cryptoSymbols.length > 0) {
    const results = await Promise.allSettled(cryptoSymbols.map((s) => researchAttempt(s,"quotes","binance",()=>binance.quote(s),2500)));
    results.forEach((r, i) => {
      if (r.status === "fulfilled") fetched.set(cryptoSymbols[i], r.value);
    });
    remaining = remaining.filter((s) => !fetched.has(s));
  }

  const vixSymbols = remaining.filter((s) => isVix(s));
  if (vixSymbols.length > 0) {
    const results = await Promise.allSettled(vixSymbols.map((s) => withFallback([
      ["yahoo-chart",()=>researchAttempt(s,"quotes","yahoo-chart",async()=>({...await yahoo.quoteFromChart("^VIX"),symbol:s}),2500)],
      ["fred",()=>researchAttempt(s,"quotes","fred",()=>vixQuote(s),2500)],
    ])));
    results.forEach((r, i) => {
      if (r.status === "fulfilled") fetched.set(vixSymbols[i], r.value);
    });
    remaining = remaining.filter((s) => !fetched.has(s));
  }

  remaining = remaining.filter(s=>!isVix(s));
  const nasdaqResults = await Promise.allSettled(remaining.map((s) => researchAttempt(s,"quotes","nasdaq",()=>nasdaq.quote(s),2500)));
  nasdaqResults.forEach((r, i) => {
    if (r.status === "fulfilled") fetched.set(remaining[i], r.value);
  });
  remaining = remaining.filter((s) => !fetched.has(s));

  if (remaining.length > 0) {
    try {
      let batch: Promise<yahoo.Quote[]> | undefined;
      const rows = (await Promise.allSettled(remaining.map(s=>researchAttempt(s,"quotes","yahoo",async()=>{
        const q=(await (batch ??= yahoo.quotes(remaining))).find(q=>q.symbol===s);
        if(!q) throw new Error("empty_response");return q;
      },2500)))).flatMap(r=>r.status==="fulfilled"?[r.value]:[]);
      for (const q of rows) fetched.set(q.symbol, q);
      remaining = remaining.filter((s) => !fetched.has(s));
    } catch {
      // fall through to chart-based per-symbol fetch below
    }
  }

  if (remaining.length > 0) {
    const batch = remaining.slice(0, FALLBACK_PER_SYMBOL_CAP);
    const results = await Promise.allSettled(batch.map((s) => researchAttempt(s,"quotes","yahoo-chart",()=>yahoo.quoteFromChart(s),2500)));
    results.forEach((r, i) => {
      if (r.status === "fulfilled") fetched.set(batch[i], r.value);
    });
    remaining = remaining.filter((s) => !fetched.has(s));
  }

  if (remaining.length > 0) {
    const batch = remaining.slice(0, FALLBACK_PER_SYMBOL_CAP);
    const results = await Promise.allSettled(batch.map((s) => researchAttempt(s,"quotes","stooq",()=>stooq.quote(s),2500)));
    results.forEach((r, i) => {
      if (r.status === "fulfilled") fetched.set(batch[i], r.value);
    });
  }

  // Fill gaps Nasdaq's quote endpoints don't cover (open, P/E, EPS, dividend
  // yield, beta, shares outstanding) from TradingView's public scanner API,
  // in one batched request for every quote that resolved an exchange.
  const needsFundamentals = [...fetched.values()].filter((q) => q.exchange && q.pe === null);
  if (needsFundamentals.length > 0) {
    try {
      const fundamentals = await Promise.race([tradingview.scanFundamentals(
        needsFundamentals.map((q) => ({ symbol: q.symbol, exchange: q.exchange }))
      ), new Promise<Map<string,never>>(resolve=>{const timer=setTimeout(()=>resolve(new Map<string,never>()),1500);timer.unref();})]);
      for (const q of needsFundamentals) {
        const f = fundamentals.get(q.symbol);
        if (!f) continue;
        q.open = q.open ?? f.open;
        q.pe = q.pe ?? f.pe;
        q.eps = q.eps ?? f.eps;
        q.dividendYield = q.dividendYield ?? f.dividendYield;
        q.beta = q.beta ?? f.beta;
        q.sharesOutstanding = q.sharesOutstanding ?? f.sharesOutstanding;
      }
    } catch {
      // best-effort enrichment only — never fails the quote request
    }
  }

  for (const [sym, q] of fetched) {
    const observation = observedQuote(q);
    fetched.set(sym, observation);
    cacheStore(`quote:${sym}`, observation, QUOTE_TTL);
  }

  const out: ObservedQuote[] = [];
  for (const sym of symbols) {
    const stale = fresh.has(sym) || fetched.has(sym) ? undefined : staleGet<ObservedQuote>(`quote:${sym}`);
    const q = fresh.get(sym) ?? fetched.get(sym) ?? (stale ? servedQuote(stale,"stale") : undefined);
    if (q) out.push(q);
  }
  return out;
}

marketRouter.get("/quotes", async (req, res) => {
  const symbols = String(req.query.symbols ?? "")
    .split(",")
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean)
    .slice(0, 150);
  if (symbols.length === 0) return res.status(400).json({ error: "symbols required" });
  try {
    const data = await getQuotes(symbols);
    if (data.length === 0) throw new Error("no quotes from any provider");
    res.json(req.query.metadata === "1" ? data : data.map(plainQuote));
  } catch (err) {
    fail(req, res, err);
  }
});

// ---- history / candles ----

marketRouter.get("/history/:symbol", async (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  const rangeKey = String(req.query.range ?? "6M");
  try {
    const request = yahooRange(rangeKey);
    const candleSymbol = isVix(symbol) ? "^VIX" : symbol;
    const load = (provider: "binance"|"nasdaq"|"yahoo"|"stooq", interval:string|null, fn:()=>Promise<yahoo.Candle[]>) =>
      researchAttempt(symbol,"history",provider,()=>historySeries(provider,interval,fn),4000,rangeKey);
    const data = await historyResponse(symbol, rangeKey, HISTORY_TTL, () =>
      binance.CRYPTO_SYMBOLS.has(symbol)
        ? load("binance",binance.historySettings(rangeKey).interval,()=>binance.history(symbol,rangeKey))
        : withFallback([
            ...(!isVix(symbol) ? [["nasdaq",()=>load("nasdaq",null,()=>nasdaq.history(symbol,rangeKey))] as [string,()=>Promise<import("../historyStatus.js").HistorySeries>]] : []),
            ["yahoo",()=>load("yahoo",request.interval,()=>yahoo.history(candleSymbol,request.range,request.interval))],
            ["stooq",()=>load("stooq","1d",()=>stooq.history(candleSymbol))],
          ])
    );
    // Existing chart clients keep the original array contract.
    res.json(req.query.metadata === "1" ? data : data.candles);
  } catch (err) {
    fail(req, res, err);
  }
});

function yahooRange(rangeKey: string): { range: string; interval: string } {
  const map: Record<string, { range: string; interval: string }> = {
    "1D": { range: "1d", interval: "5m" },
    "5D": { range: "5d", interval: "15m" },
    "1M": { range: "1mo", interval: "1h" },
    "6M": { range: "6mo", interval: "1d" },
    YTD: { range: "ytd", interval: "1d" },
    "1Y": { range: "1y", interval: "1d" },
    "5Y": { range: "5y", interval: "1wk" },
    MAX: { range: "max", interval: "1mo" },
  };
  return map[rangeKey] ?? map["6M"];
}

// ---- search ----

marketRouter.get("/search", async (req, res) => {
  const q = String(req.query.q ?? "").trim();
  if (!q) return res.json([]);
  try {
    const data = await cached(`search:${q.toLowerCase()}`, 300_000, () =>
      withFallback([
        ["tradingview", () => tradingview.search(q)],
        ["yahoo", () => yahoo.search(q)],
      ])
    );
    res.json(data);
  } catch (err) {
    fail(req, res, err);
  }
});

// ---- news ----

marketRouter.get("/news", async (req, res) => {
  const symbol = req.query.symbol ? String(req.query.symbol).toUpperCase() : null;
  try {
    const data = await cached(`news:${symbol ?? "top"}`, NEWS_TTL, async () => {
      if (symbol) {
        const lists = await Promise.allSettled([
          researchAttempt(symbol,"news","yahoo-rss",()=>news.symbolNews(symbol)),
          researchAttempt(symbol,"news","google-rss",()=>news.topNews(symbol + " stock")),
        ]);
        const ok = lists.filter((r) => r.status === "fulfilled").map((r) => (r as any).value);
        if (ok.length === 0) throw new Error("all news sources failed");
        return news.dedupe(ok).slice(0, 40);
      }
      const lists = await Promise.allSettled([
        news.topNews("stock market"),
        news.topNews("federal reserve economy"),
      ]);
      const ok = lists.filter((r) => r.status === "fulfilled").map((r) => (r as any).value);
      if (ok.length === 0) throw new Error("all news sources failed");
      return news.dedupe(ok).slice(0, 40);
    });
    res.json(data);
  } catch (err) {
    fail(req, res, err);
  }
});

// ---- economic calendar (Fed / ECB / CPI / NFP with forecast + actual) ----

marketRouter.get("/econ-calendar", async (req, res) => {
  try {
    const data = await cached("econ-calendar", 900_000, () => econcalendar.weeklyEvents());
    res.json(data);
  } catch (err) {
    fail(req, res, err);
  }
});

// ---- options ----

marketRouter.get("/options/:symbol", async (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  const expiry = req.query.expiry ? String(req.query.expiry) : undefined;
  try {
    const data = await cached(`options:${symbol}:${expiry ?? "front"}`, 60_000, () =>
      withFallback([
        ["nasdaq", () => nasdaq.optionChain(symbol, expiry)],
        [
          "yahoo",
          async () => {
            const y = await yahoo.options(symbol);
            return {
              symbol: y.symbol,
              underlyingPrice: y.underlyingPrice,
              expirationDates: y.expirationDates.map((d: number) => new Date(d * 1000).toISOString().slice(0, 10)),
              selectedDate: y.selectedDate ? new Date(y.selectedDate * 1000).toISOString().slice(0, 10) : null,
              calls: y.calls,
              puts: y.puts,
            };
          },
        ],
      ])
    );
    res.json(data);
  } catch (err) {
    fail(req, res, err);
  }
});

// ---- crypto ----

marketRouter.get("/crypto", async (req, res) => {
  try {
    const data = await cached("crypto:markets", 5_000, () =>
      withFallback([
        ["coingecko", () => coingecko.markets(50)],
        ["binance", () => binance.markets()],
      ])
    );
    res.json(data);
  } catch (err) {
    fail(req, res, err);
  }
});

marketRouter.get("/crypto/global", async (req, res) => {
  try {
    const data = await cached("crypto:global", 120_000, () =>
      withFallback([["coingecko", () => coingecko.globalStats()]])
    );
    res.json(data);
  } catch (err) {
    fail(req, res, err);
  }
});

marketRouter.get("/crypto/orderbook/:symbol", async (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  if (!binance.CRYPTO_SYMBOLS.has(symbol)) {
    return res.status(400).json({ error: "unsupported crypto symbol" });
  }
  try {
    const data = await cached(`orderbook:${symbol}`, 5_000, () =>
      withFallback([["binance", () => binance.orderBook(symbol)]])
    );
    res.json(data);
  } catch (err) {
    fail(req, res, err);
  }
});

// ---- macro: treasury yield curve (FRED) + key indexes via ETF proxies (Nasdaq) ----

const YIELD_SERIES: Array<{ id: string; tenor: string }> = [
  { id: "DGS3MO", tenor: "3M" },
  { id: "DGS5", tenor: "5Y" },
  { id: "DGS10", tenor: "10Y" },
  { id: "DGS30", tenor: "30Y" },
];

const INDEX_PROXIES: Record<string, string> = {
  SPY: "S&P 500 (SPY)",
  DIA: "Dow Jones (DIA)",
  QQQ: "Nasdaq 100 (QQQ)",
  IWM: "Russell 2000 (IWM)",
  GLD: "Gold (GLD)",
  USO: "WTI Crude (USO)",
  TLT: "20Y+ Treasury (TLT)",
  UUP: "Dollar Index (UUP)",
};

// ---- EU macro: ECB AAA euro-area yield curve + policy rate + HICP inflation,
// plus key European indexes via US-listed ETF proxies (same trick as the US
// index proxies above — Nasdaq/Yahoo already carry these tickers, so no new
// quote provider is needed).

const EU_YIELD_SERIES: Array<{ flowRef: string; key: string; tenor: string }> = [
  { flowRef: "YC", key: "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_3M", tenor: "3M" },
  { flowRef: "YC", key: "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_5Y", tenor: "5Y" },
  { flowRef: "YC", key: "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y", tenor: "10Y" },
  { flowRef: "YC", key: "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_30Y", tenor: "30Y" },
];

// Deposit facility rate — the ECB's operative policy rate since the 2024
// operational framework review (not the main refinancing rate).
const EU_POLICY_RATE = { flowRef: "FM", key: "D.U2.EUR.4F.KR.DFR.LEV" };
const EU_INFLATION = { flowRef: "ICP", key: "M.U2.N.000000.4.ANR" }; // HICP, y/y

const EU_INDEX_PROXIES: Record<string, string> = {
  FEZ: "Euro Stoxx 50 (FEZ)",
  IEUR: "MSCI Europe (IEUR)",
  EWG: "Germany (EWG)",
  EWU: "UK (EWU)",
  EWQ: "France (EWQ)",
  EWI: "Italy (EWI)",
};

marketRouter.get("/macro", async (req, res) => {
  try {
    if (req.query.region === "eu") {
      const [yieldResults, policyRate, inflation, quotes] = await Promise.all([
        Promise.allSettled(
          EU_YIELD_SERIES.map((s) => cached(`ecb:${s.key}`, 300_000, () => ecb.latest(s.flowRef, s.key)))
        ),
        cached(`ecb:${EU_POLICY_RATE.key}`, 300_000, () => ecb.latest(EU_POLICY_RATE.flowRef, EU_POLICY_RATE.key)).catch(
          () => null
        ),
        cached(`ecb:${EU_INFLATION.key}`, 300_000, () => ecb.latest(EU_INFLATION.flowRef, EU_INFLATION.key)).catch(
          () => null
        ),
        getQuotes(Object.keys(EU_INDEX_PROXIES)),
      ]);
      const yields = EU_YIELD_SERIES.map((s, i) => {
        const r = yieldResults[i];
        return { tenor: s.tenor, value: r.status === "fulfilled" ? r.value?.value ?? null : null };
      }).filter((y) => y.value !== null);

      const indexes = quotes.map((q) => ({
        symbol: q.symbol,
        label: EU_INDEX_PROXIES[q.symbol] ?? q.symbol,
        price: q.price,
        changePercent: q.changePercent,
      }));

      if (yields.length === 0 && indexes.length === 0) throw new Error("no EU macro data from any provider");
      res.json({
        yields,
        vix: null,
        indexes,
        policyRate: policyRate?.value ?? null,
        inflation: inflation?.value ?? null,
      });
      return;
    }

    const [yieldResults, vix, quotes] = await Promise.all([
      Promise.allSettled(YIELD_SERIES.map((s) => cached(`fred:${s.id}`, 300_000, () => fred.latest(s.id)))),
      cached("fred:VIXCLS", 300_000, () => fred.latest("VIXCLS")).catch(() => null),
      getQuotes(Object.keys(INDEX_PROXIES)),
    ]);
    const yields = YIELD_SERIES.map((s, i) => {
      const r = yieldResults[i];
      return { tenor: s.tenor, value: r.status === "fulfilled" ? r.value?.value ?? null : null };
    }).filter((y) => y.value !== null);

    const indexes = quotes.map((q) => ({
      symbol: q.symbol,
      label: INDEX_PROXIES[q.symbol] ?? q.symbol,
      price: q.price,
      changePercent: q.changePercent,
    }));

    if (yields.length === 0 && indexes.length === 0) throw new Error("no macro data from any provider");
    res.json({ yields, vix: vix?.value ?? null, indexes, policyRate: null, inflation: null });
  } catch (err) {
    fail(req, res, err);
  }
});

// ---- heatmap + screener over the full market (TradingView scanner — live) ----
// ?market=eu switches from the whole-US scan to the merged major-European-
// exchanges scan (see tradingview.europeMarketScan).

function marketParam(req: any): "us" | "eu" {
  return req.query.market === "eu" ? "eu" : "us";
}

// TradingView reports market cap in each stock's own listing currency (SEK,
// GBP, CHF, ...), not EUR — left unconverted, a 1.2T SEK Swedish company would
// outrank a 550B EUR Dutch one in the merged EU scan. Reference rates come
// from the same ECB source as the EU macro widget, so this needs no new
// provider (rate = local-currency units per 1 EUR).
const EU_FX_SERIES: Record<string, { flowRef: string; key: string }> = {
  GBP: { flowRef: "EXR", key: "D.GBP.EUR.SP00.A" },
  SEK: { flowRef: "EXR", key: "D.SEK.EUR.SP00.A" },
  CHF: { flowRef: "EXR", key: "D.CHF.EUR.SP00.A" },
};

async function eurFxRates(): Promise<Record<string, number>> {
  const rates: Record<string, number> = { EUR: 1 };
  const entries = await Promise.all(
    Object.entries(EU_FX_SERIES).map(async ([ccy, s]) => {
      const point = await cached(`ecb:fx:${ccy}`, 3_600_000, () => ecb.latest(s.flowRef, s.key)).catch(() => null);
      return [ccy, point?.value ?? null] as const;
    })
  );
  for (const [ccy, rate] of entries) if (rate) rates[ccy] = rate;
  return rates;
}

async function marketRows(market: "us" | "eu"): Promise<tradingview.MarketRow[]> {
  if (market === "eu") {
    return cached("marketscan:eu", 5_000, async () => {
      const [rows, fx] = await Promise.all([tradingview.europeMarketScan(1500), eurFxRates()]);
      return rows.map((r) => {
        const rate = r.currency ? fx[r.currency] : undefined;
        return rate && r.marketCap ? { ...r, marketCap: r.marketCap / rate } : r;
      });
    });
  }
  return cached("marketscan:full", 3_000, () => tradingview.marketScan(1500));
}

marketRouter.get("/heatmap", async (req, res) => {
  try {
    const rows = await marketRows(marketParam(req));
    const top = rows.filter((r) => r.marketCap).slice(0, 150);
    res.json(top);
  } catch (err) {
    fail(req, res, err);
  }
});

marketRouter.get("/screener", async (req, res) => {
  try {
    let rows = await marketRows(marketParam(req));
    const num = (v: unknown) => (v === undefined ? undefined : Number(v));
    const f = {
      sector: req.query.sector ? String(req.query.sector) : undefined,
      marketCapMin: num(req.query.marketCapMin),
      changeMin: num(req.query.changeMin),
      changeMax: num(req.query.changeMax),
      volumeMin: num(req.query.volumeMin),
    };
    rows = rows.filter((r) => {
      if (f.sector && r.sector !== f.sector) return false;
      if (f.marketCapMin !== undefined && (r.marketCap ?? 0) < f.marketCapMin) return false;
      if (f.changeMin !== undefined && (r.changePercent ?? -Infinity) < f.changeMin) return false;
      if (f.changeMax !== undefined && (r.changePercent ?? Infinity) > f.changeMax) return false;
      if (f.volumeMin !== undefined && (r.volume ?? 0) < f.volumeMin) return false;
      return true;
    });
    const sortKey = String(req.query.sort ?? "marketCap") as keyof tradingview.MarketRow;
    const dir = req.query.dir === "asc" ? 1 : -1;
    rows = [...rows].sort((a, b) => {
      const av = (a[sortKey] as number | null) ?? -Infinity;
      const bv = (b[sortKey] as number | null) ?? -Infinity;
      return (av < bv ? -1 : av > bv ? 1 : 0) * dir;
    });
    res.json(rows.slice(0, 500));
  } catch (err) {
    fail(req, res, err);
  }
});

marketRouter.get("/sectors", async (req, res) => {
  try {
    const rows = await marketRows(marketParam(req));
    res.json([...new Set(rows.map((r) => r.sector))].sort());
  } catch (err) {
    res.json([]);
  }
});

// ---- market recap: templated end-of-day-style narrative + supporting stats ----

const RECAP_TTL = 15_000;

function pct(n: number | null | undefined): string {
  if (n === null || n === undefined) return "flat";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function buildRecapSummary(d: {
  indexes: Array<{ symbol: string; label: string; changePercent: number | null }>;
  bestSector?: { sector: string; avgChangePercent: number };
  worstSector?: { sector: string; avgChangePercent: number };
  gainers: tradingview.MarketRow[];
  losers: tradingview.MarketRow[];
  vix: number | null;
}): string {
  const spy = d.indexes.find((i) => i.symbol === "SPY");
  const qqq = d.indexes.find((i) => i.symbol === "QQQ");
  const dia = d.indexes.find((i) => i.symbol === "DIA");
  const spyChange = spy?.changePercent ?? 0;
  const dir = spyChange > 0.15 ? "trading higher" : spyChange < -0.15 ? "trading lower" : "little changed";

  const parts: string[] = [];
  parts.push(
    `US stocks are ${dir}, with the S&P 500 ${pct(spy?.changePercent)}, the Nasdaq 100 ${pct(qqq?.changePercent)} and the Dow ${pct(dia?.changePercent)}.`
  );
  if (d.bestSector && d.worstSector && d.bestSector.sector !== d.worstSector.sector) {
    parts.push(
      `${d.bestSector.sector} is leading sector performance (${pct(d.bestSector.avgChangePercent)}), while ${d.worstSector.sector} lags (${pct(d.worstSector.avgChangePercent)}).`
    );
  }
  if (d.gainers[0] && d.losers[0]) {
    parts.push(
      `${d.gainers[0].name} paces advancers, up ${pct(d.gainers[0].changePercent)}, while ${d.losers[0].name} is the biggest decliner, down ${pct(
        d.losers[0].changePercent
      )}.`
    );
  }
  if (d.vix !== null) {
    parts.push(`The VIX volatility index is at ${d.vix.toFixed(2)}.`);
  }
  return parts.join(" ");
}

marketRouter.get("/recap", async (req, res) => {
  try {
    const data = await cached("recap:full", RECAP_TTL, async () => {
      const [quotes, vix, rows, headlines] = await Promise.all([
        getQuotes(Object.keys(INDEX_PROXIES)),
        cached("fred:VIXCLS", 300_000, () => fred.latest("VIXCLS")).catch(() => null),
        marketRows("us"),
        cached("news:recap", NEWS_TTL, async () => {
          const lists = await Promise.allSettled([
            news.topNews("stock market"),
            news.topNews("federal reserve economy"),
          ]);
          const ok = lists.filter((r) => r.status === "fulfilled").map((r) => (r as any).value);
          if (ok.length === 0) throw new Error("all news sources failed");
          return news.dedupe(ok);
        }),
      ]);

      const indexes = quotes.map((q) => ({
        symbol: q.symbol,
        label: INDEX_PROXIES[q.symbol] ?? q.symbol,
        price: q.price,
        changePercent: q.changePercent,
      }));

      const ranked = rows.filter((r) => (r.marketCap ?? 0) > 2_000_000_000 && r.changePercent !== null);
      const gainers = [...ranked].sort((a, b) => (b.changePercent ?? 0) - (a.changePercent ?? 0)).slice(0, 5);
      const losers = [...ranked].sort((a, b) => (a.changePercent ?? 0) - (b.changePercent ?? 0)).slice(0, 5);

      const sectorMap = new Map<string, { sum: number; count: number }>();
      for (const r of rows) {
        if (r.changePercent === null || !r.sector) continue;
        const cur = sectorMap.get(r.sector) ?? { sum: 0, count: 0 };
        cur.sum += r.changePercent;
        cur.count += 1;
        sectorMap.set(r.sector, cur);
      }
      const sectors = [...sectorMap.entries()]
        .map(([sector, { sum, count }]) => ({ sector, avgChangePercent: sum / count }))
        .sort((a, b) => b.avgChangePercent - a.avgChangePercent);

      const bestSector = sectors[0];
      const worstSector = sectors[sectors.length - 1];

      const summary = buildRecapSummary({ indexes, bestSector, worstSector, gainers, losers, vix: vix?.value ?? null });

      return {
        summary,
        updatedAt: new Date().toISOString(),
        indexes,
        vix: vix?.value ?? null,
        gainers,
        losers,
        sectors: sectors.slice(0, 3).concat(sectors.length > 3 ? sectors.slice(-3) : []),
        news: headlines.slice(0, 6),
      };
    });
    res.json(data);
  } catch (err) {
    fail(req, res, err);
  }
});

// ---- earnings calendar for a list of symbols ----

marketRouter.get("/calendar", async (req, res) => {
  const symbols = String(req.query.symbols ?? "")
    .split(",")
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean)
    .slice(0, 30);
  if (symbols.length === 0) return res.status(400).json({ error: "symbols required" });
  try {
    const data = await cached(`calendar:${symbols.join(",")}`, 3_600_000, () => tradingview.earningsCalendar(symbols));
    res.json(data);
  } catch (err) {
    fail(req, res, err);
  }
});

// ---- earnings history: forecast vs actual per quarter, plus next-day price move ----

marketRouter.get("/earnings-history/:symbol", async (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  try {
    const data = await cached(`earnings-history:${symbol}`, 3_600_000, async () => {
      const [surprises, candles] = await Promise.all([
        nasdaq.earningsSurprise(symbol),
        withFallback([
          ["nasdaq", () => nasdaq.history(symbol, "1Y")],
          ["yahoo", () => yahoo.history(symbol, yahooRange("1Y").range, yahooRange("1Y").interval)],
          ["stooq", () => stooq.history(symbol)],
        ]),
      ]);
      const sorted = [...candles].sort((a, b) => a.time - b.time);
      // Nearest trading-day close on/after a given date, and the close of the
      // trading day right after that — the "day after earnings" move.
      const closeOnOrAfter = (unixSeconds: number) => {
        for (let i = 0; i < sorted.length; i++) {
          if (sorted[i].time >= unixSeconds - 3 * 86_400) return i;
        }
        return -1;
      };
      return surprises.map((s) => {
        const idx = closeOnOrAfter(s.dateReported);
        const dayAfterChangePercent =
          idx >= 0 && idx + 1 < sorted.length
            ? ((sorted[idx + 1].close - sorted[idx].close) / sorted[idx].close) * 100
            : null;
        return { ...s, dayAfterChangePercent };
      });
    });
    res.json(data);
  } catch (err) {
    fail(req, res, err);
  }
});

// ---- short sale volume (FINRA Reg SHO daily file) ----

marketRouter.get("/short-volume/:symbol", async (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  try {
    const day = await cached("finra-shortvol-day", 6 * 3_600_000, () => finra.latestDay());
    const row = day.get(symbol);
    if (!row) return res.json(null);
    res.json({ ...row, shortVolumePercent: (row.shortVolume / row.totalVolume) * 100 });
  } catch (err) {
    fail(req, res, err);
  }
});

// ---- insider transactions (SEC EDGAR Form 4) ----

marketRouter.get("/insider/:symbol", async (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  try {
    const data = await cached(`insider:${symbol}`, 3_600_000, () => secedgar.insiderTransactions(symbol));
    res.json(data);
  } catch (err) {
    fail(req, res, err);
  }
});

// Read-only diagnostic observations; requesting this endpoint never loads a provider.
marketRouter.get("/research-diagnostics/:symbol", (req,res)=>{
  const symbol=req.params.symbol.toUpperCase();
  if(!/^[A-Z0-9.^=&-]{1,20}$/.test(symbol)||!/[A-Z0-9]/.test(symbol)) return res.status(400).json({error:"Invalid symbol"});
  res.setHeader("Cache-Control","no-store");
  res.json(diagnosticSnapshot(symbol));
});
