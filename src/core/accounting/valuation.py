"""Fresh, venue-specific marks and explicit currency conversion for snapshots."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from core.accounting.models import BookState, currencies, utc
from core.data.models import AssetClass, OrderSide, Portfolio, Position


class MissingValuationError(ValueError):
    pass


class Valuation:
    def __init__(self, state: Any, now: datetime, pegs: list[str], max_age: int = 120) -> None:
        self.state = state
        self.now = utc(now)
        self.pegs = {"USD", *pegs}
        self.max_age = max_age
        self._prices: dict[tuple[str, str], Decimal] = {}

    async def mark(self, exchange: str, symbol: str) -> Decimal:
        cache_key = (exchange, symbol)
        if cache_key not in self._prices:
            raw = await self.state.get_json(f"accounting:mark:{exchange}:{symbol}")
            if not raw:
                raise MissingValuationError(f"Missing mark: {exchange} {symbol}")
            value = Decimal(str(raw["price"]))
            age = (self.now - utc(datetime.fromisoformat(raw["timestamp"]))).total_seconds()
            if not value.is_finite() or value <= 0 or not -5 <= age <= self.max_age:
                raise MissingValuationError(f"Invalid/stale mark: {exchange} {symbol}")
            self._prices[cache_key] = value
        return self._prices[cache_key]

    async def usd(self, exchange: str, currency: str) -> Decimal:
        if currency in self.pegs:
            return Decimal(1)
        for quote in sorted(self.pegs):
            try:
                return await self.mark(exchange, f"{currency}/{quote}")
            except MissingValuationError:
                continue
        raise MissingValuationError(f"Missing USD conversion: {exchange} {currency}")

    async def portfolio(self, book_id: str, book: BookState, pnl_rows: list[Any]) -> Portfolio:
        cash = Decimal(0)
        cash_exposure = Decimal(0)
        for balance in book.cash.values():
            if balance.amount:
                value = balance.amount * await self.usd(balance.exchange.value, balance.currency)
                cash += value
                if balance.currency not in self.pegs:
                    cash_exposure += abs(value)
        positions = []
        cost = Decimal(0)
        short_collateral = Decimal(0)
        for scope, position in book.positions.items():
            _, quote = currencies(position.symbol)
            fx = await self.usd(position.exchange.value, quote)
            price = await self.mark(position.exchange.value, position.symbol)
            basis = position.average_cost * fx
            cost += position.quantity * basis
            if position.quantity < 0:
                short_collateral += abs(position.quantity) * max(basis, price * fx) * 2
            positions.append(
                Position(
                    position_id=uuid5(NAMESPACE_URL, f"alghrest:{book_id}:{scope}"),
                    symbol=position.symbol,
                    exchange=position.exchange,
                    account_id=position.account_id,
                    asset_class=AssetClass.CRYPTO,
                    side=OrderSide.BUY if position.quantity > 0 else OrderSide.SELL,
                    size=abs(position.quantity),
                    entry_price=basis,
                    current_price=price * fx,
                    strategy_id=position.strategy_id,
                    agent_id=position.agent_id,
                    opened_at=position.opened_at.replace(tzinfo=None),
                    updated_at=self.now.replace(tzinfo=None),
                )
            )
        daily = weekly = Decimal(0)
        day = self.now.replace(hour=0, minute=0, second=0, microsecond=0)
        week = day - timedelta(days=day.weekday())
        for row in pnl_rows:
            for currency, amount in json.loads(row["realized"]).items():
                if Decimal(amount) == 0:
                    continue
                value = Decimal(amount) * await self.usd(row["exchange"], currency)
                if utc(row["occurred_at"]) >= week:
                    weekly += value
                if utc(row["occurred_at"]) >= day:
                    daily += value
        capital = cash + cost
        return Portfolio(
            snapshot_time=self.now.replace(tzinfo=None),
            total_capital=capital,
            available_capital=max(Decimal(0), cash - short_collateral),
            reserved_capital=sum((p.size * p.entry_price for p in positions), Decimal(0)),
            emergency_reserve=max(capital, Decimal(0)) * Decimal("0.15"),
            daily_pnl=daily,
            weekly_pnl=weekly,
            positions=positions,
            accounting_book_id=book_id,
            accounting_revision=book.revision,
            cash_balances=[b.model_dump(mode="json") for b in book.cash.values()],
            cash_currency_exposure_usd=cash_exposure,
        )
