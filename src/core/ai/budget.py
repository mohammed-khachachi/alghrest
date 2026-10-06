"""Reserve a conservative daily spend estimate before making a paid request.

Plain-text requests only, no tools/thinking. Reserve UTF-8 bytes plus framing as
an input-token upper estimate, cache-write pricing, and the maximum output.
No refunds: failed, cancelled or ambiguous requests still consume the allowance.
Rates need review when models/provider pricing change; provider billing limits
remain authoritative. No external API is contacted by this module.
"""

import asyncio
from decimal import Decimal

import asyncpg

from core.config import settings

# USD/million tokens: worst cache-write rate for the TTL actually used, output.
# https://platform.claude.com/docs/en/about-claude/pricing (reviewed 2026-09-29)
RATES = {
    "claude-opus-4-7": (Decimal("10"), Decimal("25")),
    "claude-sonnet-4-6": (Decimal("3.75"), Decimal("15")),
}


class BudgetUnavailableError(RuntimeError):
    """A request must not be made without a durable reservation."""


def estimate_cost(model: str, system: str, user: str, output_tokens: int) -> Decimal:
    if model not in RATES or output_tokens < 1 or output_tokens > 512:
        raise BudgetUnavailableError("Unsupported model or output allowance")
    size = len(system.encode()) + len(user.encode())
    if size > settings.ai_max_prompt_bytes:
        raise BudgetUnavailableError("Prompt exceeds the bounded input size")
    input_rate, output_rate = RATES[model]
    return ((size + 1024) * input_rate + output_tokens * output_rate) / Decimal(1_000_000)


async def reserve(model: str, system: str, user: str, output_tokens: int) -> None:
    cost = estimate_cost(model, system, user, output_tokens)
    if settings.ai_daily_budget_usd < cost or settings.ai_daily_max_calls == 0:
        raise BudgetUnavailableError("Daily AI allowance exhausted or disabled")
    try:
        async with asyncio.timeout(5):
            connection = await asyncpg.connect(
                settings.database_url.replace("postgresql+asyncpg:", "postgresql:")
            )
            try:
                # The DB's UTC date prevents workers disagreeing about midnight.
                accepted = await connection.fetchval(
                    """INSERT INTO ai.daily_budget(scope, day, calls, reserved_usd)
                       VALUES ($1, (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date, 1, $2)
                       ON CONFLICT(scope, day) DO UPDATE
                       SET calls=ai.daily_budget.calls+1,
                           reserved_usd=ai.daily_budget.reserved_usd+EXCLUDED.reserved_usd
                       WHERE ai.daily_budget.calls < $3
                         AND ai.daily_budget.reserved_usd+EXCLUDED.reserved_usd <= $4
                       RETURNING calls""",
                    settings.environment,
                    cost,
                    settings.ai_daily_max_calls,
                    settings.ai_daily_budget_usd,
                )
                if accepted is None:
                    raise BudgetUnavailableError("Daily AI allowance exhausted")
            finally:
                await connection.close()
    except BudgetUnavailableError:
        raise
    except Exception:
        # Do not leak a DSN, credentials, or a prompt through driver exceptions.
        raise BudgetUnavailableError("Durable AI budget unavailable") from None
