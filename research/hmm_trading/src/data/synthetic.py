"""Synthetic market data generation."""

import numpy as np
import pandas as pd


def generate_synthetic_data(
    ticker: str = "^GSPC",
    start: str = "2010-01-01",
    end: str = "2024-12-31",
    seed: int = 42,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Generate realistic synthetic OHLCV data using a 3-regime Markov chain.

    Regime 0 — Bullish  Low-Vol  : mu=+0.0005/day, sigma=0.008
    Regime 1 — Bearish  High-Vol : mu=-0.0010/day, sigma=0.020
    Regime 2 — Sideways Med-Vol  : mu=+0.0001/day, sigma=0.010

    Transition matrix is calibrated to produce realistic regime durations.
    Used automatically as fallback when yfinance is unavailable.
    """
    np.random.seed(seed)

    dates = pd.bdate_range(start=start, end=end)
    n = len(dates)

    # Transition matrix (rows = from-state, cols = to-state)
    trans = np.array([
        [0.970, 0.015, 0.015],   # Bullish stays bullish 97% of days
        [0.025, 0.945, 0.030],   # Bearish stays bearish 94.5%
        [0.030, 0.025, 0.945],   # Sideways stays sideways 94.5%
    ])

    regime_params = [
        {"mu":  0.0005, "sigma": 0.008},   # Bullish
        {"mu": -0.0010, "sigma": 0.020},   # Bearish
        {"mu":  0.0001, "sigma": 0.010},   # Sideways
    ]

    # Simulate regime sequence via Markov chain
    regime = 0
    regimes = []
    for _ in range(n):
        regimes.append(regime)
        regime = int(np.random.choice(3, p=trans[regime]))

    regimes = np.array(regimes)

    # Draw daily log-returns per regime
    log_rets = np.array([
        np.random.normal(regime_params[r]["mu"], regime_params[r]["sigma"])
        for r in regimes
    ])

    # Price series starting at 1000
    prices = 1000.0 * np.cumprod(1.0 + log_rets)

    # OHLCV
    noise   = np.abs(np.random.normal(0.004, 0.002, n))
    opens   = prices * np.exp(np.random.normal(0, 0.002, n))
    highs   = prices * (1.0 + noise)
    lows    = prices * (1.0 - noise)
    volumes = np.random.randint(2_000_000, 9_000_000, n).astype(float)

    # Ensure OHLC consistency
    highs = np.maximum(highs, np.maximum(opens, prices))
    lows  = np.minimum(lows,  np.minimum(opens, prices))

    df = pd.DataFrame({
        "open":   opens,
        "high":   highs,
        "low":    lows,
        "close":  prices,
        "volume": volumes,
    }, index=dates)

    if verbose:
        regime_names = ["Bullish", "Bearish", "Sideways"]
        counts = {regime_names[i]: int((regimes == i).sum()) for i in range(3)}
        print(f"[DATA] Synthetic {ticker} data generated ({n:,} trading days).")
        print(f"[DATA] Period : {dates[0].date()} -> {dates[-1].date()}")
        print(f"[DATA] Price  : ${prices.min():.0f} - ${prices.max():.0f}")
        print(f"[DATA] Regimes: {counts}")

    return df
