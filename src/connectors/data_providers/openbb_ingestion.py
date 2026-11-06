"""OpenBB data ingestion pipeline for TimescaleDB, Kafka, and Redis.

Bridges normalized `OHLCVBar` records from `OpenBBAdapter` into Alghrest's
existing storage and messaging primitives:
- TimescaleDB hypertable `market_data.ohlcv_bars` (idempotent batch upsert)
- Kafka topic `prices.realtime` (`AgentMessage` with `message_type="ohlcv"`)
- Redis ticker cache `prices:{symbol}` and historical bar cache
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import asyncpg
import structlog

from connectors.data_providers.base import AssetClass as ProviderAssetClass
from connectors.data_providers.openbb_adapter import OpenBBAdapter
from core.config import Settings, settings as default_settings
from core.data.models import AgentMessage, Exchange, KafkaTopic, OHLCVBar, Timeframe
from core.orchestrator.message_bus import AlghrestProducer
from core.orchestrator.state_manager import StateManager
from core.resilience import DatabaseCircuitBreaker, ExponentialBackoffPolicy

logger = structlog.get_logger(__name__)

_UPSERT_OHLCV_SQL = """
INSERT INTO market_data.ohlcv_bars (
    time, symbol, exchange, timeframe, open, high, low, close,
    volume, quote_volume, trade_count, vwap, is_closed
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
)
ON CONFLICT (time, symbol, exchange, timeframe) DO UPDATE SET
    open = EXCLUDED.open,
    high = EXCLUDED.high,
    low = EXCLUDED.low,
    close = EXCLUDED.close,
    volume = EXCLUDED.volume,
    quote_volume = EXCLUDED.quote_volume,
    trade_count = EXCLUDED.trade_count,
    vwap = EXCLUDED.vwap,
    is_closed = EXCLUDED.is_closed
"""

_SELECT_OHLCV_SQL = """
SELECT time, symbol, exchange, timeframe, open, high, low, close,
       volume, quote_volume, trade_count, vwap, is_closed
FROM market_data.ohlcv_bars
WHERE symbol = $1 AND timeframe = $2 AND exchange = $3
ORDER BY time DESC
LIMIT $4
"""

_REDIS_PRICE_KEY_FMT = "prices:{symbol}"
_REDIS_PRICE_TTL = 60
_REDIS_HISTORY_KEY_FMT = "openbb:history:{asset_class}:{symbol}:{timeframe}:{provider}"


@dataclass(frozen=True, slots=True)
class IngestionSummary:
    """Result summary of an OpenBB ingestion pipeline run."""

    symbol: str
    provider: str
    timeframe: str
    bars_fetched: int
    db_rows_upserted: int
    kafka_messages_published: int
    redis_cached: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class OpenBBIngestionPipeline:
    """Ingests normalized OpenBB market data into TimescaleDB, Kafka, and Redis."""

    def __init__(
        self,
        *,
        adapter: OpenBBAdapter | None = None,
        config: Settings | None = None,
        db_pool: asyncpg.Pool | None = None,
        producer: AlghrestProducer | None = None,
        state: StateManager | None = None,
        circuit_breaker: DatabaseCircuitBreaker | None = None,
        source_agent_id: int = 5,
    ) -> None:
        self._settings = config or default_settings
        self._adapter = adapter or OpenBBAdapter(config=self._settings)
        self._db_pool = db_pool
        self._owns_pool = False
        self._producer = producer
        self._state = state
        self._breaker = circuit_breaker or DatabaseCircuitBreaker(name="openbb_timescaledb")
        self._backoff = ExponentialBackoffPolicy(base_delay=0.2, max_delay=2.0, max_attempts=3)
        self._source_agent_id = source_agent_id

    @property
    def adapter(self) -> OpenBBAdapter:
        return self._adapter

    async def _get_pool(self) -> asyncpg.Pool:
        if self._db_pool is not None:
            return self._db_pool
        if not self._settings.database_url:
            raise RuntimeError("DATABASE_URL is not configured for OpenBBIngestionPipeline")
        dsn = self._settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        self._db_pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,
            max_size=4,
            command_timeout=15.0,
        )
        self._owns_pool = True
        return self._db_pool

    async def close(self) -> None:
        if self._owns_pool and self._db_pool is not None:
            await self._db_pool.close()
            self._db_pool = None
            self._owns_pool = False

    async def persist_bars_to_timescaledb(self, bars: Sequence[OHLCVBar]) -> int:
        """Idempotently upsert normalized `OHLCVBar` records into `market_data.ohlcv_bars`."""
        if not bars:
            return 0
        pool = await self._get_pool()
        records = [
            (
                _ensure_utc(bar.time),
                bar.symbol,
                bar.exchange.value,
                bar.timeframe.value,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.quote_volume,
                bar.trade_count,
                bar.vwap,
                bar.is_closed,
            )
            for bar in bars
        ]

        async def _write_batch() -> int:
            async with pool.acquire() as conn, conn.transaction():
                await conn.executemany(_UPSERT_OHLCV_SQL, records)
            return len(records)

        count = await self._backoff.run(
            _write_batch,
            circuit_breaker=self._breaker,
        )
        logger.info(
            "openbb.timescaledb_upserted",
            symbol=bars[0].symbol,
            timeframe=bars[0].timeframe.value,
            rows=count,
        )
        return count

    async def read_bars_from_timescaledb(
        self,
        symbol: str,
        *,
        timeframe: Timeframe = Timeframe.D1,
        exchange: Exchange = Exchange.OPENBB,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        """Read persisted OHLCV bars for a symbol from TimescaleDB in chronological order."""
        pool = await self._get_pool()

        async def _query() -> list[Any]:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    _SELECT_OHLCV_SQL,
                    symbol.strip().upper(),
                    timeframe.value,
                    exchange.value,
                    max(1, min(limit, 5000)),
                )
                return list(rows)

        rows = await self._backoff.run(
            _query,
            circuit_breaker=self._breaker,
        )
        bars = [
            OHLCVBar(
                time=_ensure_utc(row["time"]),
                symbol=row["symbol"],
                exchange=Exchange(row["exchange"]),
                timeframe=Timeframe(row["timeframe"]),
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"] or 0)),
                quote_volume=Decimal(str(row["quote_volume"] or 0)),
                trade_count=int(row["trade_count"] or 0),
                vwap=Decimal(str(row["vwap"])) if row["vwap"] is not None else None,
                is_closed=bool(row["is_closed"]),
            )
            for row in reversed(rows)
        ]
        return bars

    async def publish_bars_to_kafka(self, bars: Sequence[OHLCVBar]) -> int:
        """Publish normalized `OHLCVBar` events to `KafkaTopic.PRICES_REALTIME`."""
        if not bars or self._producer is None:
            return 0
        published = 0
        for bar in bars:
            msg = AgentMessage(
                source_agent_id=self._source_agent_id,
                topic=KafkaTopic.PRICES_REALTIME,
                message_type="ohlcv",
                payload=bar.model_dump(mode="json"),
            )
            partition_key = f"{bar.exchange.value}:{bar.symbol}"
            await self._producer.send(KafkaTopic.PRICES_REALTIME, msg, key=partition_key)
            published += 1
        logger.info(
            "openbb.kafka_published",
            symbol=bars[0].symbol,
            messages=published,
            topic=KafkaTopic.PRICES_REALTIME.value,
        )
        return published

    async def cache_bars_in_redis(
        self,
        bars: Sequence[OHLCVBar],
        *,
        asset_class: ProviderAssetClass = ProviderAssetClass.EQUITY,
        provider: str = "yfinance",
    ) -> bool:
        """Update Redis `prices:{symbol}` and history cache for the ingested bars."""
        if not bars or self._state is None:
            return False
        latest = bars[-1]
        ts_utc = _ensure_utc(latest.time)
        price_payload = {
            "last": float(latest.close),
            "exchange": latest.exchange.value,
            "ts": ts_utc.isoformat(),
            "source": f"openbb:{provider}",
        }
        await self._state.redis.setex(
            _REDIS_PRICE_KEY_FMT.format(symbol=latest.symbol),
            _REDIS_PRICE_TTL,
            json.dumps(price_payload),
        )
        ttl = self._settings.openbb_cache_ttl_seconds
        if ttl > 0:
            history_key = _REDIS_HISTORY_KEY_FMT.format(
                asset_class=asset_class.value,
                symbol=latest.symbol,
                timeframe=latest.timeframe.value,
                provider=provider.strip().lower(),
            )
            serialized = json.dumps([bar.model_dump(mode="json") for bar in bars])
            await self._state.redis.setex(history_key, ttl, serialized)
        return True

    async def get_cached_history(
        self,
        symbol: str,
        *,
        asset_class: ProviderAssetClass = ProviderAssetClass.EQUITY,
        timeframe: Timeframe = Timeframe.D1,
        provider: str | None = None,
    ) -> list[OHLCVBar] | None:
        """Return cached `OHLCVBar` list from Redis if present and valid."""
        if self._state is None or self._settings.openbb_cache_ttl_seconds <= 0:
            return None
        resolved_provider = (provider or self._adapter.default_provider_for(asset_class)).strip().lower()
        history_key = _REDIS_HISTORY_KEY_FMT.format(
            asset_class=asset_class.value,
            symbol=symbol.strip().upper(),
            timeframe=timeframe.value,
            provider=resolved_provider,
        )
        raw = await self._state.redis.get(history_key)
        if not raw:
            return None
        try:
            items = json.loads(raw)
            return [OHLCVBar.model_validate(item) for item in items]
        except Exception:
            return None

    async def fetch_and_ingest(
        self,
        symbol: str,
        *,
        asset_class: ProviderAssetClass = ProviderAssetClass.EQUITY,
        timeframe: Timeframe = Timeframe.D1,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        provider: str | None = None,
        persist_db: bool = True,
        publish_kafka: bool = False,
        cache_redis: bool = True,
    ) -> IngestionSummary:
        """Fetch historical OHLCV via OpenBB and route through TimescaleDB, Kafka, and Redis."""
        resolved_provider = (
            provider or self._adapter.default_provider_for(asset_class)
        ).strip().lower()
        bars = await self._adapter.fetch_historical_ohlcv(
            symbol,
            asset_class=asset_class,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            provider=resolved_provider,
            exchange=Exchange.OPENBB,
        )
        db_rows = 0
        if persist_db and (self._db_pool is not None or self._settings.database_url):
            db_rows = await self.persist_bars_to_timescaledb(bars)

        kafka_msgs = 0
        if publish_kafka and self._producer is not None:
            kafka_msgs = await self.publish_bars_to_kafka(bars)

        redis_ok = False
        if cache_redis and self._state is not None:
            redis_ok = await self.cache_bars_in_redis(
                bars,
                asset_class=asset_class,
                provider=resolved_provider,
            )

        return IngestionSummary(
            symbol=symbol.strip().upper(),
            provider=resolved_provider,
            timeframe=timeframe.value,
            bars_fetched=len(bars),
            db_rows_upserted=db_rows,
            kafka_messages_published=kafka_msgs,
            redis_cached=redis_ok,
        )
