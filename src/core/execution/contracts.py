from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.accounting.models import BookState, currencies, key
from core.data.models import Exchange, Fill, OrderStatus

TERMINAL = {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED}


class RecoveryBlockedError(RuntimeError):
    pass


class OrderConflictError(ValueError):
    pass


class AccountScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exchange: Exchange
    account_id: str = Field(default="default", min_length=1)
    symbols: list[str] = Field(min_length=1)

    @field_validator("symbols")
    @classmethod
    def spot_symbols(cls, value: list[str]) -> list[str]:
        for symbol in value:
            currencies(symbol)
        if len(value) != len(set(value)):
            raise ValueError("Duplicate recovery market")
        return sorted(value)

    @property
    def key(self) -> str:
        return key(self.exchange.value, self.account_id)


@dataclass
class TradePage:
    fills: list[Fill]
    cursor: dict[str, Any] | None


def native_balances(book: BookState) -> dict[str, dict[str, Decimal]]:
    """Physical spot inventory: quote/fee cash plus signed base positions."""
    with localcontext() as ctx:
        ctx.prec = 50
        result: dict[str, dict[str, Decimal]] = {}
        for cash in book.cash.values():
            account = result.setdefault(key(cash.exchange.value, cash.account_id), {})
            account[cash.currency] = account.get(cash.currency, Decimal(0)) + cash.amount
        for position in book.positions.values():
            account = result.setdefault(key(position.exchange.value, position.account_id), {})
            base, _ = currencies(position.symbol)
            account[base] = account.get(base, Decimal(0)) + position.quantity
        return result


def balance_differences(
    expected: dict[str, Decimal],
    actual: dict[str, Decimal],
    tolerances: dict[str, Decimal],
) -> dict[str, dict[str, str]]:
    with localcontext() as ctx:
        ctx.prec = 50
        differences = {}
        for currency in sorted(expected.keys() | actual.keys()):
            wanted, found = expected.get(currency, Decimal(0)), actual.get(currency, Decimal(0))
            tolerance = tolerances.get(currency, Decimal(0))
            if (
                not wanted.is_finite()
                or not found.is_finite()
                or tolerance < 0
                or not tolerance.is_finite()
            ):
                raise ValueError("Balances/tolerances must be finite and tolerances nonnegative")
            if abs(found - wanted) > tolerance:
                differences[currency] = {
                    "expected": str(wanted),
                    "actual": str(found),
                    "delta": str(found - wanted),
                }
        return differences
