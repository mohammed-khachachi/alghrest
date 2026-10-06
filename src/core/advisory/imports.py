"""Explicit broker/chart CSV import; exact instrument, contract and UTC timestamps."""

import csv
import io
from datetime import UTC, datetime, timedelta

from pydantic import Field, HttpUrl

from core.advisory.models import INTERVAL_SECONDS, Candle, Interval, MarketSnapshot, Strict, utcnow


class CSVImport(Strict):
    instrument_id: str
    interval: Interval
    source: HttpUrl
    contract: str | None = Field(default=None, max_length=40)
    csv: str = Field(min_length=1, max_length=400000)

    def market(self) -> MarketSnapshot:
        reader = csv.DictReader(io.StringIO(self.csv))
        if reader.fieldnames is None or not {
            "time",
            "open",
            "high",
            "low",
            "close",
            "volume",
        } <= set(reader.fieldnames):
            raise ValueError("CSV columns must include time,open,high,low,close,volume")
        candles: list[Candle] = []
        now = utcnow()
        for row in reader:
            if len(candles) >= 500:
                raise ValueError("Import at most 500 candles at a time")
            raw = row.get("time")
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("Each row needs a timestamp")
            timestamp = (
                datetime.fromtimestamp(float(raw), UTC)
                if raw.replace(".", "", 1).isdigit()
                else datetime.fromisoformat(raw.replace("Z", "+00:00"))
            )
            if timestamp.tzinfo is None:
                raise ValueError("CSV time needs an explicit UTC offset")
            candle = Candle.model_validate(
                {
                    "open_time": timestamp,
                    "close_time": timestamp
                    + timedelta(seconds=INTERVAL_SECONDS[self.interval], milliseconds=-1),
                    **{
                        field: row.get(field)
                        for field in ("open", "high", "low", "close", "volume")
                    },
                }
            )
            if candle.close_time > now:
                raise ValueError("Remove unfinished or future candles before importing")
            candles.append(candle)
        return MarketSnapshot(
            instrument_id=self.instrument_id,
            interval=self.interval,
            source=self.source,
            contract=self.contract,
            fetched_at=now,
            candles=candles,
            data_mode="user_import",
        )
