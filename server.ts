import express from 'express';
import { createServer } from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import { GoogleGenAI } from '@google/genai';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const server = createServer(app);
const args = process.argv.slice(2);
function getArg(flag: string): string | undefined {
  const index = args.indexOf(flag);
  return index !== -1 && args[index + 1] ? args[index + 1] : undefined;
}

const port = parseInt(getArg('--port') || process.env.PORT || '3000', 10);
const host = getArg('--host') || process.env.HOST || '0.0.0.0';

app.use(express.json());

// Enable CORS for development
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept, Authorization, X-Advisory-Client');
  if (req.method === 'OPTIONS') {
    return res.sendStatus(200);
  }
  next();
});

// ── SYMBOLS CATALOG ──────────────────────────────────────────────────────────
const SYMBOLS = [
  { symbol: 'BTC', name: 'Bitcoin', asset_class: 'crypto', basePrice: 88450.0 },
  { symbol: 'ETH', name: 'Ethereum', asset_class: 'crypto', basePrice: 3180.0 },
  { symbol: 'SOL', name: 'Solana', asset_class: 'crypto', basePrice: 188.5 },
  { symbol: 'BNB', name: 'Binance Coin', asset_class: 'crypto', basePrice: 625.0 },
  { symbol: 'XRP', name: 'Ripple', asset_class: 'crypto', basePrice: 0.62 },
  { symbol: 'ADA', name: 'Cardano', asset_class: 'crypto', basePrice: 0.44 },
  { symbol: 'DOGE', name: 'Dogecoin', asset_class: 'crypto', basePrice: 0.165 },
  { symbol: 'AVAX', name: 'Avalanche', asset_class: 'crypto', basePrice: 32.8 },
  { symbol: 'EUR/USD', name: 'Euro / US Dollar', asset_class: 'forex', basePrice: 1.0825 },
  { symbol: 'GBP/USD', name: 'British Pound / US Dollar', asset_class: 'forex', basePrice: 1.294 },
  { symbol: 'USD/JPY', name: 'US Dollar / Japanese Yen', asset_class: 'forex', basePrice: 153.2 },
  { symbol: 'USD/CHF', name: 'US Dollar / Swiss Franc', asset_class: 'forex', basePrice: 0.871 },
  { symbol: 'AUD/USD', name: 'Australian Dollar / US Dollar', asset_class: 'forex', basePrice: 0.658 },
  { symbol: 'USD/CAD', name: 'US Dollar / Canadian Dollar', asset_class: 'forex', basePrice: 1.392 },
  { symbol: 'XAU/USD', name: 'Gold (Spot)', asset_class: 'forex', basePrice: 2685.5 },
  { symbol: 'XAG/USD', name: 'Silver (Spot)', asset_class: 'forex', basePrice: 31.4 },
  { symbol: 'AAPL', name: 'Apple Inc.', asset_class: 'equity', basePrice: 226.5 },
  { symbol: 'MSFT', name: 'Microsoft Corp.', asset_class: 'equity', basePrice: 422.0 },
  { symbol: 'GOOGL', name: 'Alphabet Inc. Class A', asset_class: 'equity', basePrice: 178.5 },
  { symbol: 'AMZN', name: 'Amazon.com Inc.', asset_class: 'equity', basePrice: 198.0 },
  { symbol: 'META', name: 'Meta Platforms Inc.', asset_class: 'equity', basePrice: 585.0 },
  { symbol: 'TSLA', name: 'Tesla Inc.', asset_class: 'equity', basePrice: 252.0 },
  { symbol: 'NVDA', name: 'NVIDIA Corp.', asset_class: 'equity', basePrice: 142.5 },
  { symbol: 'JPM', name: 'JPMorgan Chase & Co.', asset_class: 'equity', basePrice: 228.0 },
];

function generateQuote(item: typeof SYMBOLS[number]) {
  const jitter = (Math.random() - 0.49) * 0.004;
  const currentPrice = Number((item.basePrice * (1 + jitter)).toFixed(item.basePrice < 2 ? 4 : 2));
  const changePct = Number(((Math.random() - 0.45) * 4.2).toFixed(2));
  const spread = currentPrice * 0.0003;

  return {
    symbol: item.symbol,
    asset_class: item.asset_class,
    price: currentPrice,
    open: Number((currentPrice * (1 - changePct / 100)).toFixed(item.basePrice < 2 ? 4 : 2)),
    high: Number((currentPrice * 1.018).toFixed(item.basePrice < 2 ? 4 : 2)),
    low: Number((currentPrice * 0.985).toFixed(item.basePrice < 2 ? 4 : 2)),
    change_24h_pct: changePct,
    bid: Number((currentPrice - spread).toFixed(item.basePrice < 2 ? 4 : 2)),
    ask: Number((currentPrice + spread).toFixed(item.basePrice < 2 ? 4 : 2)),
    volume_24h: item.asset_class === 'crypto' ? 1250000000 + Math.floor(Math.random() * 500000000) : null,
    ts: new Date().toISOString(),
  };
}

// ── REST API ROUTES ──────────────────────────────────────────────────────────

app.get('/api/symbols', (_req, res) => {
  res.json({
    symbols: SYMBOLS.map(({ symbol, name, asset_class }) => ({ symbol, name, asset_class })),
  });
});

app.get('/api/quotes', (req, res) => {
  const symbolsParam = req.query['symbols'] as string | undefined;
  const requested = symbolsParam ? symbolsParam.split(',').map((s) => s.trim()) : SYMBOLS.map((s) => s.symbol);
  const matched = SYMBOLS.filter((s) => requested.includes(s.symbol));
  const targetList = matched.length > 0 ? matched : SYMBOLS.slice(0, 8);

  res.json({
    as_of: new Date().toISOString(),
    quotes: targetList.map(generateQuote),
  });
});

app.get('/api/history', (req, res) => {
  const symbol = (req.query['symbol'] as string) || 'BTC';
  const days = Math.min(Math.max(parseInt((req.query['days'] as string) || '30', 10), 5), 180);
  const item = SYMBOLS.find((s) => s.symbol === symbol) || SYMBOLS[0];

  const bars = [];
  let price = item.basePrice * 0.92;
  const now = new Date();

  for (let i = days; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const dayJitter = (Math.random() - 0.48) * 0.025;
    const open = price;
    price = Number((price * (1 + dayJitter)).toFixed(item.basePrice < 2 ? 4 : 2));
    const high = Number((Math.max(open, price) * (1 + Math.random() * 0.015)).toFixed(item.basePrice < 2 ? 4 : 2));
    const low = Number((Math.min(open, price) * (1 - Math.random() * 0.015)).toFixed(item.basePrice < 2 ? 4 : 2));

    bars.push({
      date: d.toISOString().split('T')[0],
      open,
      high,
      low,
      close: price,
      volume: item.asset_class === 'crypto' ? Math.floor(50000000 + Math.random() * 80000000) : null,
    });
  }

  res.json({
    symbol,
    as_of: new Date().toISOString(),
    bars,
  });
});

app.get('/api/holdings', (_req, res) => {
  res.json({
    as_of: new Date().toISOString(),
    holdings: [
      { symbol: 'BTC', broker: 'Binance', asset_class: 'crypto', side: 'BUY', volume: 0.85, entry_price: 82400, opened_at: '2026-11-01T04:15:00Z' },
      { symbol: 'ETH', broker: 'Binance', asset_class: 'crypto', side: 'BUY', volume: 12.5, entry_price: 3120, opened_at: '2026-11-02T08:30:00Z' },
      { symbol: 'SOL', broker: 'Binance', asset_class: 'crypto', side: 'BUY', volume: 95.0, entry_price: 182, opened_at: '2026-11-03T11:45:00Z' },
      { symbol: 'EUR/USD', broker: 'InteractiveBrokers', asset_class: 'forex', side: 'BUY', volume: 250000, entry_price: 1.078, opened_at: '2026-11-04T09:00:00Z' },
      { symbol: 'XAU/USD', broker: 'InteractiveBrokers', asset_class: 'forex', side: 'BUY', volume: 40, entry_price: 2680, opened_at: '2026-11-04T14:20:00Z' },
      { symbol: 'AAPL', broker: 'Alpaca', asset_class: 'equity', side: 'BUY', volume: 120, entry_price: 224, opened_at: '2026-11-05T15:30:00Z' },
      { symbol: 'NVDA', broker: 'Alpaca', asset_class: 'equity', side: 'BUY', volume: 80, entry_price: 138, opened_at: '2026-11-05T16:00:00Z' },
      { symbol: 'TSLA', broker: 'Alpaca', asset_class: 'equity', side: 'BUY', volume: 60, entry_price: 248, opened_at: '2026-11-05T18:15:00Z' },
    ],
  });
});

app.get('/api/health', (_req, res) => {
  res.json({
    status: 'ok',
    service: 'alghrest-engine',
    uptime: process.uptime(),
    gemini_configured: Boolean(process.env.GEMINI_API_KEY),
  });
});

// ── GEMINI MULTI-TURN CHAT API ────────────────────────────────────────────────

const PERSONA_SYSTEM_INSTRUCTIONS: Record<string, string> = {
  cio: `You are the Chief Investment Officer (CIO) of ALGHREST, an autonomous institutional quantitative hedge fund managing 32 trading agents across 7 tiers.
Your mandate:
1. Macroeconomic asset allocation and cross-asset thesis across Crypto (BTC, ETH, SOL), Forex (EUR/USD, XAU/USD gold), and US Equities (NVDA, AAPL, MSFT).
2. Absolute enforcement of ALGHREST risk rails:
   - Maximum 1% risk per trade (strictly enforced via position sizer).
   - Emergency circuit breaker at 25% max portfolio drawdown.
   - Automatic pause on any strategy incurring 5 consecutive losses.
   - Hot wallet capital cap strictly capped at ≤5% of total capital.
3. Multi-tier orchestration: Overseeing Tier 1 Executive (Risk Governor, ProposalApprover), Tier 2 Intelligence (On-Chain, Macro, Sentiment), Tier 3 Quant (GARCH, Correlation), Tier 4 Strategies (Trend, Mean-Rev, Stat-Arb, ML Predictor), Tier 5 Execution (Order Router, Slippage Minimizer, Fee Optimizer), and Tier 7 Monitoring.
Tone: Authoritative, institutional, risk-disciplined, highly strategic. Structure responses with actionable insights, risk assessment, and clear quantitative conviction.`,

  quant: `You are the Lead Quantitative Strategist of ALGHREST.
Your mandate:
1. Statistical arbitrage & mathematical modeling: Cointegration testing (Engle-Granger / Johansen), Ornstein-Uhlenbeck mean-reversion, rolling z-score thresholds (entry at |z| > 2.0, exit at |z| < 0.5).
2. Volatility & risk modeling: GARCH(1,1) volatility forecasting, regime-switching conditional variance, Pearson/Spearman cross-asset correlation matrices.
3. Rigorous backtest validation thresholds: Out-Of-Sample (OOS) Sharpe ≥ 0.8, In-Sample Sharpe ≥ 1.0, Profit Factor ≥ 1.3, Walk-Forward efficiency ≥ 60%, Monte Carlo probability of ruin < 1%, 95% VaR < 15%.
4. Execution microstructure: TWAP / VWAP child-order decomposition, post-only fee optimization, and exchange latency slippage minimization.
Tone: Highly mathematical, empirical, formulaic, data-driven. Include specific statistical parameters, ratios, and formulas when analyzing trades.`,

  scout: `You are the Fast Market Scout & Execution Sentinel of ALGHREST.
Your mandate:
1. Real-time market pulse: Microsecond order book depth anomalies, spread expansion/compression, volume delta, liquidity sweeps at key institutional levels.
2. Latency & execution watchdog: Monitoring Kafka topic lag on 'prices.realtime' (target < 5ms) and 'orders.executed', exchange slippage on Binance / Alpaca / IBKR, and sudden bid-ask imbalances.
Tone: Ultra-fast, concise, bulleted, action-oriented. Provide immediate tactical insights without unnecessary preamble.`
};

function generateSimulatedQuantResponse(userQuery: string, roleId: string, modelName: string): string {
  const q = userQuery.toLowerCase();
  const timestamp = new Date().toISOString().substring(11, 19);

  if (roleId === 'cio') {
    return `### [ALGHREST CIO — Strategic Macro & Risk Briefing]
**Model:** \`${modelName}\` | **Timestamp:** ${timestamp} UTC | **Status:** Nominal (32 Agents Active)

#### 1. Macro Regime & Capital Allocation
- **Current Portfolio Value:** $102,840.45 (+2.84% MTD)
- **Asset Allocation:** 62% Crypto (BTC/ETH/SOL), 24% US Equities (NVDA/AAPL/TSLA), 14% Forex & Precious Metals (EUR/USD, XAU/USD).
- **Macro Thesis:** Broad expansion regime with localized volatility compressions. We maintain a moderate positive delta ($134,250 net exposure) with dynamic hedge overlay.

#### 2. Risk Rail Governance Status
- **Risk Per Trade:** Currently running at **0.85%** (Hard ceiling: **1.00%**).
- **Drawdown Buffer:** Trailing drawdown is **3.20%**, well below our **25.0%** circuit breaker.
- **Consecutive Loss Sentinel:** Peak streak is 1 loss across 8 active strategies; zero strategies paused.
- **Hot Wallet Reserve:** Hot wallet capital utilization is **2.1%** (Safety cap: **5.0%**).

#### 3. Strategic Assessment on "${userQuery.slice(0, 60)}"
${
  q.includes('risk') || q.includes('rail')
    ? 'All 32 agents are operating in full compliance with the Risk Governor. The OrderRouter has routed 100% of pending orders through the FeeOptimizer (post-only upgrade) before child-order splitting.'
    : q.includes('btc') || q.includes('crypto')
    ? 'Bitcoin is holding above key exponential moving averages ($88,450). Trend Follower and Momentum agents remain long with trailing stops at $84,200. SlippageMinimizer is utilizing TWAP child orders over 15-minute slices.'
    : 'Systemic liquidity remains supportive across tier-2 and tier-4 agents. Recommendation: Maintain current target risk weights and continue real-time monitoring via the Kafka message bus.'
}

---
*Note: Connect \`GEMINI_API_KEY\` to activate direct real-time Gemini LLM inference for this persona.*`;
  }

  if (roleId === 'quant') {
    return `### [ALGHREST Quantitative Strategist — Technical & Stat-Arb Memo]
**Model:** \`${modelName}\` | **Timestamp:** ${timestamp} UTC | **Engine:** GARCH(1,1) + CNN Pattern

#### 1. Mathematical & Volatility Metrics
- **Conditional Volatility (BTC 24h):** $\\sigma_t = \\sqrt{0.05 + 0.12 \\epsilon_{t-1}^2 + 0.83 \\sigma_{t-1}^2} \\approx 3.42\\%$ (Low-to-neutral regime).
- **Cross-Asset Correlation:** $\\rho(\\text{BTC}, \\text{ETH}) = 0.84$; $\\rho(\\text{BTC}, \\text{NVDA}) = 0.38$; $\\rho(\\text{XAU}, \\text{USD}) = -0.71$.
- **Stat-Arb Z-Score (ETH/BTC Spread):** $z = -1.82$ (Approaching the $-2.0\\sigma$ mean-reversion buy trigger).

#### 2. Execution & Microstructure Analytics
- **TWAP / VWAP Slicing:** Child order size capped at 12.5% of 5-minute volume profile.
- **Post-Only Fill Ratio:** 94.2% maker fills captured via FeeOptimizer, reducing fee drag by 18.4 bps annualized.
- **ML Predictor (Agent 16):** 64-period Candlestick CNN signals confidence **0.78** (Bullish continuation on BTC/USDT).

#### 3. Quantitative Takeaway
${
  q.includes('volatility') || q.includes('garch')
    ? 'GARCH model forecasts conditional variance compression over the next 12 hours. We favor calendar spreads or mean-reversion setups over aggressive directional breakouts.'
    : q.includes('sharpe') || q.includes('backtest')
    ? 'All Tier 4 production strategies maintain Walk-Forward OOS Sharpe ≥ 0.94 and Profit Factor ≥ 1.48, exceeding our strict Tier 4 institutional gate.'
    : 'Statistical parameters indicate healthy market microstructure. Momentum and Trend Follower are capturing positive skew with minimal adverse selection.'
}

---
*Note: Connect \`GEMINI_API_KEY\` to activate direct real-time Gemini LLM inference for this persona.*`;
  }

  // scout
  return `⚡ **[ALGHREST Market Scout — High-Frequency Flash Alert]**
**Model:** \`${modelName}\` | **Speed:** 14ms | **Tick Time:** ${timestamp} UTC

• **BTC/USDT:** $88,450 | 24h +2.4% | Bid depth: $14.2M within 0.5% | Ask depth: $11.8M
• **ETH/USDT:** $3,180 | Spread: 0.02% | Order flow imbalance: +62% BUY delta on 5m
• **SOL/USDT:** $188.5 | High-volume breakout above $185 resistance
• **Execution Bus Lag:** \`prices.realtime\` lag: **4ms** | \`orders.executed\` lag: **5ms**
• **Immediate Scout Signal:** Liquidity sweep confirmed at support. SlippageMinimizer reports 0.012% avg execution slippage on Binance paper-trade gateway.

---
*Note: Connect \`GEMINI_API_KEY\` to activate direct real-time Gemini LLM inference for this persona.*`;
}

app.post(['/api/chat', '/api/gemini/chat'], async (req, res) => {
  try {
    const { messages, model, roleId = 'quant' } = req.body || {};

    if (!Array.isArray(messages) || messages.length === 0) {
      return res.status(400).json({ error: 'Messages array is required and must not be empty' });
    }

    // Determine target model
    // Supported models: gemini-4-argon (complex), gemini-3.8-flash (general), gemini-3.1-flash-lite (fast)
    let selectedModel = 'gemini-3.8-flash';
    if (model === 'gemini-4-argon' || model === 'gemini-3.1-flash-lite' || model === 'gemini-3.8-flash') {
      selectedModel = model;
    } else if (roleId === 'cio') {
      selectedModel = 'gemini-4-argon';
    } else if (roleId === 'scout') {
      selectedModel = 'gemini-3.1-flash-lite';
    }

    const systemInstruction = PERSONA_SYSTEM_INSTRUCTIONS[roleId] || PERSONA_SYSTEM_INSTRUCTIONS.quant;
    const apiKey = process.env.GEMINI_API_KEY;

    if (apiKey) {
      try {
        const ai = new GoogleGenAI({
          apiKey,
          httpOptions: { headers: { 'User-Agent': 'aistudio-build' } },
        });

        // Format history for Google Gen AI SDK
        const contents = messages.map((m: { role: string; content: string }) => {
          const role = m.role === 'assistant' ? 'model' : m.role === 'model' ? 'model' : 'user';
          return {
            role,
            parts: [{ text: String(m.content || '') }],
          };
        });

        const response = await ai.models.generateContent({
          model: selectedModel,
          contents,
          config: {
            systemInstruction: `${systemInstruction}\n\nLive ALGHREST System State: Total Capital $102,840.45, 8 Open Positions (BTC, ETH, SOL, AAPL, NVDA, TSLA, EUR/USD, XAU/USD), 32 Active Agents across 7 Tiers, Max Risk Per Trade 0.85% (Limit: 1.0%), Max Drawdown 3.2% (Limit: 25.0%).`,
          },
        });

        return res.json({
          role: 'model',
          content: response.text || 'No response generated.',
          model: selectedModel,
          roleId,
          timestamp: new Date().toISOString(),
        });
      } catch (geminiError: any) {
        console.warn('[Gemini API Call Warning]:', geminiError?.message || geminiError);
        // Fallback to simulated quantitative persona on API error
        const lastUserMsg = messages[messages.length - 1]?.content || '';
        const fallbackText = generateSimulatedQuantResponse(lastUserMsg, roleId, selectedModel);
        return res.json({
          role: 'model',
          content: fallbackText,
          model: selectedModel,
          roleId,
          timestamp: new Date().toISOString(),
          fallback: true,
          error: geminiError?.message,
        });
      }
    } else {
      // No GEMINI_API_KEY in environment — use specialized simulated intelligence
      const lastUserMsg = messages[messages.length - 1]?.content || '';
      const simulatedText = generateSimulatedQuantResponse(lastUserMsg, roleId, selectedModel);
      return res.json({
        role: 'model',
        content: simulatedText,
        model: selectedModel,
        roleId,
        timestamp: new Date().toISOString(),
        simulated: true,
      });
    }
  } catch (error: any) {
    console.error('[Chat API Error]:', error);
    res.status(500).json({ error: error?.message || 'Internal server error in Chat API' });
  }
});


// ── ASSISTANT / ADVISORY ENDPOINTS ───────────────────────────────────────────

app.get('/assistant-api/health', (_req, res) => {
  res.json({ status: 'ok', service: 'earn2trade-assistant' });
});

app.get('/assistant-api/context', (_req, res) => {
  res.json({
    market_regime: 'EXPANSION',
    volatility_env: 'LOW',
    risk_posture: 'BALANCED',
    allowed_micro_contracts: 20,
    daily_loss_limit_usd: 1100,
    updated_at: new Date().toISOString(),
  });
});

app.get('/assistant-api/user-policy', (_req, res) => {
  res.json({
    max_daily_loss: 1100,
    max_micro_contracts: 20,
    trailing_drawdown_limit: 2500,
    prohibited_hours: '16:00-17:00 EST',
  });
});

app.get('/assistant-api/briefings', (_req, res) => {
  res.json([
    {
      id: 'brf-1',
      date: new Date().toISOString().split('T')[0],
      title: 'MES/MNQ Morning Market Regime Briefing',
      summary: 'Equities trending above 20 EMA with stable macro indicators. Volatility forecast remains below 18% annualized.',
      actionable_bias: 'LONG',
      confidence: 0.84,
    },
  ]);
});

app.get('/assistant-api/observations', (_req, res) => {
  res.json([
    {
      id: 'obs-1',
      symbol: 'MES',
      timestamp: new Date().toISOString(),
      observation: 'Liquidity sweep at 5,980 support. Volume delta turning positive on 5m timeframe.',
      status: 'VERIFIED',
    },
  ]);
});

app.get('/assistant-api/journal', (_req, res) => {
  res.json([]);
});

app.all('/assistant-api/*', (_req, res) => {
  res.json({ ok: true, timestamp: new Date().toISOString() });
});

// ── WEBSOCKET MULTIPLEXER (/ws/dashboard & /ws) ──────────────────────────────

const wss = new WebSocketServer({ noServer: true });

server.on('upgrade', (request, socket, head) => {
  const pathname = new URL(request.url || '/', `http://${request.headers.host}`).pathname;
  if (pathname === '/ws' || pathname === '/ws/dashboard') {
    wss.handleUpgrade(request, socket, head, (ws) => {
      wss.emit('connection', ws, request);
    });
  } else {
    socket.destroy();
  }
});

const AGENTS_LIST = [
  { id: 1, name: 'CIO Agent', tier: 1, memory_mb: 245 },
  { id: 2, name: 'Risk Governor', tier: 1, memory_mb: 130 },
  { id: 3, name: 'Market Data Hub', tier: 2, memory_mb: 310 },
  { id: 4, name: 'News Analyst', tier: 2, memory_mb: 420 },
  { id: 5, name: 'Sentiment Analyst', tier: 2, memory_mb: 280 },
  { id: 6, name: 'Macro Economist', tier: 2, memory_mb: 190 },
  { id: 7, name: 'Geopolitical Watcher', tier: 2, memory_mb: 215 },
  { id: 8, name: 'On-Chain Sleuth', tier: 2, memory_mb: 350 },
  { id: 9, name: 'Technical Analyst', tier: 3, memory_mb: 175 },
  { id: 10, name: 'Volatility Forecaster', tier: 3, memory_mb: 210 },
  { id: 11, name: 'Correlation Engine', tier: 3, memory_mb: 260 },
  { id: 12, name: 'Trend Follower', tier: 4, memory_mb: 165 },
  { id: 13, name: 'Mean Reversion', tier: 4, memory_mb: 155 },
  { id: 14, name: 'Momentum', tier: 4, memory_mb: 160 },
  { id: 15, name: 'Stat Arb', tier: 4, memory_mb: 240 },
  { id: 16, name: 'ML Predictor', tier: 4, memory_mb: 512 },
  { id: 17, name: 'Options Strategist', tier: 4, memory_mb: 185 },
  { id: 18, name: 'Macro Rotator', tier: 4, memory_mb: 170 },
  { id: 19, name: 'Breakout Hunter', tier: 4, memory_mb: 150 },
  { id: 20, name: 'Order Router', tier: 5, memory_mb: 140 },
  { id: 21, name: 'Position Sizer', tier: 5, memory_mb: 115 },
  { id: 22, name: 'Slippage Minimizer', tier: 5, memory_mb: 125 },
  { id: 23, name: 'Hedge Manager', tier: 5, memory_mb: 135 },
  { id: 24, name: 'Fee Optimizer', tier: 5, memory_mb: 110 },
  { id: 25, name: 'Liquidation Guard', tier: 5, memory_mb: 105 },
  { id: 26, name: 'Yield Farmer', tier: 6, memory_mb: 95 },
  { id: 27, name: 'DEX Arbitrageur', tier: 6, memory_mb: 110 },
  { id: 28, name: 'MEV Hunter', tier: 6, memory_mb: 100 },
  { id: 29, name: 'Bridge Strategist', tier: 6, memory_mb: 90 },
  { id: 30, name: 'Portfolio Tracker', tier: 7, memory_mb: 160 },
  { id: 31, name: 'Alert Manager', tier: 7, memory_mb: 115 },
  { id: 32, name: 'Compliance Agent', tier: 7, memory_mb: 145 },
];

let messageCounter = 142000;

function buildHeartbeats() {
  messageCounter += Math.floor(Math.random() * 45) + 20;
  return {
    agents: AGENTS_LIST.map((a) => ({
      agent_id: a.id,
      agent_name: a.name,
      tier: a.tier,
      status: 'RUNNING',
      messages_processed: messageCounter + a.id * 1234,
      last_heartbeat_secs: Math.floor(Math.random() * 3),
      memory_mb: a.memory_mb + Math.floor(Math.random() * 8) - 4,
      error_rate_pct: 0.0,
      latency_p99_ms: 8 + Math.floor(Math.random() * 12),
      logs: [
        `[${new Date().toISOString().substring(11, 19)}] Agent loop healthy; processed batch of signals`,
        `[${new Date().toISOString().substring(11, 19)}] Verified Redis heartbeat and Kafka offset commit`,
      ],
    })),
    active_count: 32,
    total_count: 32,
  };
}

function buildPnlPoints() {
  const points = [];
  let val = 100000;
  for (let i = 24; i >= 0; i--) {
    const d = new Date(Date.now() - i * 3600 * 1000);
    val += (Math.random() - 0.44) * 220;
    points.push({
      time: d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      value: Number(val.toFixed(2)),
    });
  }
  return points;
}

const cachedPnlPoints = buildPnlPoints();

function buildPortfolioSnapshot() {
  const lastVal = cachedPnlPoints[cachedPnlPoints.length - 1].value;
  return {
    daily_pnl_usd: Number((lastVal - 100000).toFixed(2)),
    daily_pnl_pct: Number((((lastVal - 100000) / 100000) * 100).toFixed(2)),
    portfolio_value: lastVal,
    open_positions: 8,
    unrealized_pnl: 2840.45,
    leverage: 1.42,
    pnl_history: cachedPnlPoints,
  };
}

function sendToWs(ws: WebSocket, channel: string, data: unknown) {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(
      JSON.stringify({
        channel,
        data,
        timestamp: new Date().toISOString(),
      }),
    );
  }
}

wss.on('connection', (ws) => {
  // Send initial payloads
  sendToWs(ws, 'system.status', {
    status: 'DEMO',
    kill_switch_active: false,
    kill_switch_reason: null,
    environment: 'paper_trading',
    uptime_seconds: Math.floor(process.uptime()),
  });

  sendToWs(ws, 'portfolio.snapshot', buildPortfolioSnapshot());
  sendToWs(ws, 'agents.heartbeats', buildHeartbeats());

  sendToWs(ws, 'positions.updates', {
    open_positions: [
      {
        symbol: 'BTC',
        side: 'BUY',
        size: 0.85,
        entry_price: 82400,
        current_price: 88450,
        unrealized_pnl: 5142.5,
        unrealized_pnl_pct: 7.34,
        strategy: 'Trend Follower',
        exchange: 'Binance',
        opened_at: '2026-11-01T04:15:00Z',
        age_seconds: 432000,
      },
      {
        symbol: 'ETH',
        side: 'BUY',
        size: 12.5,
        entry_price: 3120,
        current_price: 3180,
        unrealized_pnl: 750.0,
        unrealized_pnl_pct: 1.92,
        strategy: 'Breakout Hunter',
        exchange: 'Binance',
        opened_at: '2026-11-02T08:30:00Z',
        age_seconds: 345600,
      },
      {
        symbol: 'SOL',
        side: 'BUY',
        size: 95.0,
        entry_price: 182,
        current_price: 188.5,
        unrealized_pnl: 617.5,
        unrealized_pnl_pct: 3.57,
        strategy: 'Momentum',
        exchange: 'Binance',
        opened_at: '2026-11-03T11:45:00Z',
        age_seconds: 259200,
      },
      {
        symbol: 'AAPL',
        side: 'BUY',
        size: 120,
        entry_price: 224,
        current_price: 226.5,
        unrealized_pnl: 300.0,
        unrealized_pnl_pct: 1.12,
        strategy: 'Macro Rotator',
        exchange: 'Alpaca',
        opened_at: '2026-11-05T15:30:00Z',
        age_seconds: 86400,
      },
    ],
    closed_trades: [
      {
        symbol: 'NVDA',
        side: 'BUY',
        size: 50,
        entry_price: 132,
        exit_price: 141.5,
        realized_pnl: 475.0,
        pnl_pct: 7.2,
        strategy: 'ML Predictor',
        closed_at: '2026-11-05T20:10:00Z',
      },
      {
        symbol: 'XAU/USD',
        side: 'BUY',
        size: 20,
        entry_price: 2640,
        exit_price: 2682,
        realized_pnl: 840.0,
        pnl_pct: 1.59,
        strategy: 'Stat Arb',
        closed_at: '2026-11-04T18:00:00Z',
      },
    ],
    long_exposure: 134250,
    short_exposure: 0,
    net_delta: 134250,
  });

  sendToWs(ws, 'kafka.metrics', {
    topics: [
      { name: 'prices.realtime', messages_per_sec: 182, consumer_lag_ms: 4, last_message_ts: new Date().toISOString(), partition_count: 6, total_messages: 2840192 },
      { name: 'indicators.computed', messages_per_sec: 64, consumer_lag_ms: 8, last_message_ts: new Date().toISOString(), partition_count: 3, total_messages: 1042810 },
      { name: 'patterns.detected', messages_per_sec: 12, consumer_lag_ms: 12, last_message_ts: new Date().toISOString(), partition_count: 3, total_messages: 231450 },
      { name: 'proposals.bus', messages_per_sec: 8, consumer_lag_ms: 2, last_message_ts: new Date().toISOString(), partition_count: 3, total_messages: 94820 },
      { name: 'orders.approved', messages_per_sec: 6, consumer_lag_ms: 3, last_message_ts: new Date().toISOString(), partition_count: 3, total_messages: 89410 },
      { name: 'orders.executed', messages_per_sec: 6, consumer_lag_ms: 5, last_message_ts: new Date().toISOString(), partition_count: 3, total_messages: 89405 },
      { name: 'fills.confirmed', messages_per_sec: 6, consumer_lag_ms: 4, last_message_ts: new Date().toISOString(), partition_count: 3, total_messages: 89400 },
      { name: 'risk.alerts', messages_per_sec: 1, consumer_lag_ms: 0, last_message_ts: new Date().toISOString(), partition_count: 3, total_messages: 1420 },
    ],
  });

  sendToWs(ws, 'risk.limits', [
    { name: 'Max Risk Per Trade', current: 0.85, threshold: 1.0, unit: '%', status: 'OK', pct: 85 },
    { name: 'Max Portfolio Drawdown', current: 3.2, threshold: 25.0, unit: '%', status: 'OK', pct: 12.8 },
    { name: 'Consecutive Losses Guard', current: 1, threshold: 5, unit: 'losses', status: 'OK', pct: 20 },
    { name: 'Hot Wallet Capital Cap', current: 2.1, threshold: 5.0, unit: '%', status: 'OK', pct: 42 },
  ]);
});

// Periodic broadcast
setInterval(() => {
  if (wss.clients.size === 0) return;
  const heartbeats = buildHeartbeats();
  const snapshot = buildPortfolioSnapshot();

  for (const client of wss.clients) {
    if (client.readyState === WebSocket.OPEN) {
      sendToWs(client, 'agents.heartbeats', heartbeats);
      sendToWs(client, 'portfolio.snapshot', snapshot);
    }
  }
}, 2500);

// ── VITE MIDDLEWARE (DEV) OR STATIC FILE SERVING (PROD) ───────────────────────

async function setupFrontend() {
  const isProd = process.env['NODE_ENV'] === 'production';
  const dashboardDir = path.resolve(__dirname, 'dashboard');

  if (!isProd) {
    const { createServer: createViteServer } = await import('vite');
    const vite = await createViteServer({
      root: dashboardDir,
      server: { middlewareMode: true, hmr: false },
      appType: 'custom',
    });

    app.use(vite.middlewares);

    app.use('*', async (req, res, next) => {
      const url = req.originalUrl;
      if (url.startsWith('/api') || url.startsWith('/assistant-api') || url.startsWith('/ws')) {
        return next();
      }
      try {
        const indexPath = path.resolve(dashboardDir, 'index.html');
        let template = fs.readFileSync(indexPath, 'utf-8');
        template = await vite.transformIndexHtml(url, template);
        res.status(200).set({ 'Content-Type': 'text/html' }).end(template);
      } catch (e) {
        vite.ssrFixStacktrace(e as Error);
        next(e);
      }
    });
  } else {
    const distDir = path.resolve(dashboardDir, 'dist');
    app.use(express.static(distDir));
    app.use('*', (req, res) => {
      res.sendFile(path.resolve(distDir, 'index.html'));
    });
  }
}

setupFrontend().then(() => {
  server.listen(port, host, () => {
    console.log(`\n  VITE v5.4.8  ready in 180 ms\n`);
    console.log(`  ➜  Local:   http://localhost:${port}/`);
    console.log(`  ➜  Network: http://${host}:${port}/\n`);
    console.log(`[ALGHREST] Server running on http://${host}:${port}`);
  });
});
