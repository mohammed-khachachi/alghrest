"""Explicit opening state and decimal-only ledger projections."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.data.models import Exchange

Money = Annotated[Decimal, Field(allow_inf_nan=False)]
PositiveMoney = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]


def utc(value: datetime) -> datetime:
    # Existing event contracts use naive UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def key(*parts: str) -> str:
    return json.dumps(parts, separators=(",", ":"))


def currencies(symbol: str) -> tuple[str, str]:
    parts = symbol.split("/")
    if len(parts) != 2 or not all(parts) or ":" in symbol or parts[0] == parts[1]:
        raise ValueError("Accounting requires a spot BASE/QUOTE symbol")
    return parts[0], parts[1]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CashBalance(StrictModel):
    exchange: Exchange
    account_id: str = Field(default="default", min_length=1)
    currency: str = Field(min_length=1, pattern=r"^[A-Z0-9]+$")
    amount: Money

    @property
    def key(self) -> str:
        return key(self.exchange.value, self.account_id, self.currency)


class LedgerPosition(StrictModel):
    exchange: Exchange
    account_id: str = Field(default="default", min_length=1)
    symbol: str
    quantity: Money  # signed; negative inventory is retained, never clamped away
    average_cost: PositiveMoney  # quote currency per net base unit, including fees
    opened_at: datetime
    strategy_id: str = "external"
    agent_id: int = 0

    @field_validator("symbol")
    @classmethod
    def spot_symbol(cls, value: str) -> str:
        currencies(value)
        return value

    @field_validator("opened_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return utc(value)

    @property
    def key(self) -> str:
        return key(self.exchange.value, self.account_id, self.symbol)


class OpeningBalances(StrictModel):
    """Balances after all exchange activity at or before as_of (inclusive)."""

    as_of: datetime
    reference: str = Field(min_length=1)  # reconciliation/export reference
    cash: list[CashBalance]
    positions: list[LedgerPosition] = Field(default_factory=list)

    @field_validator("as_of")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Opening cutoff must include a timezone")
        return utc(value)

    @model_validator(mode="after")
    def unique_balances(self) -> Self:
        if len({item.key for item in self.cash}) != len(self.cash):
            raise ValueError("Duplicate opening cash balance")
        if len({item.key for item in self.positions}) != len(self.positions):
            raise ValueError("Duplicate opening position")
        if any(p.quantity == 0 or p.opened_at > self.as_of for p in self.positions):
            raise ValueError("Opening positions must be nonzero and precede the cutoff")
        return self


class BookState(StrictModel):
    revision: int = 0
    cash: dict[str, CashBalance] = Field(default_factory=dict)
    positions: dict[str, LedgerPosition] = Field(default_factory=dict)

    @classmethod
    def from_opening(cls, opening: OpeningBalances) -> BookState:
        return cls(
            cash={p.key: p.model_copy(deep=True) for p in opening.cash},
            positions={p.key: p.model_copy(deep=True) for p in opening.positions},
        )
