"""Experimental loss-run probes on recorded net outcome signs.

The IID baseline is conditional on an assumed independent loss probability. The
non-circular block bootstrap keeps serial ordering within sampled blocks only.
Neither calculation establishes futures edge, TCP25 fit or strategy approval.
"""

import hashlib
from collections.abc import Iterator, Sequence
from datetime import datetime
from decimal import Decimal, localcontext
from math import isfinite
from typing import Literal, Self, cast

import numpy as np
from numpy.typing import NDArray
from pydantic import Field, StrictInt, model_validator

from core.advisory.selection import Evidence, LosingStreakEstimate
from core.data.models import BacktestResult

Horizon = Literal[10, 25, 50, 100]
LossRun = Literal[2, 3, 4, 5]
HORIZONS: tuple[Horizon, ...] = (10, 25, 50, 100)
LOSS_RUNS: tuple[LossRun, ...] = (2, 3, 4, 5)


def iid_loss_run_probability(probability: Decimal, horizon: int, loss_run: int) -> Decimal:
    """Absorbing-state recurrence: at least k losses anywhere among n trades."""
    if (
        not isinstance(probability, Decimal)
        or not probability.is_finite()
        or not 0 <= probability <= 1
        or isinstance(horizon, bool)
        or not isinstance(horizon, int)
        or isinstance(loss_run, bool)
        or not isinstance(loss_run, int)
        or not 0 <= horizon <= 10000
        or not 1 <= loss_run <= 1000
        or horizon * loss_run > 1000000
    ):
        raise ValueError("Require finite probability, bounded integer horizon and loss run")
    if horizon < loss_run or probability == 0:
        return Decimal(0)
    if probability == 1:
        return Decimal(1)
    with localcontext() as context:
        context.prec = 50
        states = [Decimal(1)] + [Decimal(0)] * (loss_run - 1)
        hit = Decimal(0)
        for _ in range(horizon):
            hit += states[-1] * probability
            states = [sum(states) * (1 - probability)] + [
                value * probability for value in states[:-1]
            ]
        # Preserve the smaller tail: adding nearly all probability mass to
        # `hit` accumulates rounding drift near one, while subtracting survival
        # from one loses genuinely tiny hit probabilities near zero.
        result = hit if hit <= Decimal("0.5") else Decimal(1) - sum(states)
        return min(Decimal(1), max(Decimal(0), result))


class LossStreakConfig(Evidence):
    # Must be chosen and sensitivity-tested; no guessed production default.
    block_length: StrictInt = Field(ge=1, le=10000)
    simulations: StrictInt = Field(ge=1, le=100000)
    seed: StrictInt = Field(ge=0, le=2**64 - 1)


class LongestRunDistribution(Evidence):
    horizon_trades: Literal[10, 25, 50, 100]
    # Index is longest nonpositive run length, including 0 = no losses.
    counts: tuple[StrictInt, ...]

    @model_validator(mode="after")
    def valid_counts(self) -> Self:
        if len(self.counts) != self.horizon_trades + 1 or any(v < 0 for v in self.counts):
            raise ValueError("Longest-run distribution needs one nonnegative count per length")
        return self


def _source_error(source: BacktestResult) -> str | None:
    if not isinstance(source, BacktestResult):
        raise ValueError("Path probe requires a typed backtest record")
    observed = source.trade_returns
    if observed is None:
        return "missing_recorded_net_trade_history"
    if (
        isinstance(source.total_trades, bool)
        or not isinstance(source.total_trades, int)
        or source.total_trades < 0
        or not isinstance(observed, list | tuple)
    ):
        return "invalid_recorded_net_trade_history"
    if source.total_trades == 0 and not observed:
        return "missing_recorded_net_trade_history"
    if len(observed) != source.total_trades or any(
        isinstance(v, bool) or not isinstance(v, int | float) or not isfinite(v) or v < -1
        for v in observed
    ):
        return "invalid_recorded_net_trade_history"
    if len(observed) > 10000:
        return "recorded_trade_history_limit"
    if not isinstance(source.start_date, datetime) or not isinstance(source.end_date, datetime):
        return "invalid_backtest_period"
    try:
        if source.start_date >= source.end_date:
            return "invalid_backtest_period"
    except TypeError:
        return "invalid_backtest_period"
    return None


LossRunTables = tuple[
    Decimal,
    tuple[LosingStreakEstimate, ...],
    tuple[LosingStreakEstimate, ...],
    tuple[LongestRunDistribution, ...],
]


def _block_starts(
    observations: int, horizon: int, config: LossStreakConfig
) -> Iterator[tuple[int, int, NDArray[np.int64]]]:
    """Same non-circular starts and final truncation for signs and paired means."""
    rng = np.random.default_rng(config.seed)
    for offset in range(0, horizon, config.block_length):
        length = min(config.block_length, horizon - offset)
        starts = rng.integers(0, observations - config.block_length + 1, size=config.simulations)
        yield offset, length, starts


def paired_block_bootstrap_means(
    outcomes_r: Sequence[Decimal],
    outcomes_usd: Sequence[Decimal],
    *,
    configuration: LossStreakConfig,
) -> tuple[tuple[Decimal, ...], tuple[Decimal, ...]]:
    """Full-length paired means, not 100-trade extrapolation or account returns.

    Block starts are shared between channels. Prefix sums avoid an observations
    by simulations index matrix; work is bounded to 10 million sampled values.
    Callers decide whether sample size/dependence support an inference.
    """
    config = LossStreakConfig.model_validate(configuration.model_dump(warnings=False))
    if (
        not isinstance(outcomes_r, Sequence)
        or not isinstance(outcomes_usd, Sequence)
        or not 1 <= len(outcomes_r) <= 10000
        or len(outcomes_r) != len(outcomes_usd)
        or any(
            not isinstance(v, Decimal) or not v.is_finite() for v in (*outcomes_r, *outcomes_usd)
        )
    ):
        raise ValueError("Paired bootstrap requires aligned bounded finite Decimal outcomes")
    n = len(outcomes_r)
    if config.block_length > n:
        raise ValueError("Block length exceeds observed paired outcomes")
    if n * config.simulations > 10000000:
        raise ValueError("Paired bootstrap sampled-value work limit exceeded")
    with localcontext() as context:
        context.prec = 80
        prefixes = []
        for values in (outcomes_r, outcomes_usd):
            prefix = [Decimal(0)]
            for value in values:
                prefix.append(prefix[-1] + value)
            prefixes.append(prefix)
        sums = [[Decimal(0)] * config.simulations for _ in range(2)]
        for _, length, starts in _block_starts(n, n, config):
            for sample, raw_start in enumerate(starts):
                start = int(raw_start)
                for channel in range(2):
                    sums[channel][sample] += (
                        prefixes[channel][start + length] - prefixes[channel][start]
                    )
        return tuple(v / n for v in sums[0]), tuple(v / n for v in sums[1])


def recorded_loss_run_tables(
    outcomes: Sequence[Decimal], *, configuration: LossStreakConfig
) -> LossRunTables:
    """Shared sign math; magnitudes may be USD, R or cash returns.

    This does not validate provenance or predict calibrated future probabilities.
    Callers must first verify a complete ordered net outcome history. Unlike the
    cash record adapter, a valid futures loss below -1R is not rejected.
    """
    config = LossStreakConfig.model_validate(configuration.model_dump(warnings=False))
    if (
        not isinstance(outcomes, Sequence)
        or not 1 <= len(outcomes) <= 10000
        or any(not isinstance(v, Decimal) or not v.is_finite() for v in outcomes)
    ):
        raise ValueError("Loss runs require a bounded nonempty finite Decimal outcome sequence")
    if config.block_length > len(outcomes):
        raise ValueError("Block length cannot exceed complete observed trade history")
    losses = np.asarray([value <= 0 for value in outcomes], dtype=np.bool_)
    with localcontext() as context:
        context.prec = 50
        loss_probability = Decimal(int(losses.sum())) / len(losses)
        iid = tuple(
            LosingStreakEstimate(
                horizon_trades=h,
                loss_run=k,
                probability=iid_loss_run_probability(loss_probability, h, k),
            )
            for h in HORIZONS
            for k in LOSS_RUNS
        )
        # At most 10 million booleans; draw block starts without a giant index matrix.
        paths = np.empty((config.simulations, 100), dtype=np.bool_)
        for start, length, starts in _block_starts(len(losses), 100, config):
            for offset in range(length):
                paths[:, start + offset] = losses[starts + offset]
        trailing = np.zeros(config.simulations, dtype=np.int64)
        longest = np.zeros(config.simulations, dtype=np.int64)
        distributions = []
        bootstrap = []
        for index in range(100):
            trailing[:] = np.where(paths[:, index], trailing + 1, 0)
            longest[:] = np.maximum(longest, trailing)
            if index + 1 in HORIZONS:
                horizon = cast(Horizon, index + 1)
                counts = tuple(int(v) for v in np.bincount(longest, minlength=horizon + 1))
                distributions.append(LongestRunDistribution(horizon_trades=horizon, counts=counts))
                for loss_run in LOSS_RUNS:
                    hits = sum(counts[loss_run:])
                    bootstrap.append(
                        LosingStreakEstimate(
                            horizon_trades=horizon,
                            loss_run=loss_run,
                            probability=Decimal(hits) / config.simulations,
                        )
                    )
        return loss_probability, iid, tuple(bootstrap), tuple(distributions)


def _compute(source: BacktestResult, config: LossStreakConfig) -> LossRunTables:
    observed = source.trade_returns
    assert observed is not None
    return recorded_loss_run_tables(tuple(Decimal(str(v)) for v in observed), configuration=config)


class LossStreakStudy(Evidence):
    algorithm_version: Literal["recorded-loss-runs-v1"] = "recorded-loss-runs-v1"
    scope: Literal["experimental_cash_backtest_path_risk"] = "experimental_cash_backtest_path_risk"
    lifecycle: Literal["EXPERIMENT"] = "EXPERIMENT"
    loss_definition: Literal["net_trade_return_lte_zero"] = "net_trade_return_lte_zero"
    bootstrap_method: Literal["non_circular_contiguous_blocks"] = "non_circular_contiguous_blocks"
    source: BacktestResult | None
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    configuration: LossStreakConfig
    state: Literal["CALCULATED", "UNKNOWN"]
    reasons: tuple[str, ...]
    empirical_loss_fraction: Decimal | None
    iid_baseline: tuple[LosingStreakEstimate, ...]
    bootstrap: tuple[LosingStreakEstimate, ...]
    longest_runs: tuple[LongestRunDistribution, ...]
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def reproduce(self) -> Self:
        if self.source is None:
            if (
                self.state != "UNKNOWN"
                or len(self.reasons) != 1
                or self.reasons[0]
                not in {
                    "missing_recorded_net_trade_history",
                    "invalid_recorded_net_trade_history",
                    "recorded_trade_history_limit",
                    "invalid_backtest_period",
                }
                or self.source_sha256 is not None
                or self.empirical_loss_fraction is not None
                or self.iid_baseline
                or self.bootstrap
                or self.longest_runs
            ):
                raise ValueError("Unknown history cannot expose calculated path probabilities")
        else:
            if self.state != "CALCULATED" or self.reasons or _source_error(self.source):
                raise ValueError("Calculated path probe requires complete valid recorded outcomes")
            expected_digest = hashlib.sha256(self.source.model_dump_json().encode()).hexdigest()
            if self.source_sha256 != expected_digest:
                raise ValueError("Path probe source digest must match its captured backtest")
            actual = (
                self.empirical_loss_fraction,
                self.iid_baseline,
                self.bootstrap,
                self.longest_runs,
            )
            if actual != _compute(self.source, self.configuration):
                raise ValueError(
                    "Path probe must reproduce from its source and seeded configuration"
                )
        return self


def loss_streak_analysis(
    source: BacktestResult, *, configuration: LossStreakConfig
) -> LossStreakStudy:
    configuration = LossStreakConfig.model_validate(configuration.model_dump(warnings=False))
    error = _source_error(source)
    if error is not None:
        return LossStreakStudy(
            source=None,
            configuration=configuration,
            state="UNKNOWN",
            reasons=(error,),
            empirical_loss_fraction=None,
            iid_baseline=(),
            bootstrap=(),
            longest_runs=(),
        )
    source = BacktestResult.model_validate_json(source.model_dump_json())
    fraction, iid, bootstrap, distributions = _compute(source, configuration)
    return LossStreakStudy(
        source=source,
        source_sha256=hashlib.sha256(source.model_dump_json().encode()).hexdigest(),
        configuration=configuration,
        state="CALCULATED",
        reasons=(),
        empirical_loss_fraction=fraction,
        iid_baseline=iid,
        bootstrap=bootstrap,
        longest_runs=distributions,
    )
