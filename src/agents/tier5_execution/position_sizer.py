"""
Position Sizer — Quarter Kelly criterion with volatility targeting.

Computes safe position sizes from signal conviction + current portfolio risk.
All Tier 4 strategy agents call this before creating a TradeProposal.

The result conforms to PositionSizingResult (core.data.models) and includes
the full audit trail of which constraints were binding.
"""

from __future__ import annotations

import math
from decimal import Decimal

import structlog

from core.data.models import RISK_LIMITS, PositionSizingResult, RiskLimits, VolatilityRegime

log = structlog.get_logger(__name__)

_KELLY_FRACTION = 0.25  # quarter Kelly
_MIN_SIZE_USD = Decimal("10")  # ignore dust
_VOL_TARGET_ANN = 0.15  # 15% annualised portfolio vol target
_TRADING_DAYS = 252


class PositionSizer:
    """
    Stateless position sizing calculator.

    Usage:
        sizer = PositionSizer(portfolio_value_usd=Decimal("100000"))
        result = sizer.size(
            symbol="BTC/USDT",
            strategy_id="trend_follower_donchian",
            entry_price=Decimal("45000"),
            stop_loss=Decimal("44000"),
            win_rate=0.55,
            avg_win=0.02,
            avg_loss=0.01,
            symbol_daily_vol=0.025,
            current_leverage=1.2,
        )
    """

    def __init__(
        self,
        portfolio_value_usd: Decimal,
        risk_limits: RiskLimits = RISK_LIMITS,
    ) -> None:
        self.portfolio_value = Decimal(str(portfolio_value_usd))
        self.limits = risk_limits

    # ─── Public ──────────────────────────────────────────────────────────────

    def size(
        self,
        symbol: str,
        strategy_id: str,
        entry_price: Decimal,
        stop_loss: Decimal,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        symbol_daily_vol: float,
        current_leverage: float,
        signal_strength: float = 1.0,
        vol_regime: VolatilityRegime = VolatilityRegime.NORMAL,
        existing_position_usd: float = 0.0,
    ) -> PositionSizingResult:
        """Return PositionSizingResult with full audit trail."""
        constraints: list[str] = []
        entry_price = Decimal(str(entry_price))
        stop_loss = Decimal(str(stop_loss))

        # Step 1: Full Kelly + Quarter Kelly
        kelly_raw = self._kelly(win_rate, avg_win, avg_loss)
        full_kelly_usd = Decimal(str(kelly_raw)) * self.portfolio_value
        quarter_kelly_pct = kelly_raw * _KELLY_FRACTION
        quarter_kelly_usd = Decimal(str(quarter_kelly_pct)) * self.portfolio_value

        # Step 2: Volatility scaling
        vol_scalar = self._vol_scalar(symbol_daily_vol, vol_regime)
        vol_adjusted_pct = quarter_kelly_pct * vol_scalar * max(0.1, min(1.0, signal_strength))
        vol_adjusted_usd = Decimal(str(vol_adjusted_pct)) * self.portfolio_value
        if vol_scalar < 1.0:
            constraints.append(f"vol_regime={vol_regime.value}_scalar={vol_scalar:.2f}")

        # Step 3: Per-trade risk cap (by stop distance)
        max_risk_usd = Decimal(str(self.limits.max_risk_per_trade)) * self.portfolio_value
        stop_distance = abs(entry_price - stop_loss)
        if stop_distance > 0 and entry_price > 0:
            max_size_by_risk = max_risk_usd * entry_price / stop_distance
            if vol_adjusted_usd > max_size_by_risk:
                vol_adjusted_usd = max_size_by_risk
                constraints.append(
                    f"capped_by_max_risk_per_trade={self.limits.max_risk_per_trade:.1%}"
                )

        # Step 4: Single asset cap
        max_single_usd = Decimal(str(self.limits.max_single_asset)) * self.portfolio_value
        if vol_adjusted_usd > max_single_usd:
            vol_adjusted_usd = max_single_usd
            constraints.append(f"capped_by_max_single_asset={self.limits.max_single_asset:.1%}")

        # Step 5: Leverage headroom
        capped_by_leverage = self._leverage_cap(
            vol_adjusted_usd, current_leverage, existing_position_usd
        )
        if capped_by_leverage < vol_adjusted_usd:
            constraints.append(f"capped_by_leverage_headroom_max={self.limits.max_leverage}x")
        final_usd = capped_by_leverage

        # Step 6: Min floor
        if final_usd < _MIN_SIZE_USD:
            final_usd = Decimal("0")
            constraints.append("below_minimum_size")

        # Step 7: Risk amount + units
        final_units = final_usd / entry_price if entry_price > 0 else Decimal("0")
        risk_amount = stop_distance * final_units
        risk_pct = float(risk_amount / self.portfolio_value) if self.portfolio_value > 0 else 0.0

        log.debug(
            "position_sizer.result",
            symbol=symbol,
            final_usd=float(final_usd),
            kelly_raw=round(kelly_raw, 4),
            vol_scalar=round(vol_scalar, 4),
            constraints=constraints,
        )

        return PositionSizingResult(
            symbol=symbol,
            strategy_id=strategy_id,
            entry_price=entry_price,
            stop_loss=stop_loss,
            total_capital=self.portfolio_value,
            kelly_fraction_raw=float(kelly_raw),
            kelly_size_usd=full_kelly_usd.quantize(Decimal("0.01")),
            quarter_kelly_size_usd=quarter_kelly_usd.quantize(Decimal("0.01")),
            vol_adjusted_size_usd=Decimal(str(vol_adjusted_usd)).quantize(Decimal("0.01")),
            final_size_usd=final_usd.quantize(Decimal("0.01")),
            final_size_units=final_units.quantize(Decimal("0.00000001")),
            risk_amount_usd=risk_amount.quantize(Decimal("0.01")),
            risk_pct_of_capital=risk_pct,
            constraints_applied=constraints,
        )

    # ─── Vol-targeted sizing (alternative method) ─────────────────────────────

    def vol_target_size(
        self,
        symbol: str,
        strategy_id: str,
        entry_price: Decimal,
        stop_loss: Decimal,
        symbol_daily_vol: float,
        current_leverage: float = 1.0,
    ) -> PositionSizingResult:
        """Size to hit _VOL_TARGET_ANN portfolio volatility."""
        entry_price = Decimal(str(entry_price))
        stop_loss = Decimal(str(stop_loss))

        if symbol_daily_vol <= 0 or entry_price <= 0:
            return self._zero_result(
                symbol, strategy_id, entry_price, stop_loss, ["zero_vol_or_price"]
            )

        ann_vol = symbol_daily_vol * math.sqrt(_TRADING_DAYS)
        target_size_pct = min(_VOL_TARGET_ANN / ann_vol, float(self.limits.max_single_asset))
        size_usd = Decimal(str(target_size_pct)) * self.portfolio_value
        size_usd = self._leverage_cap(size_usd, current_leverage, 0.0)

        units = size_usd / entry_price
        stop_distance = abs(entry_price - stop_loss)
        risk_amount = stop_distance * units

        return PositionSizingResult(
            symbol=symbol,
            strategy_id=strategy_id,
            entry_price=entry_price,
            stop_loss=stop_loss,
            total_capital=self.portfolio_value,
            kelly_fraction_raw=0.0,
            kelly_size_usd=Decimal("0"),
            quarter_kelly_size_usd=Decimal("0"),
            vol_adjusted_size_usd=size_usd.quantize(Decimal("0.01")),
            final_size_usd=size_usd.quantize(Decimal("0.01")),
            final_size_units=units.quantize(Decimal("0.00000001")),
            risk_amount_usd=risk_amount.quantize(Decimal("0.01")),
            risk_pct_of_capital=(
                float(risk_amount / self.portfolio_value) if self.portfolio_value > 0 else 0.0
            ),
            constraints_applied=["vol_targeted"],
        )

    # ─── Internals ────────────────────────────────────────────────────────────

    def _zero_result(
        self,
        symbol: str,
        strategy_id: str,
        entry_price: Decimal,
        stop_loss: Decimal,
        constraints: list[str],
    ) -> PositionSizingResult:
        return PositionSizingResult(
            symbol=symbol,
            strategy_id=strategy_id,
            entry_price=entry_price,
            stop_loss=stop_loss,
            total_capital=self.portfolio_value,
            kelly_fraction_raw=0.0,
            kelly_size_usd=Decimal("0"),
            quarter_kelly_size_usd=Decimal("0"),
            vol_adjusted_size_usd=Decimal("0"),
            final_size_usd=Decimal("0"),
            final_size_units=Decimal("0"),
            risk_amount_usd=Decimal("0"),
            risk_pct_of_capital=0.0,
            constraints_applied=constraints,
        )

    @staticmethod
    def _kelly(win_rate: float, avg_win: float, avg_loss: float) -> float:
        """Full Kelly fraction. Clamped to [0, 1]."""
        if avg_win <= 0 or avg_loss <= 0:
            return 0.0
        p = max(0.0, min(1.0, win_rate))
        q = 1.0 - p
        ratio = avg_win / avg_loss
        kelly = (p * ratio - q) / ratio
        return max(0.0, min(1.0, kelly))

    @staticmethod
    def _vol_scalar(daily_vol: float, regime: VolatilityRegime) -> float:
        """Scale down position in volatile regimes."""
        regime_scalars = {
            VolatilityRegime.CALM: 1.0,
            VolatilityRegime.NORMAL: 1.0,
            VolatilityRegime.VOLATILE: 0.6,
            VolatilityRegime.CRISIS: 0.25,
        }
        base_scalar = regime_scalars.get(regime, 1.0)
        if daily_vol > 0.05:
            base_scalar *= 0.5
        elif daily_vol > 0.03:
            base_scalar *= 0.75
        return base_scalar

    def _leverage_cap(
        self,
        proposed_usd: Decimal,
        current_leverage: float,
        existing_position_usd: float,
    ) -> Decimal:
        """Ensure adding this position won't breach max leverage."""
        max_total_exposure = self.portfolio_value * Decimal(str(self.limits.max_leverage))
        current_exposure = Decimal(str(current_leverage)) * self.portfolio_value
        remaining = max_total_exposure - current_exposure - Decimal(str(existing_position_usd))
        remaining = max(Decimal("0"), remaining)
        return min(proposed_usd, remaining)
