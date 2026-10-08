"""
data_loader.py
==============
Responsible for loading financial market data.

Primary  : yfinance (live download)
Fallback : generate_synthetic_data() — realistic 3-regime Markov simulation
           used automatically when yfinance is unavailable (offline/sandbox).

In the HMM framework:
  - Each trading day  = one observation timestep  o_t
  - The full history  = observation sequence  O = {o_1, ..., o_T}
  - HMM discovers the hidden regime q_t behind each o_t
"""

import pandas as pd
from typing import Optional

from src.data.synthetic import generate_synthetic_data

try:
    import yfinance as yf
    _YFINANCE_AVAILABLE = True
except ImportError:
    _YFINANCE_AVAILABLE = False

SUPPORTED_TICKERS = {
    "^GSPC":   "S&P 500 Index",
    "SPY":     "SPDR S&P 500 ETF",
    "AAPL":    "Apple Inc.",
    "BTC-USD": "Bitcoin USD",
    "QQQ":     "Invesco QQQ (Nasdaq-100)",
    "GLD":     "SPDR Gold Shares",
}


# ─────────────────────────────────────────────────────────────────────
# 1.  Live download via yfinance
# ─────────────────────────────────────────────────────────────────────

def download_data(
    ticker: str = "^GSPC",
    start: str = "2010-01-01",
    end: str = "2024-12-31",
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Download OHLCV data from Yahoo Finance.
    Raises ValueError if the download returns nothing.
    """
    if not _YFINANCE_AVAILABLE:
        raise ImportError("yfinance is not installed.")

    label = SUPPORTED_TICKERS.get(ticker, ticker)
    if verbose:
        print(f"[DATA] Downloading {label} ({ticker}): {start} -> {end}")

    raw = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)

    if raw is None or raw.empty:
        raise ValueError(f"No data returned for ticker '{ticker}'.")

    # Flatten MultiIndex columns (yfinance >= 0.2)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    raw.columns = [c.lower() for c in raw.columns]

    required = ["open", "high", "low", "close", "volume"]
    for col in required:
        if col not in raw.columns:
            raise ValueError(f"Missing column '{col}' in downloaded data.")

    df = raw[required].copy().sort_index().ffill().bfill().dropna()
    df["volume"] = df["volume"].clip(lower=0)

    if verbose:
        print(f"[DATA] Loaded {len(df):,} trading days "
              f"({df.index[0].date()} -> {df.index[-1].date()})")
        print(f"[DATA] Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")

    return df


# ─────────────────────────────────────────────────────────────────────
# 3.  Public interface  (tries live, falls back to synthetic)
# ─────────────────────────────────────────────────────────────────────

def load_data(
    ticker: str = "^GSPC",
    start: str = "2010-01-01",
    end: str = "2024-12-31",
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Load market data.  Tries yfinance first; on any failure uses synthetic data.
    This ensures the full pipeline runs even in offline / sandboxed environments.
    """
    try:
        return download_data(ticker=ticker, start=start, end=end, verbose=verbose)
    except Exception as exc:
        if verbose:
            print(f"[DATA] yfinance unavailable ({exc.__class__.__name__}: {exc})")
            print("[DATA] Falling back to synthetic Markov-regime data.")
        return generate_synthetic_data(
            ticker=ticker, start=start, end=end, verbose=verbose
        )
