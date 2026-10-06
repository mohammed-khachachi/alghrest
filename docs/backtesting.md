# Backtest calculations and validation

`src/backtesting/engine.py` uses the same accounting and metric conventions for
VectorBT and its dependency-free long-only fallback. Neither backend certifies a
strategy merely because its calculations or tests pass.

## Inputs and execution

Inputs require at least two unique, increasing timestamps, finite positive close
prices, and non-null boolean signals with exactly the same index. Initial capital
must be positive; fees and slippage are fractions in `[0, 1)`, and allocation is
in `(0, 1]`.

Both backends enter at `close * (1 + slippage)` and exit at
`close * (1 - slippage)`, charging commission on each side. Allocation includes
the entry fee; unallocated capital stays in cash. Simultaneous entry and exit
signals are ignored. Signals are assumed available at the execution price: the
caller must shift any signal that could only be known after the current close.

An open position at the final timestamp remains marked to market. It contributes
to equity and drawdown but not closed-trade statistics or the Monte Carlo sample.
There is no implicit liquidation at the last bar. The simulator remains long-only
and does not model order-book depth, exchange size filters, or partial fills.

## Time, equity and returns

- Elapsed years are `(last timestamp - first timestamp) / 365.25 days`. Bar count
  does not substitute for elapsed history. Hourly/minute data cannot manufacture
  five years of history by supplying many bars.
- Trades per year use completed trades divided by elapsed years.
- Annualized return is compound growth, `(final / initial) ** (1 / years) - 1`.
- Drawdown uses the entire marked equity path and the initial capital high-water
  mark, including entry costs. Duration runs from the preceding peak through
  recovery or the end of an unrecovered period. Fractional days are preserved.
- Sharpe and Sortino use daily end-of-day equity returns, a zero risk-free rate,
  and 365.25 calendar days. Missing days carry the latest mark forward; this is a
  valuation convention, not evidence of fresh prices. Coarse/sparse input cannot
  reveal risk between observations. Undefined zero-dispersion ratios are reported
  as zero and cannot satisfy the Sharpe eligibility threshold.

Closed-trade return is net PnL divided by committed entry capital **including the
entry fee**. `BacktestResult.trade_returns` stores those observations as fractions:
`0.01` means 1%. Public summary fields ending in `_pct` remain percentages.
Infinite profit factor for profitable trades with no losses survives JSON
round trips as the string `"Infinity"`; unavailable legacy trade samples are `null`.

## Empirical Monte Carlo

Monte Carlo samples the recorded closed-trade returns with replacement. It never
manufactures a normal distribution from win rate or average profit/loss. Its
three-year horizon uses the observed completed-trade rate and the actual elapsed
history, rounded up to a whole number of trades. A fixed seed makes runs
reproducible.

Paths compound returns on committed capital and stop when capital reaches **50%
or less** of the initial value. Ruin is a path event, including exactly 50% loss.
VaR/CVaR report loss fractions floored at zero, so uniformly profitable paths do
not produce negative reported risk. This IID bootstrap does not model serial
dependence, market-regime changes, variable portfolio allocations, or future
monthly contributions.

Missing observations, count mismatches, non-finite observations, returns below
-100%, and invalid elapsed history fail validation with an explicit reason.
Legacy serialized results still load, but need a rerun with recorded trades
before they can pass Monte Carlo. Invalid simulation counts and work beyond the
100-million-draw budget raise a configuration error rather than returning an
approval.

The existing thresholds remain unchanged: five years, 50 trades/year, IS Sharpe
at least 1.0, OOS Sharpe at least 0.8, drawdown below 25%, profit factor at least
1.3, walk-forward efficiency at least 60%, ruin below 1%, and 95% VaR below 15%.

## Regression checks

```powershell
poetry run pytest tests/unit/test_backtest_math.py tests/integration/test_backtesting_validation.py tests/unit/test_model_contracts.py --no-cov -q
poetry run mypy src/agents/ src/core/ src/backtesting/
poetry run python -m scripts.test_with_services --timeout=60 -q
```

The arithmetic tests cover cash and both fees, compounded growth, elapsed calendar
history, intraday drawdown duration, open inventory, all eight timeframes,
backend parity, invalid inputs, empirical distribution support, exact ruin
boundaries, and serialization/replay of the Monte Carlo evidence.
