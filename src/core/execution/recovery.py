"""Resumable recovery orchestration; all recovered fills travel through Kafka."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from core.accounting.models import key
from core.config import settings
from core.data.models import Exchange, KafkaTopic, Order
from core.execution.contracts import TERMINAL, AccountScope, RecoveryBlockedError
from core.execution.store import ExecutionStore


class RecoveryCoordinator:
    def __init__(
        self,
        store: ExecutionStore,
        accounts: list[AccountScope],
        venues: dict[str, Any],
        state: Any,
        publish: Any,
        *,
        page_budget: int = 30,
        ttl: int = 30,
        overlap_ms: int = 86400000,
        full_scan_ms: int = 86400000,
        tolerances: dict[str, Decimal] | None = None,
        order_lock: asyncio.Lock | None = None,
    ) -> None:
        self.store, self.accounts, self.venues = store, accounts, venues
        self.state, self.publish = state, publish
        self.page_budget, self.ttl = page_budget, ttl
        self.overlap_ms, self.full_scan_ms = overlap_ms, full_scan_ms
        self.tolerances = tolerances or {}
        self.order_lock = order_lock or asyncio.Lock()

    async def flush(self, *, allow_new_risk: bool = False) -> None:
        settings.require_order_execution()
        for event in await self.store.outbox(include_execution_intents=allow_new_risk):
            await self.publish(
                KafkaTopic(event["topic"]),
                payload=json.loads(event["payload"]),
                message_type=event["message_type"],
            )
            # A crash before this mark resends; the ledger's identity is permanent.
            await self.store.delivered(event["id"])

    async def _ensure_writer(self) -> None:
        ensure = getattr(self.store, "ensure_writer", None)
        if callable(ensure):
            await ensure()
            return
        await self.store.check_writer()

    async def recover_orders(self, halted: bool) -> list[str]:
        settings.require_order_execution()
        async with self.order_lock:
            await self._ensure_writer()
            return await self._recover_orders(halted)

    async def _recover_orders(self, halted: bool) -> list[str]:
        settings.require_order_execution()
        issues = []
        for row in await self.store.orders():
            order = Order.model_validate_json(row["current_order"])
            venue = self.venues[key(order.exchange.value, order.account_id)]
            try:
                found = await venue.lookup(order)
                if found is None:
                    issues.append(f"unresolved submission {order.client_order_id}")
                    continue
                observed = await self.store.observe(order, found)
                if (halted or row["cancel_requested"]) and observed.status not in TERMINAL:
                    await self.store.request_cancel(observed)
                    await venue.cancel(observed)
            except Exception as exc:
                issues.append(f"order recovery {order.client_order_id}: {type(exc).__name__}")
        return issues

    async def history(self, account: AccountScope, symbol: str, target_ms: int) -> bool:
        async with self.store.ledger.locked_state() as (_, _state, opening):
            opening_ms = int(opening.as_of.timestamp() * 1000)
        for _ in range(self.page_budget):
            saved = await self.store.checkpoint(account, symbol)
            cursor = saved["cursor"]
            if cursor is None:
                full = (
                    not saved["through_ms"]
                    or target_ms - saved["last_full_ms"] >= self.full_scan_ms
                )
                start = (
                    opening_ms if full else max(opening_ms, saved["through_ms"] - self.overlap_ms)
                )
                cursor = {
                    "start": start,
                    "end": min(start + 86399999, target_ms),
                    "target": target_ms,
                    "page": None,
                    "full": full,
                }
            page = await self.venues[account.key].history_page(
                symbol, cursor["start"], cursor["end"], cursor["page"]
            )
            if page.cursor is not None:
                token_hash = hashlib.sha256(
                    json.dumps(page.cursor, sort_keys=True).encode()
                ).hexdigest()
                seen = cursor.get("seen", [])
                if page.cursor == cursor["page"] or token_hash in seen:
                    raise RecoveryBlockedError("History cursor repeated")
                following = {**cursor, "page": page.cursor, "seen": [*seen, token_hash]}
                through = saved["through_ms"]
            elif cursor["end"] < cursor["target"]:
                start = cursor["end"] + 1
                following = {
                    **cursor,
                    "start": start,
                    "end": min(start + 86399999, cursor["target"]),
                    "page": None,
                    "seen": [],
                }
                through = saved["through_ms"]
            else:
                following = None
                through = cursor["target"]
            await self.store.capture_page(
                account,
                symbol,
                saved["version"],
                following,
                through,
                page.fills,
                cursor["target"] if following is None and cursor["full"] else None,
            )
            if following is None:
                return True
        return False  # checkpoint persists; next pass resumes this exact page

    async def run_once(self) -> dict[str, Any]:
        settings.require_order_execution()
        await self._ensure_writer()
        await self.store.block("reconciliation in progress")
        await self.state.set_reconciliation(
            {"book_id": self.store.book_id, "ready": False}, self.ttl
        )
        issues = await self.recover_orders(await self.state.is_kill_switch_active())
        balances = {}
        target_ms = int(datetime.now(UTC).timestamp() * 1000)
        for account in self.accounts:
            venue = self.venues[account.key]
            try:
                if hasattr(venue, "maintain_protection"):
                    await venue.maintain_protection()
                before = await venue.balances()
                for symbol in ["*"] if account.exchange == Exchange.KRAKEN else account.symbols:
                    if not await self.history(account, symbol, target_ms):
                        issues.append(f"history page budget: {account.key} {symbol}")
                for opened in await venue.open_orders():
                    if not (
                        hasattr(venue, "verify_protection")
                        and await venue.verify_protection(opened)
                    ):
                        issues.append(f"open exchange orders: {account.key}")
                after = await venue.balances()
                # Native zero entries may appear/disappear without a movement.
                if {c: v for c, v in before.items() if v} != {c: v for c, v in after.items() if v}:
                    issues.append(f"balance changed during reconciliation: {account.key}")
                balances[account.key] = after
            except Exception as exc:
                issues.append(f"account recovery {account.key}: {type(exc).__name__}")
        await self.flush()
        report = await self.store.verify(self.accounts, balances, issues, self.tolerances, self.ttl)
        await self.state.set_reconciliation(report, self.ttl)
        # Fills/statuses must flow even when blocked. New execution instructions
        # wait for both authoritative and shared readiness, otherwise the
        # executor correctly rejects a child during this reconciliation pass.
        if report["ready"]:
            await self.flush(allow_new_risk=True)
        return report
