"""Market data loading utilities."""

from __future__ import annotations

from datetime import date
import pandas as pd
import yfinance as yf


def load_market_data(
    ticker: str = "^GSPC",
    start: str = "2015-01-01",
    end: str | None = None,
) -> pd.DataFrame:
    """Download and clean daily OHLCV market data from Yahoo Finance."""

    end_date = end or date.today().isoformat()
    data = yf.download(
        ticker,
        start=start,
        end=end_date,
        auto_adjust=True,
        progress=False,
        threads=False,
    )

    if data.empty:
        raise ValueError(f"No market data returned for ticker {ticker!r}.")

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    data = data.rename(columns={column: column.lower().replace(" ", "_") for column in data.columns})
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Downloaded data is missing required columns: {sorted(missing)}")

    data = data.loc[:, ["open", "high", "low", "close", "volume"]].copy()
    data.index = pd.to_datetime(data.index)
    data = data.sort_index()
    data = data.replace([float("inf"), float("-inf")], pd.NA).dropna()
    if len(data) < 300:
        raise ValueError("Not enough observations. Use a wider date range.")
    return data
