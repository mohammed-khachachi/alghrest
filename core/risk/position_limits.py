"""
ALGHREST — Position Limit Enforcer
Checks ALL hard risk limits before any trade proposal can be approved.
The CRO agent calls check_proposal() — rejection is silent-fast, no exceptions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

import structlog

from core.data.models import Portfolio, TradeProposal, RISK_LIMITS

logger = structlog.get_logger(__name__)

_ASSET_CLASS_TO_SECTOR = {
    "BTC": "crypto_large_cap",
    "ETH": "crypto_large_cap",
    "BNB": "crypto_exchange",
    "SOL": "crypto_alt_l1",
    "AVAX": "crypto_alt_l1",
    "MATIC": "crypto_alt_l1",
    "LINK": "crypto_defi",
    "UNI": "crypto_defi",
    "AAVE": "crypto_defi",
    "SPY": "equity_index",
    "QQQ": "equity_index",
    "GLD": "commodity",
    "EURUSD": "forex_major",
    "GBPUSD": "forex_major",
    "USDJPY": "forex_major",
}


@dataclass
class LimitCheckResult:
    approved: bool
    rejections: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    adjusted_size_usd: Optional[Decimal] = None


class PositionLimitChecker:
    """
    Enforces all hard position limits from RISK_LIMITS.
    Called before EVERY trade proposal is approved.
    """

    def check_proposal(
        self,
        proposal: TradeProposal,
        portfolio: Portfolio,
        open_proposals_count: int = 0,
    ) -> LimitCheckResult:
        """
        Run ALL limit checks on a trade proposal.
        Returns LimitCheckResult with approved=False and reasons if any limit breached.
        """
        rejections: list[str] = []
        warnings: list[str] = []
        adjusted_size = proposal.size_usd

        total_cap = float(portfolio.total_capital)
        if total_cap <= 0:
            return LimitCheckResult(False, ["Portfolio capital is zero"])

        # ── 1. SIZE — Max risk per trade ─────────────────────────────────────
        if proposal.stop_loss and proposal.limit_price:
            stop_distance = abs(float(proposal.limit_price - proposal.stop_loss))
            entry = float(proposal.limit_price)
            if entry > 0:
                risk_pct = stop_distance / entry * float(proposal.size_usd) / total_cap
                if risk_pct > RISK_LIMITS.max_risk_per_trade:
                    max_size = (
                        RISK_LIMITS.max_risk_per_trade
                        * total_cap
                        * entry
                        / stop_distance
                    )
                    adjusted_size = Decimal(str(round(max_size, 2)))
                    warnings.append(
                        f"Size reduced: risk {risk_pct:.2%} > {RISK_LIMITS.max_risk_per_trade:.0%} limit "
                        f"(adjusted to ${adjusted_size:,.0f})"
                    )

        # ── 2. SINGLE ASSET concentration ────────────────────────────────────
        current_exposure = sum(
            float(p.size * p.current_price)
            for p in portfolio.positions
            if p.symbol == proposal.symbol
        )
        proposed_total = (current_exposure + float(adjusted_size)) / total_cap
        if proposed_total > RISK_LIMITS.max_single_asset:
            max_additional = max(
                0.0,
                RISK_LIMITS.max_single_asset * total_cap - current_exposure,
            )
            if max_additional < 10:  # Less than $10 available — reject outright
                rejections.append(
                    f"Single-asset limit: {proposal.symbol} already at "
                    f"{current_exposure / total_cap:.1%} of capital (limit: {RISK_LIMITS.max_single_asset:.0%})"
                )
            else:
                adjusted_size = Decimal(str(round(max_additional, 2)))
                warnings.append(
                    f"Size reduced for asset concentration ({proposal.symbol}: "
                    f"{proposed_total:.1%} > {RISK_LIMITS.max_single_asset:.0%})"
                )

        # ── 3. SECTOR concentration ───────────────────────────────────────────
        base_symbol = proposal.symbol.split("/")[0].split("USDT")[0].split("USD")[0]
        sector = _ASSET_CLASS_TO_SECTOR.get(base_symbol, f"crypto_{proposal.asset_class.lower()}")

        sector_exposure = sum(
            float(p.size * p.current_price)
            for p in portfolio.positions
            if _ASSET_CLASS_TO_SECTOR.get(
                p.symbol.split("/")[0], "unknown"
            ) == sector
        )
        sector_pct = (sector_exposure + float(adjusted_size)) / total_cap
        if sector_pct > RISK_LIMITS.max_single_sector:
            max_sector = max(0.0, RISK_LIMITS.max_single_sector * total_cap - sector_exposure)
            if max_sector < 10:
                rejections.append(
                    f"Sector limit breached: {sector} at {sector_exposure / total_cap:.1%} "
                    f"(limit: {RISK_LIMITS.max_single_sector:.0%})"
                )
            else:
                adjusted_size = min(adjusted_size, Decimal(str(round(max_sector, 2))))
                warnings.append(f"Size reduced for sector concentration ({sector})")

        # ── 4. LEVERAGE ────────────────────────────────────────────────────────
        current_exposure_total = float(portfolio.total_exposure_usd)
        new_leverage = (current_exposure_total + float(adjusted_size)) / total_cap
        if new_leverage > RISK_LIMITS.max_leverage:
            max_additional_for_leverage = max(
                0.0,
                RISK_LIMITS.max_leverage * total_cap - current_exposure_total,
            )
            if max_additional_for_leverage < 10:
                rejections.append(
                    f"Leverage limit: would reach {new_leverage:.1f}x (max: {RISK_LIMITS.max_leverage}x)"
                )
            else:
                adjusted_size = min(
                    adjusted_size, Decimal(str(round(max_additional_for_leverage, 2)))
                )
                warnings.append(f"Size reduced for leverage ({new_leverage:.1f}x -> {RISK_LIMITS.max_leverage}x)")

        # ── 5. EMERGENCY RESERVE ──────────────────────────────────────────────
        available_non_reserve = float(portfolio.available_capital) - float(portfolio.emergency_reserve)
        if float(adjusted_size) > available_non_reserve:
            if available_non_reserve < 10:
                rejections.append(
                    f"Insufficient capital: ${available_non_reserve:,.0f} available "
                    f"(emergency reserve protected)"
                )
            else:
                adjusted_size = Decimal(str(round(max(0.0, available_non_reserve), 2)))
                warnings.append("Size reduced to protect emergency reserve")

        if rejections:
            logger.info(
                "proposal rejected",
                proposal_id=str(proposal.proposal_id),
                symbol=proposal.symbol,
                reasons=rejections,
            )
            return LimitCheckResult(
                approved=False, rejections=rejections, warnings=warnings
            )

        return LimitCheckResult(
            approved=True,
            warnings=warnings,
            adjusted_size_usd=adjusted_size if adjusted_size != proposal.size_usd else None,
        )
