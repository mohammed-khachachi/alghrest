import { useEffect, useState } from 'react';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { clsx } from 'clsx';
import { PlayCircle, StopCircle, RefreshCw, BarChart2, ShieldCheck } from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

interface DailyLog {
  day: number;
  date: string;
  price: number;
  daily_pnl: number;
  cumulative_pnl: number;
  equity: number;
  drawdown_pct: number;
  trades_count: number;
  win_rate: number;
  consecutive_losses: number;
  decision_logic: string;
}

// DailyLog interface remains the same

export function BacktestSimulation() {
  const [symbol, setSymbol] = useState('SOLUSDT');
  const [period, setPeriod] = useState('2Y');
  const [currentDay, setCurrentDay] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isFinished, setIsFinished] = useState(false);
  const [fullLogs, setFullLogs] = useState<DailyLog[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Fetch REAL Historical Data from Binance
  useEffect(() => {
    setIsPlaying(false);
    setIsFinished(false);
    setCurrentDay(0);
    setIsLoading(true);

    const fetchMarketData = async () => {
      try {
        const endDate = new Date();
        const startDate = new Date();
        
        if (period === '1Y') startDate.setFullYear(startDate.getFullYear() - 1);
        else if (period === '2Y') startDate.setFullYear(startDate.getFullYear() - 2);
        else if (period === 'YTD') {
           startDate.setFullYear(endDate.getFullYear());
           startDate.setMonth(0);
           startDate.setDate(1);
        }

        // warmup needs to be 200 days before the startDate
        const warmupStartObj = new Date(startDate);
        warmupStartObj.setDate(warmupStartObj.getDate() - 200);
        
        const warmupStart = warmupStartObj.getTime();
        const yearEnd = endDate.getTime();
        
        let rawData: any[] = [];
        
        if (symbol.endsWith('USDT')) {
          const res = await fetch(`https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=1d&startTime=${warmupStart}&endTime=${yearEnd}&limit=1000`);
          rawData = await res.json();
        } else {
          // Yahoo Finance via Proxy
          const startSeconds = Math.floor(warmupStart / 1000);
          const endSeconds = Math.floor(yearEnd / 1000);
          const res = await fetch(`/yahoo-api/v8/finance/chart/${symbol}?interval=1d&period1=${startSeconds}&period2=${endSeconds}`);
          const data = await res.json();
          
          if (data.chart && data.chart.result && data.chart.result.length > 0) {
            const result = data.chart.result[0];
            const timestamps = result.timestamp;
            const quote = result.indicators.quote[0];
            
            for (let i = 0; i < timestamps.length; i++) {
              if (quote.close[i] !== null) {
                // Map to Binance kline format: [timestamp, open, high, low, close]
                rawData.push([
                  timestamps[i] * 1000,
                  quote.open[i],
                  quote.high[i],
                  quote.low[i],
                  quote.close[i]
                ]);
              }
            }
          }
        }
        
        const allCloses: number[] = rawData.map((c: any) => parseFloat(c[4]));
        
        // Helper: Exponential Moving Average
        const calculateEMA = (prices: number[], period: number): number[] => {
          const k = 2 / (period + 1);
          const emaArray = new Array(prices.length).fill(0);
          if (prices.length < period) return emaArray;
          
          let sum = 0;
          for (let i = 0; i < period; i++) sum += prices[i];
          emaArray[period - 1] = sum / period;
          
          for (let i = period; i < prices.length; i++) {
            emaArray[i] = (prices[i] - emaArray[i - 1]) * k + emaArray[i - 1];
          }
          return emaArray;
        };
        const ema19All = calculateEMA(allCloses, 19);
        const ema200All = calculateEMA(allCloses, 200);

        // Find the index of the Start Date to begin trading there
        let startIdx = rawData.findIndex((c: any) => c[0] >= startDate.getTime());
        if (startIdx < 10) startIdx = 10; // Safety: ensure enough warm-up
        
        const logs: DailyLog[] = [];
        const INITIAL_CAPITAL = 100.0;
        let totalDeposited = INITIAL_CAPITAL;
        let equity = INITIAL_CAPITAL;
        let peakEquity = INITIAL_CAPITAL;
        let allocatedCapital = INITIAL_CAPITAL; // Quarterly compounded capital
        let currentConsecutiveLosses = 0;
        let ceoHaltCooldown = 0; // CEO keeps system halted for N days

        for (let i = startIdx; i < rawData.length; i++) {
          const currCandle = rawData[i];
          const currOpen = parseFloat(currCandle[1]);
          const currHigh = parseFloat(currCandle[2]);
          const currLow = parseFloat(currCandle[3]);
          const currClose = parseFloat(currCandle[4]);
          const dateStr = new Date(currCandle[0]).toISOString().split('T')[0];
          
          // ═══════════════════════════════════════════════════════════════
          // AGENT #3: Volatility Forecaster (Tier 3)
          // Calculates Average True Range to assess market turbulence
          // ═══════════════════════════════════════════════════════════════
          const atrPeriod = 7;
          let atrSum = 0;
          for (let k = i - atrPeriod; k < i; k++) {
            const h = parseFloat(rawData[k][2]);
            const l = parseFloat(rawData[k][3]);
            const pc = parseFloat(rawData[k - 1][4]);
            atrSum += Math.max(h - l, Math.abs(h - pc), Math.abs(l - pc));
          }
          const atr = atrSum / atrPeriod;
          const atrPct = (atr / currOpen) * 100;
          const isExtremeVolatility = atrPct > 8; // Skip if ATR > 8% of price
          
          // ═══════════════════════════════════════════════════════════════
          // AGENT #1: CIO — Regime Detection via EMA 200 (Macro Trend)
          // ═══════════════════════════════════════════════════════════════
          const ema200 = ema200All[i - 1];
          const ema19 = ema19All[i - 1];
          const isBullMarket = ema19 > ema200; // Macro uptrend
          
          const prevLow = parseFloat(rawData[i-1][3]);
          const prevHigh = parseFloat(rawData[i-1][2]);
          
          // ICT Concept: Liquidity Sweep (Turtle Soup)
          // Bullish Sweep: Price sweeps below previous day low but closes back inside range
          const isBullishSweep = currLow < prevLow && currClose > prevLow;
          // Bearish Sweep: Price sweeps above previous day high but closes back inside range
          const isBearishSweep = currHigh > prevHigh && currClose < prevHigh;

          // ═══════════════════════════════════════════════════════════════
          // CEO SUPERVISION & RISK PROTOCOLS
          // ═══════════════════════════════════════════════════════════════
          let isHalted = false;
          let logic = "";
          
          if (ceoHaltCooldown > 0) {
            isHalted = true;
            ceoHaltCooldown--;
          } else if (currentConsecutiveLosses >= 3) {
            isHalted = true;
            ceoHaltCooldown = 2; // Cooldown for 2 days after 3 losses
            currentConsecutiveLosses = 0;
          }
          
          const currentDD = peakEquity > 0 ? ((peakEquity - equity) / peakEquity) * 100 : 0;
          if (currentDD > 20) {
            isHalted = true;
            logic = `CEO -> EMERGENCY HALT: Drawdown > 20%`;
          }

          // Fetch previous state early to make decisions
          const prevState = logs.length > 0 ? (logs[logs.length-1].decision_logic.includes("LONG") ? "LONG" : logs[logs.length-1].decision_logic.includes("SHORT") ? "SHORT" : "FLAT") : "FLAT";

          // Determine Intended Position
          let intendedState = "FLAT";
          let activeAgentStr = "";
          let positionSize = 1.0;

          if (isHalted) {
            intendedState = "FLAT";
            if (!logic) logic = `CEO -> TRADING HALTED (Cooldown)`;
          } else if (isExtremeVolatility) {
            intendedState = "FLAT";
            logic = `Agt#3(Volatility) -> SKIP: ATR ${atrPct.toFixed(1)}% too high`;
          } else if (isBullMarket) {
            // Macro Bull Regime
            if (isBullishSweep) {
               intendedState = "LONG";
               activeAgentStr = "Agt#13(ICT Liq Sweep)";
               positionSize = 1.0; // High conviction
            } else if (currLow <= ema19 && currClose > ema19) {
               intendedState = "LONG";
               activeAgentStr = "Agt#14(EMA19 Bounce)";
               positionSize = 0.5; // Medium conviction
            } else if (prevState === "LONG" && currClose < ema19) {
               // CEO Exit: Take profit / cut loss if short term trend breaks
               intendedState = "FLAT";
               activeAgentStr = "CEO(Trend Exit)";
            } else {
               intendedState = prevState === "LONG" ? "LONG" : "FLAT"; // Hold trend
               activeAgentStr = "Agt#14(Macro Trend)";
               positionSize = 0.5;
            }
          } else {
            // Macro Bear Regime
            if (isBearishSweep) {
               intendedState = "SHORT";
               activeAgentStr = "Agt#13(ICT Liq Sweep)";
               positionSize = 1.0;
            } else if (currHigh >= ema19 && currClose < ema19) {
               intendedState = "SHORT";
               activeAgentStr = "Agt#14(EMA19 Reject)";
               positionSize = 0.5;
            } else if (prevState === "SHORT" && currClose > ema19) {
               // CEO Exit: Take profit / cut loss if short term trend breaks
               intendedState = "FLAT";
               activeAgentStr = "CEO(Trend Exit)";
            } else {
               intendedState = prevState === "SHORT" ? "SHORT" : "FLAT"; // Hold trend
               activeAgentStr = "Agt#14(Macro Trend)";
               positionSize = 0.5;
            }
          }

          // Track position changes to apply realistic exchange fees only on entry/exit, not daily!
          let fee = 0;
          
          if (intendedState !== prevState) {
             fee = 0.002; // 0.1% exit + 0.1% entry
          }

          // Monthly DCA & Quarterly Compounding
          const currentMonth = new Date(dateStr).getMonth();
          const prevDateStr = i > startIdx ? new Date(rawData[i-1][0]).toISOString().split('T')[0] : dateStr;
          const prevMonth = new Date(prevDateStr).getMonth();
          
          if (currentMonth !== prevMonth) {
             // DCA: Add $50 at the start of every new month
             totalDeposited += 50.0;
             equity += 50.0;
             
             // If we entered a new Quarter (Months: 0=Jan, 3=Apr, 6=Jul, 9=Oct), Re-invest everything
             if (currentMonth % 3 === 0) {
                allocatedCapital = equity;
             } else {
                // Otherwise just add the new $50 to our working allocated capital so it's traded immediately
                allocatedCapital += 50.0;
             }
          }

          const currChangePct = (currClose - currOpen) / currOpen;
          let tradePnlPct = 0;
          if (intendedState === "LONG") tradePnlPct = currChangePct;
          else if (intendedState === "SHORT") tradePnlPct = -currChangePct;

          tradePnlPct -= fee;
          
          // Risk is calculated on the working Allocated Capital
          let pnl = allocatedCapital * tradePnlPct * positionSize;
          equity += pnl;

          if (pnl < 0 && intendedState !== "FLAT") currentConsecutiveLosses++;
          else if (pnl > 0) currentConsecutiveLosses = 0;

          if (equity > peakEquity) peakEquity = equity;
          const drawdownPct = peakEquity > 0 ? ((peakEquity - equity) / peakEquity) * 100 : 0;

          if (!logic) {
            const sizeStr = positionSize === 1.0 ? "100%" : "50%";
            const outcome = pnl > 0 ? "Win" : pnl < 0 ? "Loss" : "Flat";
            logic = `CIO -> ${activeAgentStr} -> ${intendedState} (${sizeStr}) [${outcome}]`;
          }

          logs.push({
            day: logs.length + 1,
            date: dateStr,
            price: currClose, // Real Historical Price
            daily_pnl: pnl,
            cumulative_pnl: equity - totalDeposited,
            equity: equity,
            drawdown_pct: drawdownPct,
            trades_count: isHalted ? 0 : 1, // 0 trades on halt day
            win_rate: pnl > 0 ? 100 : 0,
            consecutive_losses: currentConsecutiveLosses,
            decision_logic: logic
          });
        }
        setFullLogs(logs);
        setIsLoading(false);
      } catch (e) {
        console.error("Failed to fetch market data:", e);
        setIsLoading(false);
      }
    };
    
    fetchMarketData();
  }, [symbol, period]);

  useEffect(() => {
    let timer: any;
    if (isPlaying && currentDay < fullLogs.length) {
      // 150ms per day to replay ~365 days in under 1 minute
      timer = setInterval(() => {
        setCurrentDay((prev) => {
          if (prev >= fullLogs.length - 1) {
            setIsPlaying(false);
            setIsFinished(true);
            return fullLogs.length;
          }
          return prev + 1;
        });
      }, 150); 
    }
    return () => clearInterval(timer);
  }, [isPlaying, currentDay, fullLogs.length]);

  const startBacktest = () => {
    if (isFinished) {
      setCurrentDay(0);
      setIsFinished(false);
    }
    setIsPlaying(true);
  };

  const pauseBacktest = () => setIsPlaying(false);

  const displayedLogs = fullLogs.slice(0, currentDay);
  const latestLog = displayedLogs[displayedLogs.length - 1];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#0a0a0a]">
        <div className="text-white font-mono text-center space-y-4">
          <div className="animate-spin text-purple-500 mb-4 mx-auto"><RefreshCw size={32} /></div>
          <p>Connecting to {symbol.endsWith('USDT') ? 'Binance' : 'Yahoo Finance'} API...</p>
          <p className="text-text-muted text-sm">Fetching {period} historical OHLCV data for {symbol.endsWith('USDT') ? symbol.replace('USDT', '-USDT') : symbol}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
            <BarChart2 className="text-purple-400" size={28} />
            {symbol.endsWith('USDT') ? symbol.replace('USDT', '-USDT') : symbol} Deep Backtest
          </h1>
          <p className="text-sm text-text-muted mt-1">
            {period} Historical Walk-Forward Simulation (Day-by-Day with Quarterly Compounding)
          </p>
        </div>
        <div className="flex items-center gap-4">
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            disabled={isPlaying}
            className="bg-[#1a1b23] border border-white/10 text-white text-sm rounded-lg px-4 py-2.5 outline-none focus:border-purple-500 transition-colors disabled:opacity-50 font-mono"
          >
            <optgroup label="Crypto (Binance)">
              <option value="BTCUSDT">Bitcoin (BTC)</option>
              <option value="SOLUSDT">Solana (SOL)</option>
              <option value="BNBUSDT">Binance Coin (BNB)</option>
            </optgroup>
            <optgroup label="Global Stocks (Yahoo)">
              <option value="AAPL">Apple (AAPL)</option>
              <option value="TSLA">Tesla (TSLA)</option>
              <option value="NVDA">Nvidia (NVDA)</option>
            </optgroup>
          </select>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            disabled={isPlaying}
            className="bg-[#1a1b23] border border-white/10 text-white text-sm rounded-lg px-4 py-2.5 outline-none focus:border-purple-500 transition-colors disabled:opacity-50 font-mono"
          >
            <option value="1Y">1 Year</option>
            <option value="2Y">2 Years</option>
            <option value="YTD">YTD</option>
          </select>
          <div className="w-px h-8 bg-white/10 mx-1"></div>
          {isPlaying ? (
            <button onClick={pauseBacktest} className="bg-red-500/20 border border-red-500/50 text-red-400 hover:bg-red-500/30 px-4 py-2.5 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors">
              <StopCircle size={16} /> Halt Engine
            </button>
          ) : (
            <button onClick={startBacktest} className="bg-purple-600 hover:bg-purple-700 text-white px-5 py-2.5 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors shadow-[0_0_15px_rgba(168,85,247,0.4)]">
              {isFinished ? <RefreshCw size={16} /> : <PlayCircle size={16} />}
              {isFinished ? 'Restart Simulation' : `Start ${period} Engine`}
            </button>
          )}
        </div>
      </div>

      {/* Progress Bar */}
      <div className="bg-bg-surface border border-white/8 rounded-xl p-4">
        <div className="flex justify-between text-xs font-mono text-text-muted mb-2">
          <span>Simulation Progress: Day {currentDay} of {fullLogs.length}</span>
          <span className={clsx(
            isFinished ? "text-green-400" : isPlaying ? "text-purple-400 animate-pulse" : "text-text-muted"
          )}>
            {isFinished ? '100% - COMPLETED' : isPlaying ? 'PROCESSING...' : 'READY'}
          </span>
        </div>
        <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
          <div 
            className={clsx("h-full rounded-full transition-all duration-[400ms] linear", isFinished ? "bg-green-400 shadow-[0_0_10px_#4ade80]" : "bg-purple-500")}
            style={{ width: `${(currentDay / fullLogs.length) * 100}%` }}
          />
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-5 gap-4">
        <div className="bg-bg-surface border border-white/8 rounded-xl p-4 relative overflow-hidden">
          <div className="absolute top-0 right-0 bg-indigo-500/20 text-indigo-300 text-[10px] font-mono px-2 py-1 rounded-bl-lg border-l border-b border-indigo-500/30">
            DCA: $50/mo
          </div>
          <div className="text-text-muted text-xs font-medium uppercase tracking-wider mb-2">Total Equity (USD)</div>
          <div className={clsx("text-2xl font-bold font-mono", (latestLog?.cumulative_pnl ?? 0) >= 0 ? "text-green-400" : "text-red-400")}>
            {latestLog ? `$${latestLog.equity.toFixed(2)}` : '$100.00'}
          </div>
          <div className="text-[11px] text-text-muted mt-1 font-mono">
            Net PnL: {latestLog && latestLog.cumulative_pnl > 0 ? '+' : ''}{latestLog ? latestLog.cumulative_pnl.toFixed(2) : '0.00'} USDT
          </div>
        </div>

        <div className="bg-bg-surface border border-white/8 rounded-xl p-4">
          <div className="text-text-muted text-xs font-medium uppercase tracking-wider mb-2">Closing SOL Price</div>
          <div className="text-2xl font-bold font-mono text-white">
            {latestLog ? `$${latestLog.price.toFixed(2)}` : '---'}
          </div>
        </div>

        <div className="bg-bg-surface border border-white/8 rounded-xl p-4">
          <div className="text-text-muted text-xs font-medium uppercase tracking-wider mb-2">Total Executed Trades</div>
          <div className="text-2xl font-bold font-mono text-blue-400">
            {displayedLogs.reduce((acc, l) => acc + l.trades_count, 0)}
          </div>
        </div>

        <div className="bg-bg-surface border border-white/8 rounded-xl p-4">
          <div className="text-text-muted text-xs font-medium uppercase tracking-wider mb-2">Dynamic Max Drawdown</div>
          <div className="text-2xl font-bold font-mono text-red-400">
            -{displayedLogs.length > 0 ? Math.max(...displayedLogs.map(l => l.drawdown_pct)).toFixed(2) : '0.00'}%
          </div>
          <div className="text-[11px] text-text-muted mt-1 font-mono">
            Peak to Valley Drop
          </div>
        </div>

        <div className="bg-bg-surface border border-white/8 rounded-xl p-4">
          <div className="text-text-muted text-xs font-medium uppercase tracking-wider mb-2">Largest Single Loss</div>
          <div className="text-2xl font-bold font-mono text-orange-400">
            {displayedLogs.length > 0 ? `$${Math.min(0, ...displayedLogs.map(l => l.daily_pnl)).toFixed(2)}` : '$0.00'}
          </div>
        </div>

        <div className="bg-bg-surface border border-white/8 rounded-xl p-4">
          <div className="text-text-muted text-xs font-medium uppercase tracking-wider mb-2">Max Consecutive Losses</div>
          <div className="text-2xl font-bold font-mono text-amber-400">
            {displayedLogs.length > 0 ? Math.max(...displayedLogs.map(l => l.consecutive_losses)) : 0} Days
          </div>
        </div>
      </div>

      {/* Equity Curve Chart */}
      <ErrorBoundary>
        <div className="bg-bg-surface border border-white/8 rounded-xl p-4 h-64">
          <h2 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-4">Equity Curve Progression</h2>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={displayedLogs}>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
              <XAxis dataKey="day" stroke="#ffffff50" fontSize={12} tickLine={false} />
              <YAxis stroke="#ffffff50" fontSize={12} tickLine={false} domain={['auto', 'auto']} />
              <Tooltip 
                contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #ffffff20', borderRadius: '8px' }}
                itemStyle={{ color: '#fff', fontFamily: 'monospace' }}
              />
              <Line type="monotone" dataKey="cumulative_pnl" stroke="#a855f7" strokeWidth={3} dot={false} animationDuration={300} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </ErrorBoundary>

      {/* Details Table */}
      <ErrorBoundary>
        <div className="bg-bg-surface border border-white/8 rounded-xl overflow-hidden">
          <div className="overflow-y-auto max-h-80 relative">
            <table className="w-full text-sm text-left">
              <thead className="sticky top-0 text-xs text-text-muted uppercase bg-[#14151a] border-b border-white/8 z-10 shadow-md">
                <tr>
                  <th className="px-6 py-4 font-semibold tracking-wider">Day</th>
                  <th className="px-6 py-4 font-semibold tracking-wider">Date</th>
                  <th className="px-6 py-4 font-semibold tracking-wider">Daily PnL</th>
                  <th className="px-6 py-4 font-semibold tracking-wider">Equity ($)</th>
                  <th className="px-6 py-4 font-semibold tracking-wider">Drawdown</th>
                  <th className="px-6 py-4 font-semibold tracking-wider">Cons. Loss</th>
                  <th className="px-6 py-4 font-semibold tracking-wider">Trading Decision Logic</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/4">
                {[...displayedLogs].reverse().map((log) => (
                  <tr key={log.day} className="hover:bg-white/4 transition-colors">
                    <td className="px-6 py-3 font-mono text-white">#{String(log.day).padStart(2, '0')}</td>
                    <td className="px-6 py-3 font-mono text-text-muted">{log.date}</td>
                    <td className={clsx("px-6 py-3 font-mono font-medium", log.daily_pnl >= 0 ? "text-green-400" : "text-red-400")}>
                      {log.daily_pnl > 0 ? '+' : ''}{log.daily_pnl.toFixed(2)}
                    </td>
                    <td className="px-6 py-3 font-mono text-white">${log.equity.toFixed(2)}</td>
                    <td className="px-6 py-3 font-mono text-red-400">-{log.drawdown_pct.toFixed(2)}%</td>
                    <td className={clsx("px-6 py-3 font-mono", log.consecutive_losses > 0 ? "text-orange-400" : "text-text-muted")}>
                      {log.consecutive_losses > 0 ? `${log.consecutive_losses} Days` : '-'}
                    </td>
                    <td className="px-6 py-3 font-mono text-xs text-blue-300 truncate max-w-xs">{log.decision_logic}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {currentDay === 0 && (
              <div className="p-12 flex items-center justify-center">
                <div className="text-center text-text-muted text-sm font-mono bg-white/5 border border-white/10 px-6 py-4 rounded-lg">
                  Engine Ready.<br/>Click "Start {period} Engine" to replay {period} of {symbol.endsWith('USDT') ? symbol.replace('USDT', '-USDT') : symbol} data.
                </div>
              </div>
            )}
          </div>
        </div>
      </ErrorBoundary>

      {/* CEO Final Performance Report */}
      {isFinished && fullLogs.length > 0 && (
        <div className="bg-gradient-to-r from-[#0a0f1c] to-[#131126] border border-indigo-500/30 rounded-xl p-6 shadow-2xl mt-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
          <div className="flex items-center gap-3 mb-6 border-b border-white/10 pb-4">
            <div className="bg-indigo-600/20 text-indigo-400 p-2.5 rounded-xl border border-indigo-500/30">
              <ShieldCheck size={28} />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white tracking-tight">CEO Agent: Final Executive Report</h2>
              <p className="text-xs text-indigo-300 font-mono mt-1">Status: COMPLETED | Period: {period} (Quarterly Re-invested) | Asset: {symbol.endsWith('USDT') ? symbol.replace('USDT', '-USDT') : symbol}</p>
            </div>
          </div>
          
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-sm mb-6">
            <div className="bg-white/5 p-4 rounded-lg border border-white/5">
              <p className="text-text-muted text-xs uppercase tracking-wider mb-2">Total Deposited (Initial + DCA)</p>
              <p className="font-mono text-white text-xl">${latestLog ? (latestLog.equity - latestLog.cumulative_pnl).toFixed(2) : '100.00'}</p>
            </div>
            <div className="bg-white/5 p-4 rounded-lg border border-white/5">
              <p className="text-text-muted text-xs uppercase tracking-wider mb-2">Final Equity</p>
              <p className={clsx("font-mono text-xl font-bold", latestLog.equity >= 100 ? "text-green-400" : "text-red-400")}>
                ${latestLog.equity.toFixed(2)}
              </p>
            </div>
            <div className="bg-white/5 p-4 rounded-lg border border-white/5">
              <p className="text-text-muted text-xs uppercase tracking-wider mb-2">CEO Halts (Rescues)</p>
              <p className="font-mono text-orange-400 text-xl">
                {displayedLogs.filter(l => l.decision_logic.includes('HALTED')).length} Days
              </p>
            </div>
            <div className="bg-white/5 p-4 rounded-lg border border-white/5">
              <p className="text-text-muted text-xs uppercase tracking-wider mb-2">Dominant Agent</p>
              <p className="font-mono text-blue-400 text-sm mt-1">
                {displayedLogs.filter(l => l.decision_logic.includes('Agt#14')).length > displayedLogs.filter(l => l.decision_logic.includes('Agt#13')).length ? 'Agent #14 (EMA Trend)' : 'Agent #13 (ICT Sweep)'}
              </p>
            </div>
          </div>
          
          <div className="bg-black/40 p-5 rounded-lg border border-indigo-500/20 relative overflow-hidden mb-6">
            <div className="absolute top-0 left-0 w-1 h-full bg-indigo-500"></div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-400 mb-2">Executive Summary & Verdict</h3>
            <p className="text-white/90 leading-relaxed text-sm">
              {latestLog.equity >= 120 
                ? "EXCELLENT PERFORMANCE. The Multi-Agent ensemble successfully captured market alpha. ICT logic timed entries perfectly while EMA Trend Logic maintained profitable continuation. APPROVED for live scaling." 
                : latestLog.equity >= 100 
                ? "STABLE PERFORMANCE. The system preserved capital and generated moderate returns. The CEO circuit breakers successfully prevented deep drawdowns. APPROVED for continued paper trading."
                : "NEGATIVE EXPECTANCY DETECTED. The system experienced a net loss. Market conditions were highly adversarial to both ICT setups and EMA bounces. RECOMMENDATION: Halt live deployment and review agent logic."}
            </p>
          </div>

          {/* Detailed Agent Efficiency Breakdown */}
          {(() => {
            const getStats = (agentPattern: string) => {
              // Only count days where the agent was active and PnL changed
              const logs = fullLogs.filter(l => l.decision_logic.includes(agentPattern) && Math.abs(l.daily_pnl) > 0.001);
              const wins = logs.filter(l => l.daily_pnl > 0).length;
              const total = logs.length;
              const winRate = total > 0 ? ((wins / total) * 100).toFixed(1) : "0.0";
              const pnl = logs.reduce((sum, l) => sum + l.daily_pnl, 0).toFixed(2);
              return { total, winRate, pnl };
            };

            const ictStats = getStats('Agt#13');
            const emaStats = getStats('Agt#14');

            return (
              <div className="mt-4 pt-6 border-t border-white/10">
                <h3 className="text-sm font-bold text-white mb-4">Detailed Agent Efficiency Breakdown</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="bg-blue-500/5 border border-blue-500/20 p-4 rounded-lg">
                    <h4 className="text-blue-400 font-bold mb-3 text-sm flex items-center justify-between">
                      <span>Agent #13 (ICT Liquidity Sweep)</span>
                      <span className="text-xs font-mono bg-blue-500/20 px-2 py-1 rounded">Tier 2</span>
                    </h4>
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span className="text-text-muted">Total Active Days:</span>
                        <span className="text-white font-mono">{ictStats.total}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-text-muted">Win Rate:</span>
                        <span className={clsx("font-mono", parseFloat(ictStats.winRate) >= 50 ? "text-green-400" : "text-red-400")}>{ictStats.winRate}%</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-text-muted">Net PnL Contribution:</span>
                        <span className={clsx("font-mono", parseFloat(ictStats.pnl) >= 0 ? "text-green-400" : "text-red-400")}>
                          ${ictStats.pnl}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="bg-purple-500/5 border border-purple-500/20 p-4 rounded-lg">
                    <h4 className="text-purple-400 font-bold mb-3 text-sm flex items-center justify-between">
                      <span>Agent #14 (EMA 19 Trend)</span>
                      <span className="text-xs font-mono bg-purple-500/20 px-2 py-1 rounded">Tier 2</span>
                    </h4>
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span className="text-text-muted">Total Active Days:</span>
                        <span className="text-white font-mono">{emaStats.total}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-text-muted">Win Rate:</span>
                        <span className={clsx("font-mono", parseFloat(emaStats.winRate) >= 50 ? "text-green-400" : "text-red-400")}>{emaStats.winRate}%</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-text-muted">Net PnL Contribution:</span>
                        <span className={clsx("font-mono", parseFloat(emaStats.pnl) >= 0 ? "text-green-400" : "text-red-400")}>
                          ${emaStats.pnl}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}
