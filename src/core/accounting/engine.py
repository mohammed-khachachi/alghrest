"""Pure average-cost spot accounting, with no I/O or binary float arithmetic."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, localcontext

from core.accounting.models import BookState, CashBalance, LedgerPosition, currencies, key, utc
from core.data.models import Fill, FillFee, OrderSide

ZERO = Decimal(0)


def fees(fill: Fill) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    items = (
        fill.fees
        if fill.fees is not None
        else [FillFee(currency=fill.fee_currency, amount=fill.fee)]
    )
    for item in items:
        if not item.currency or not item.amount.is_finite():
            raise ValueError("Fill fee requires a currency and finite amount")
        result[item.currency] = result.get(item.currency, ZERO) + item.amount
    return {currency: amount for currency, amount in result.items() if amount}


def identity(fill: Fill) -> tuple[str, str, str, str]:
    if not fill.exchange_trade_id or not fill.account_id:
        raise ValueError("Fill requires stable exchange_trade_id and account_id")
    currencies(fill.symbol)
    if not fill.fill_size.is_finite() or fill.fill_size <= 0:
        raise ValueError("Fill size must be finite and positive")
    if not fill.fill_price.is_finite() or fill.fill_price <= 0:
        raise ValueError("Fill price must be finite and positive")
    return fill.exchange.value, fill.account_id, fill.symbol, fill.exchange_trade_id


def fingerprint(fill: Fill) -> str:
    """Exclude regenerated internal IDs/attribution; compare exchange economics."""
    identity(fill)

    def number(value: Decimal) -> str:
        result = format(value, "f")
        return result.rstrip("0").rstrip(".") if "." in result else result

    payload = {
        "side": fill.side.value,
        "size": number(fill.fill_size),
        "price": number(fill.fill_price),
        "fees": {currency: number(amount) for currency, amount in sorted(fees(fill).items())},
        "time": utc(fill.timestamp).isoformat(),
        "exchange_order_id": fill.exchange_order_id,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def apply_fill(state: BookState, fill: Fill) -> dict[str, Decimal]:
    """Mutate a private projection; return realized P&L by native currency.

    Base fees reduce net inventory; quote fees enter cost basis/proceeds. Other
    currency fees debit cash and are expensed immediately. Negative fees are rebates.
    """
    identity(fill)
    base, quote = currencies(fill.symbol)
    charges = fees(fill)
    with localcontext() as ctx:
        ctx.prec = 50
        gross = fill.fill_size if fill.side == OrderSide.BUY else -fill.fill_size
        quantity = gross - charges.pop(base, ZERO)
        proceeds = -gross * fill.fill_price - charges.pop(quote, ZERO)
        if quantity * gross <= 0 or quantity * proceeds >= 0:
            raise ValueError("Fees exceed fill consideration or reverse its direction")
        price = -proceeds / quantity
        scope = key(fill.exchange.value, fill.account_id, fill.symbol)
        old = state.positions.get(scope)
        realized = {currency: -amount for currency, amount in charges.items()}
        realized[quote] = ZERO
        cash_changes = {**{c: -v for c, v in charges.items()}, quote: proceeds}
        for currency, amount in cash_changes.items():
            balance = CashBalance(
                exchange=fill.exchange,
                account_id=fill.account_id,
                currency=currency,
                amount=amount,
            )
            if balance.key in state.cash:
                balance.amount += state.cash[balance.key].amount
            state.cash[balance.key] = balance

        if old is None:
            remaining, cost, opened_at = quantity, price, utc(fill.timestamp)
        elif old.quantity * quantity > 0:
            remaining = old.quantity + quantity
            cost = (old.quantity * old.average_cost + quantity * price) / remaining
            opened_at = old.opened_at
        else:
            closed = min(abs(old.quantity), abs(quantity))
            realized[quote] = closed * (price - old.average_cost) * (1 if old.quantity > 0 else -1)
            remaining = old.quantity + quantity
            reversed_side = remaining * old.quantity < 0
            cost = price if reversed_side else old.average_cost
            opened_at = utc(fill.timestamp) if reversed_side else old.opened_at

        if remaining:
            strategy = fill.strategy_id or "external"
            if old and old.strategy_id != strategy:
                strategy = "mixed"
            state.positions[scope] = LedgerPosition(
                exchange=fill.exchange,
                account_id=fill.account_id,
                symbol=fill.symbol,
                quantity=remaining,
                average_cost=cost,
                opened_at=opened_at,
                strategy_id=strategy,
                agent_id=fill.agent_id if strategy != "mixed" else 0,
            )
        else:
            state.positions.pop(scope, None)
        return realized
