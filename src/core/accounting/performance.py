"""Performance persistence; callers hold the ledger book lock and transaction."""

from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from typing import Any

from core.accounting.models import BookState, utc
from core.data.models import Portfolio
from core.data.performance import Performance, PeriodReference, period_starts


class PerformanceUnavailableError(ValueError):
    pass


def observe(
    previous: Performance | None, book_id: str, book: BookState, nav: Decimal, now: datetime
) -> Performance:
    now = utc(now)
    if not nav.is_finite():
        raise PerformanceUnavailableError("Non-finite portfolio value")
    starts = period_starts(now)
    if previous is None:
        if book.revision != 0 or nav <= 0:
            raise PerformanceUnavailableError(
                "Traded/empty book requires verified performance history"
            )
        return Performance(
            book_id=book_id,
            revision=book.revision,
            observed_at=now,
            units=nav,
            unit_price=Decimal(1),
            peak=Decimal(1),
            day=PeriodReference(start=starts["day"], unit_price=Decimal(1)),
            week=PeriodReference(start=starts["week"], unit_price=Decimal(1)),
            month=PeriodReference(start=starts["month"], unit_price=Decimal(1)),
            daily_closes={now.date(): Decimal(1)},
        )
    if (
        previous.book_id != book_id
        or previous.revision > book.revision
        or now < previous.observed_at
    ):
        raise PerformanceUnavailableError("Performance book, revision or timestamp mismatch")
    result = previous.model_copy(deep=True)
    with localcontext() as ctx:
        ctx.prec = 50
        result.unit_price = nav / previous.units
    result.peak = max(previous.peak, result.unit_price)
    for name, start in starts.items():
        ref = getattr(previous, name)
        if start != ref.start:
            # Carry the last observed close across a boundary; do not erase a
            # loss first observed after restart/midnight by using the new NAV.
            setattr(
                result,
                name,
                PeriodReference(
                    start=start,
                    unit_price=(
                        max(previous.unit_price, ref.unit_price)
                        if previous.unit_price <= 0
                        else previous.unit_price
                    ),
                ),
            )
    result.observed_at = now
    result.revision = book.revision
    result.daily_closes[now.date()] = result.unit_price
    result.daily_closes = {
        d: p for d, p in result.daily_closes.items() if d >= now.date() - timedelta(days=365)
    }
    return result


async def load(conn: Any, book_id: str) -> Performance | None:
    raw = await conn.fetchval("SELECT state FROM accounting.performance WHERE book_id=$1", book_id)
    return Performance.model_validate_json(raw) if raw else None


async def save(conn: Any, performance: Performance) -> None:
    await conn.execute(
        """INSERT INTO accounting.performance(book_id,state) VALUES($1,$2::jsonb)
        ON CONFLICT(book_id) DO UPDATE SET state=excluded.state,updated_at=now()""",
        performance.book_id,
        performance.model_dump_json(),
    )


async def snapshot(conn: Any, book: BookState, portfolio: Portfolio) -> Performance:
    assert portfolio.accounting_book_id is not None
    result = observe(
        await load(conn, portfolio.accounting_book_id),
        portfolio.accounting_book_id,
        book,
        portfolio.total_capital + portfolio.unrealized_pnl,
        portfolio.snapshot_time,
    )
    await save(conn, result)
    return result


def require_performance(portfolio: Portfolio) -> Performance:
    result = portfolio.performance
    if (
        result is None
        or result.book_id != portfolio.accounting_book_id
        or result.revision != portfolio.accounting_revision
        or result.observed_at != utc(portfolio.snapshot_time)
    ):
        raise PerformanceUnavailableError("Matching durable performance snapshot is required")
    return result
