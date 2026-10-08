"""Typed, durable performance index. Cash contributions never constitute returns."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Finite = Annotated[Decimal, Field(allow_inf_nan=False)]
Positive = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]


class PeriodReference(BaseModel):
    start: date
    unit_price: Positive


class Performance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    book_id: str
    revision: int = Field(ge=0)
    observed_at: AwareDatetime
    units: Positive
    unit_price: Finite
    peak: Positive
    day: PeriodReference
    week: PeriodReference
    month: PeriodReference
    daily_closes: dict[date, Finite] = Field(default_factory=dict)

    def drawdown(self, reference: Decimal | None = None) -> float:
        baseline = self.peak if reference is None else reference
        return max(0.0, float((baseline - self.unit_price) / baseline))

    def daily_returns(self, window: int = 90) -> list[float]:
        # Today's running observation is not a completed daily close. Gaps
        # cannot be treated as single-day samples or filled with invented prices.
        end = self.observed_at.date()
        dates = sorted(d for d in self.daily_closes if end - timedelta(days=window + 1) <= d < end)
        return [
            float(self.daily_closes[b] / self.daily_closes[a] - 1)
            for a, b in pairwise(dates)
            if b - a == timedelta(days=1) and self.daily_closes[a] > 0
        ]


def period_starts(now: datetime) -> dict[str, date]:
    day = now.date()
    return {"day": day, "week": day - timedelta(days=day.weekday()), "month": day.replace(day=1)}
