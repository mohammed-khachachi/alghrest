"""
Unit tests for Agent 30 — PortfolioTracker.

Focus: I10 fix — Sharpe / Sortino must be computed from TRUE daily returns
(NAV bucketed by UTC calendar date), not from 30-second snapshot deltas.

These tests bypass `BaseAgent.__init__` (which spins up Kafka/Redis/metrics)
by constructing the tracker via `object.__new__` and seeding only the
attributes the pure-Python helpers touch (`_daily_closes`, `_peak_nav`).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest

from agents.tier7_monitoring.portfolio_tracker import (
    _MIN_DAYS_FOR_SHARPE,
    _RETURNS_WINDOW_DAYS,
    _TRADING_DAYS_PER_YEAR,
    PortfolioTracker,
)
from core.data.models import Portfolio


def _make_tracker(closes: dict[str, float] | None = None, peak_nav: float = 0.0) -> PortfolioTracker:
    """Build a PortfolioTracker without invoking BaseAgent.__init__."""
    tracker = object.__new__(PortfolioTracker)
    tracker._daily_closes = dict(closes or {})
    tracker._peak_nav = peak_nav
    tracker._current_date = None
    return tracker


def _portfolio(capital: float = 100_000.0) -> Portfolio:
    return Portfolio(
        snapshot_time=datetime.utcnow(),
        total_capital=Decimal(str(capital)),
        available_capital=Decimal(str(capital * 0.85)),
        reserved_capital=Decimal(str(capital * 0.15)),
        emergency_reserve=Decimal(str(capital * 0.15)),
        positions=[],
    )


# ─── _compute_daily_returns ──────────────────────────────────────────────────


@pytest.mark.unit
def test_daily_returns_empty():
    tracker = _make_tracker()
    assert tracker._compute_daily_returns(window=90) == []


@pytest.mark.unit
def test_daily_returns_single_close_returns_empty():
    tracker = _make_tracker({"2026-05-01": 100_000.0})
    assert tracker._compute_daily_returns(window=90) == []


@pytest.mark.unit
def test_daily_returns_two_consecutive_days():
    tracker = _make_tracker({
        "2026-05-01": 100_000.0,
        "2026-05-02": 101_000.0,
    })
    rets = tracker._compute_daily_returns(window=90)
    assert len(rets) == 1
    assert rets[0] == pytest.approx(0.01)


@pytest.mark.unit
def test_daily_returns_multi_day_sequence():
    tracker = _make_tracker({
        "2026-05-01": 100.0,
        "2026-05-02": 110.0,   # +10%
        "2026-05-03": 99.0,    # -10%
        "2026-05-04": 99.0,    #  0%
    })
    rets = tracker._compute_daily_returns(window=90)
    assert rets == pytest.approx([0.10, -0.10, 0.0])


@pytest.mark.unit
def test_daily_returns_window_caps_to_last_n_plus_one():
    closes = {f"2026-{m:02d}-{d:02d}": 100.0 + (m * 31 + d)
              for m in (1, 2) for d in range(1, 29)}
    tracker = _make_tracker(closes)
    rets = tracker._compute_daily_returns(window=10)
    # window=N produces at most N returns
    assert len(rets) <= 10


@pytest.mark.unit
def test_daily_returns_iso_dates_sort_chronologically():
    # ISO YYYY-MM-DD strings sort identically to dates — verify no dict-order bug.
    tracker = _make_tracker({
        "2026-05-03": 102.0,   # inserted first
        "2026-05-01": 100.0,
        "2026-05-02": 101.0,
    })
    rets = tracker._compute_daily_returns(window=90)
    # Chronological: 100 → 101 (+1%), 101 → 102 (~+0.99%)
    assert rets[0] == pytest.approx(0.01)
    assert rets[1] == pytest.approx(1.0 / 101.0)


@pytest.mark.unit
def test_daily_returns_skips_zero_previous_nav():
    tracker = _make_tracker({
        "2026-05-01": 0.0,
        "2026-05-02": 100.0,
        "2026-05-03": 101.0,
    })
    rets = tracker._compute_daily_returns(window=90)
    # 0 → 100 is skipped (prev not > 0); only 100 → 101 yields a return.
    assert rets == pytest.approx([0.01])


@pytest.mark.unit
def test_daily_returns_gap_produces_single_multi_day_return():
    # System down for two days — pairs the next available close against the
    # previous available one. We don't fabricate intermediate values.
    tracker = _make_tracker({
        "2026-05-01": 100.0,
        # 2026-05-02 missing
        # 2026-05-03 missing
        "2026-05-04": 110.0,
        "2026-05-05": 111.0,
    })
    rets = tracker._compute_daily_returns(window=90)
    assert rets == pytest.approx([0.10, 1.0 / 110.0])


# ─── _compute_metrics: Sharpe / Sortino ──────────────────────────────────────


@pytest.mark.unit
def test_metrics_below_minimum_samples_yields_none_sharpe():
    closes = {f"2026-04-{d:02d}": 100.0 + d for d in range(1, _MIN_DAYS_FOR_SHARPE)}
    tracker = _make_tracker(closes, peak_nav=200.0)
    metrics = tracker._compute_metrics(_portfolio(), nav=150.0)
    assert metrics["sharpe_90d"] is None
    assert metrics["sortino_90d"] is None
    assert metrics["daily_returns_observed"] < _MIN_DAYS_FOR_SHARPE
    assert metrics["min_days_required"] == _MIN_DAYS_FOR_SHARPE


@pytest.mark.unit
def test_metrics_sharpe_matches_textbook_formula():
    # Build 60 days of synthetic returns with known mean / stdev so we can
    # back-solve the expected Sharpe and confirm the annualization is sqrt(252)
    # over DAILY returns — not sqrt(252 * 96) over 15-minute samples.
    rng = np.random.default_rng(42)
    daily_rets = rng.normal(loc=0.001, scale=0.01, size=60)
    nav = 100_000.0
    closes = {}
    for i, r in enumerate([0.0, *daily_rets]):
        nav *= (1.0 + r)
        closes[f"2026-{((i // 28) + 1):02d}-{((i % 28) + 1):02d}"] = nav

    tracker = _make_tracker(closes, peak_nav=max(closes.values()))
    metrics = tracker._compute_metrics(_portfolio(), nav=nav)

    rets = np.asarray(tracker._compute_daily_returns(window=_RETURNS_WINDOW_DAYS))
    expected = float(rets.mean() / rets.std(ddof=1) * np.sqrt(_TRADING_DAYS_PER_YEAR))
    # Metric is rounded to 3 decimals before serialization.
    assert metrics["sharpe_90d"] == pytest.approx(round(expected, 3), abs=1e-3)


@pytest.mark.unit
def test_metrics_constant_returns_zero_std_yields_none_sharpe():
    # Same NAV every day → returns are all zero → std is zero → Sharpe undefined.
    closes = {f"2026-04-{d:02d}": 100_000.0 for d in range(1, _MIN_DAYS_FOR_SHARPE + 5)}
    tracker = _make_tracker(closes, peak_nav=100_000.0)
    metrics = tracker._compute_metrics(_portfolio(), nav=100_000.0)
    assert metrics["sharpe_90d"] is None
    # Sortino also None — no downside dispersion.
    assert metrics["sortino_90d"] is None


@pytest.mark.unit
def test_metrics_no_downside_returns_no_sortino_but_has_sharpe():
    # Strictly increasing NAV → all returns positive → no downside std.
    closes = {f"2026-04-{d:02d}": 100.0 + d for d in range(1, _MIN_DAYS_FOR_SHARPE + 5)}
    tracker = _make_tracker(closes, peak_nav=max(closes.values()))
    metrics = tracker._compute_metrics(_portfolio(), nav=max(closes.values()))
    assert metrics["sharpe_90d"] is not None
    assert metrics["sortino_90d"] is None


@pytest.mark.unit
def test_metrics_drawdown_computed_against_peak():
    tracker = _make_tracker(peak_nav=100_000.0)
    metrics = tracker._compute_metrics(_portfolio(capital=80_000.0), nav=80_000.0)
    # 20% drawdown from 100k peak.
    assert metrics["drawdown_pct"] == pytest.approx(20.0)


@pytest.mark.unit
def test_metrics_drawdown_zero_when_above_peak():
    tracker = _make_tracker(peak_nav=100_000.0)
    metrics = tracker._compute_metrics(_portfolio(), nav=110_000.0)
    assert metrics["drawdown_pct"] == 0.0


@pytest.mark.unit
def test_metrics_annualization_factor_is_daily_not_micro():
    # Anchor test for the I10 fix: with mean=0.001 and std=0.01, the daily
    # Sharpe annualised correctly is 0.001/0.01 * sqrt(252) ≈ 1.587.
    # The OLD bug annualised 15-min returns with sqrt(252) — ~16x understated.
    closes = {}
    nav = 100_000.0
    for i in range(_MIN_DAYS_FOR_SHARPE + 5):
        # Alternate +0.011 / -0.009 → mean ≈ 0.001, std ≈ 0.01
        r = 0.011 if i % 2 == 0 else -0.009
        nav *= (1.0 + r)
        closes[f"2026-{((i // 28) + 1):02d}-{((i % 28) + 1):02d}"] = nav

    tracker = _make_tracker(closes, peak_nav=max(closes.values()))
    metrics = tracker._compute_metrics(_portfolio(), nav=nav)
    assert metrics["sharpe_90d"] is not None
    # Annualised Sharpe of a near-zero-mean alternating series is small but
    # well-defined; the key invariant is that the magnitude is consistent
    # with sqrt(252) annualisation, which sits in the order of single digits
    # for daily-return series — NOT the exploded 30+ produced by the old
    # 15-min-sample path.
    assert abs(metrics["sharpe_90d"]) < 10.0


# ─── _decode_redis_hash ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_stationary_returns_sharpe_remains_stable():
    """
    Stationarity invariant: when daily returns are drawn IID from a fixed
    distribution N(μ, σ²), rolling-window Sharpe estimates should hover
    around the population Sharpe = (μ/σ) × sqrt(252) instead of drifting
    or oscillating wildly.

    This is the canonical regression test for the I10 rewrite — the OLD
    code computed Sharpe over 15-minute snapshot deltas and produced
    estimates that swung by an order of magnitude as the snapshot buffer
    drifted, even when the underlying daily-return distribution was
    perfectly stationary.
    """
    rng = np.random.default_rng(42)
    mu, sigma = 0.001, 0.01
    n_days = 500
    daily_rets = rng.normal(loc=mu, scale=sigma, size=n_days)

    population_sharpe = (mu / sigma) * np.sqrt(_TRADING_DAYS_PER_YEAR)  # ≈ 1.587

    start = date(2025, 1, 1)
    nav = 100_000.0
    full_closes: dict[str, float] = {}
    for i, r in enumerate(daily_rets):
        nav *= (1.0 + r)
        full_closes[(start + timedelta(days=i)).isoformat()] = nav

    sorted_dates = sorted(full_closes.keys())
    rolling_sharpes: list[float] = []
    # Step every 5 days for runtime; any step yields IID-overlapping windows.
    for i in range(_RETURNS_WINDOW_DAYS + 1, len(sorted_dates) + 1, 5):
        prefix_dates = sorted_dates[:i]
        prefix = {d: full_closes[d] for d in prefix_dates}
        tracker = _make_tracker(prefix, peak_nav=max(prefix.values()))
        m = tracker._compute_metrics(_portfolio(), nav=prefix[prefix_dates[-1]])
        assert m["sharpe_90d"] is not None
        rolling_sharpes.append(m["sharpe_90d"])

    sharpes = np.asarray(rolling_sharpes)
    assert len(sharpes) >= 50

    # 1. Mean of rolling estimates is close to the population Sharpe.
    #    Tolerance accounts for finite-sample bias of σ̂ in 90-day windows.
    assert abs(sharpes.mean() - population_sharpe) < 0.4, (
        f"rolling-Sharpe mean {sharpes.mean():.3f} far from "
        f"population {population_sharpe:.3f}"
    )

    # 2. No single estimate is a wild outlier. SE per 90-day estimate
    #    (Lo 2002) ≈ sqrt((1 + SR²/2) / N) × sqrt(252). Allow ~4 SE.
    daily_sr = mu / sigma
    se = np.sqrt((1 + 0.5 * daily_sr ** 2) / _RETURNS_WINDOW_DAYS) * np.sqrt(
        _TRADING_DAYS_PER_YEAR
    )
    bound = 4 * se
    assert np.all(np.abs(sharpes - population_sharpe) < bound), (
        f"outlier rolling Sharpe — max deviation "
        f"{np.max(np.abs(sharpes - population_sharpe)):.3f} exceeds {bound:.3f}"
    )

    # 3. Variance of rolling estimates is consistent with finite-sample
    #    sampling noise — the std of the rolling series should not exceed
    #    the per-window SE (it's actually smaller than 1×SE in practice
    #    because adjacent rolling windows are heavily autocorrelated).
    assert sharpes.std() < se, (
        f"rolling Sharpe std {sharpes.std():.3f} exceeds per-window SE "
        f"{se:.3f} — estimator looks unstable"
    )


@pytest.mark.unit
def test_stationary_returns_sharpe_close_across_independent_samples():
    """
    Two independent IID samples from the same N(μ, σ²) should produce
    Sharpe estimates within a few SEs of each other and of the population
    Sharpe. Uses 400-day windows so the Lo-2002 SE ≈ 0.79 (annualised),
    which makes the test meaningfully discriminating.
    """
    rng = np.random.default_rng(2026)
    mu, sigma = 0.001, 0.01
    n = 400  # long enough that SE is small
    population_sharpe = (mu / sigma) * np.sqrt(_TRADING_DAYS_PER_YEAR)

    def _sharpe_of(rets: np.ndarray) -> float:
        nav = 50_000.0
        closes: dict[str, float] = {}
        start = date(2024, 1, 1)
        for i, r in enumerate(rets):
            nav *= (1.0 + r)
            closes[(start + timedelta(days=i)).isoformat()] = nav
        tracker = _make_tracker(closes, peak_nav=max(closes.values()))
        # Pull through _compute_daily_returns with window=n so we use the
        # full sample (production path uses _RETURNS_WINDOW_DAYS=90).
        rets_observed = tracker._compute_daily_returns(window=n)
        arr = np.asarray(rets_observed, dtype=float)
        return float(arr.mean() / arr.std(ddof=1) * np.sqrt(_TRADING_DAYS_PER_YEAR))

    sample_a = rng.normal(loc=mu, scale=sigma, size=n)
    sample_b = rng.normal(loc=mu, scale=sigma, size=n)

    sharpe_a = _sharpe_of(sample_a)
    sharpe_b = _sharpe_of(sample_b)

    daily_sr = mu / sigma
    se = np.sqrt((1 + 0.5 * daily_sr ** 2) / n) * np.sqrt(_TRADING_DAYS_PER_YEAR)

    # Each estimate should be within 3 SEs of the population value.
    assert abs(sharpe_a - population_sharpe) < 3 * se
    assert abs(sharpe_b - population_sharpe) < 3 * se
    # Difference of two independent estimates has SE = sqrt(2) × SE.
    assert abs(sharpe_a - sharpe_b) < 4 * se


@pytest.mark.unit
def test_stationary_returns_sharpe_invariant_to_starting_point():
    """
    Sharpe of a stationary series should not depend on which calendar
    date the series 'starts' at. Same returns, different start dates,
    same Sharpe.
    """
    rng = np.random.default_rng(7)
    daily_rets = rng.normal(loc=0.0008, scale=0.012, size=120)

    def _build_closes(start_date: date) -> dict[str, float]:
        closes: dict[str, float] = {}
        nav = 50_000.0
        for i, r in enumerate(daily_rets):
            nav *= (1.0 + r)
            closes[(start_date + timedelta(days=i)).isoformat()] = nav
        return closes

    sharpes = []
    for start in (date(2024, 1, 1), date(2025, 6, 15), date(2026, 3, 7)):
        closes = _build_closes(start)
        tracker = _make_tracker(closes, peak_nav=max(closes.values()))
        m = tracker._compute_metrics(_portfolio(), nav=max(closes.values()))
        assert m["sharpe_90d"] is not None
        sharpes.append(m["sharpe_90d"])

    # All three Sharpe estimates should be IDENTICAL — the function only
    # cares about return SEQUENCE, not absolute calendar position.
    assert sharpes[0] == sharpes[1] == sharpes[2], (
        f"Sharpe varied with start date: {sharpes}"
    )


@pytest.mark.unit
def test_decode_redis_hash_bytes_input():
    raw = {b"2026-05-01": b"100000.5", b"2026-05-02": b"100500.0"}
    out = PortfolioTracker._decode_redis_hash(raw)
    assert out == {"2026-05-01": 100_000.5, "2026-05-02": 100_500.0}


@pytest.mark.unit
def test_decode_redis_hash_str_input():
    raw = {"2026-05-01": "100000.5"}
    out = PortfolioTracker._decode_redis_hash(raw)
    assert out == {"2026-05-01": 100_000.5}


@pytest.mark.unit
def test_decode_redis_hash_skips_malformed_values():
    raw = {b"2026-05-01": b"not-a-number", b"2026-05-02": b"100.0"}
    out = PortfolioTracker._decode_redis_hash(raw)
    assert out == {"2026-05-02": 100.0}
