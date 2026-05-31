"""Kafka event to TimescaleDB statement mapping.

The mapper targets tables already created by ``infra/init/timescale-init.sql``.
It intentionally avoids migrations, execution-state changes, DLQs, or auth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ValidationError

from core.data.models import (
    Fill,
    KafkaTopic,
    OHLCVBar,
    Order,
    OrderBook,
    TradeProposal,
    TradeProposalStatus,
)


class PersistenceMappingError(ValueError):
    """Raised when a supported Kafka topic carries an invalid persistence payload."""


@dataclass(frozen=True)
class NormalizedKafkaMessage:
    topic: str
    message_type: str
    payload: dict[str, Any]
    source_agent_id: int
    timestamp: datetime
    message_id: str | None = None
    kafka_offset: int | None = None


@dataclass(frozen=True)
class PersistenceStatement:
    table: str
    sql: str
    params: dict[str, Any]


PERSISTED_TOPICS: list[KafkaTopic] = [
    KafkaTopic.PRICES_REALTIME,
    KafkaTopic.NEWS_TAGGED,
    KafkaTopic.SENTIMENT_SCORED,
    KafkaTopic.ONCHAIN_SIGNALS,
    KafkaTopic.MACRO_REGIME,
    KafkaTopic.INDICATORS_COMPUTED,
    KafkaTopic.PATTERNS_DETECTED,
    KafkaTopic.VOLATILITY_FORECAST,
    KafkaTopic.CORRELATION_MATRIX,
    KafkaTopic.ANALYSIS_TECHNICAL,
    KafkaTopic.STRATEGY_SIGNALS,
    KafkaTopic.PROPOSALS_BUS,
    KafkaTopic.PROPOSALS_APPROVED,
    KafkaTopic.ORDERS_PENDING,
    KafkaTopic.ORDERS_APPROVED,
    KafkaTopic.ORDERS_EXECUTED,
    KafkaTopic.ORDERS_FILLED,
    KafkaTopic.FILLS_CONFIRMED,
    KafkaTopic.PORTFOLIO_STATE,
    KafkaTopic.RISK_ALERTS,
]

_SIGNAL_TYPES_BY_TOPIC = {
    KafkaTopic.SENTIMENT_SCORED.value: "sentiment",
    KafkaTopic.ONCHAIN_SIGNALS.value: "onchain",
    KafkaTopic.MACRO_REGIME.value: "macro",
    KafkaTopic.INDICATORS_COMPUTED.value: "indicator",
    KafkaTopic.PATTERNS_DETECTED.value: "pattern",
    KafkaTopic.VOLATILITY_FORECAST.value: "volatility",
    KafkaTopic.CORRELATION_MATRIX.value: "correlation",
    KafkaTopic.ANALYSIS_TECHNICAL.value: "technical",
    KafkaTopic.STRATEGY_SIGNALS.value: "strategy",
}

_KILL_SWITCH_MESSAGE_TYPES = {"KillSwitchEvent", "HaltAllStrategies"}
_USE_CURRENT_TIME = object()


def build_persistence_statements(raw_message: dict[str, Any]) -> list[PersistenceStatement]:
    """Build SQL statements for a Kafka event envelope.

    Unknown topics are ignored so the writer can safely subscribe only to the
    explicit Phase 1 topic set. Invalid payloads on known topics raise
    ``PersistenceMappingError``; the Kafka consumer then avoids committing.
    """

    message = normalize_kafka_message(raw_message)
    topic = message.topic

    if topic == KafkaTopic.PRICES_REALTIME.value:
        return _build_price_statement(message)
    if topic in {KafkaTopic.PROPOSALS_BUS.value, KafkaTopic.PROPOSALS_APPROVED.value}:
        return [_build_trade_proposal_statement(message)]
    if topic in {
        KafkaTopic.ORDERS_PENDING.value,
        KafkaTopic.ORDERS_APPROVED.value,
        KafkaTopic.ORDERS_EXECUTED.value,
        KafkaTopic.ORDERS_FILLED.value,
    }:
        return [_build_order_statement(message)]
    if topic == KafkaTopic.FILLS_CONFIRMED.value:
        return [_build_fill_statement(message)]
    if topic in _SIGNAL_TYPES_BY_TOPIC:
        return [_build_signal_statement(message)]
    if topic == KafkaTopic.NEWS_TAGGED.value:
        return [_build_news_statement(message)]
    if topic == KafkaTopic.PORTFOLIO_STATE.value:
        return [_build_portfolio_statement(message)]
    if topic == KafkaTopic.RISK_ALERTS.value:
        if message.message_type in _KILL_SWITCH_MESSAGE_TYPES:
            return [_build_kill_switch_statement(message)]
        return [_build_risk_alert_statement(message)]

    return []


def normalize_kafka_message(raw_message: dict[str, Any]) -> NormalizedKafkaMessage:
    """Normalize an AgentMessage envelope or a legacy dict into one shape."""

    topic = _enum_value(raw_message.get("topic") or raw_message.get("kafka_topic") or "")
    if not topic:
        raise PersistenceMappingError("Kafka message is missing topic")

    payload_raw = raw_message.get("payload")
    payload = dict(payload_raw) if isinstance(payload_raw, dict) else dict(raw_message)
    message_type = str(raw_message.get("message_type") or payload.get("message_type") or topic)
    source_agent_id = _int_or_zero(
        raw_message.get("source_agent_id")
        or payload.get("source_agent_id")
        or payload.get("agent_id")
    )
    timestamp = _parse_datetime(
        raw_message.get("timestamp")
        or payload.get("timestamp")
        or payload.get("created_at")
        or payload.get("time")
    )
    message_id = raw_message.get("message_id")
    kafka_offset = raw_message.get("kafka_offset")

    return NormalizedKafkaMessage(
        topic=topic,
        message_type=message_type,
        payload=payload,
        source_agent_id=source_agent_id,
        timestamp=timestamp,
        message_id=str(message_id) if message_id is not None else None,
        kafka_offset=_int_or_none(kafka_offset),
    )


def _build_price_statement(message: NormalizedKafkaMessage) -> list[PersistenceStatement]:
    payload = message.payload
    msg_type = message.message_type.lower()
    if msg_type == "ohlcv" or {"open", "high", "low", "close"}.issubset(payload):
        return [_build_ohlcv_statement(payload)]
    if msg_type == "order_book" or "bids" in payload or "asks" in payload:
        return [_build_order_book_statement(payload)]
    return []


def _build_ohlcv_statement(payload: dict[str, Any]) -> PersistenceStatement:
    try:
        bar = OHLCVBar.model_validate(payload)
    except ValidationError as exc:
        raise PersistenceMappingError(f"Invalid OHLCV payload: {exc}") from exc

    return PersistenceStatement(
        table="market_data.ohlcv_bars",
        sql="""
            INSERT INTO market_data.ohlcv_bars (
                time, symbol, exchange, timeframe, open, high, low, close, volume, is_closed
            ) VALUES (
                :time, :symbol, :exchange, :timeframe, :open, :high, :low, :close,
                :volume, :is_closed
            )
            ON CONFLICT (time, symbol, exchange, timeframe) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                is_closed = EXCLUDED.is_closed
        """,
        params={
            "time": bar.time,
            "symbol": bar.symbol,
            "exchange": _enum_value(bar.exchange),
            "timeframe": _enum_value(bar.timeframe),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "is_closed": bar.is_closed,
        },
    )


def _build_order_book_statement(payload: dict[str, Any]) -> PersistenceStatement:
    try:
        book = OrderBook.model_validate(payload)
    except ValidationError as exc:
        raise PersistenceMappingError(f"Invalid order book payload: {exc}") from exc

    bids = sorted(book.bids, key=lambda level: level.price, reverse=True)[:10]
    asks = sorted(book.asks, key=lambda level: level.price)[:10]
    best_bid = bids[0].price if bids else None
    best_ask = asks[0].price if asks else None
    bid_depth = sum((level.size for level in bids), Decimal("0"))
    ask_depth = sum((level.size for level in asks), Decimal("0"))
    mid_price = None
    spread_bps = None
    if best_bid is not None and best_ask is not None:
        mid_price = (best_bid + best_ask) / Decimal("2")
        if mid_price > 0:
            spread_bps = (best_ask - best_bid) / mid_price * Decimal("10000")

    imbalance = None
    total_depth = bid_depth + ask_depth
    if total_depth > 0:
        imbalance = (bid_depth - ask_depth) / total_depth

    return PersistenceStatement(
        table="market_data.order_book_snapshots",
        sql="""
            INSERT INTO market_data.order_book_snapshots (
                time, symbol, exchange, mid_price, spread_bps, bid_depth, ask_depth,
                imbalance, bids, asks
            ) VALUES (
                :time, :symbol, :exchange, :mid_price, :spread_bps, :bid_depth,
                :ask_depth, :imbalance, CAST(:bids AS jsonb), CAST(:asks AS jsonb)
            )
        """,
        params={
            "time": book.timestamp,
            "symbol": book.symbol,
            "exchange": _enum_value(book.exchange),
            "mid_price": mid_price,
            "spread_bps": spread_bps,
            "bid_depth": bid_depth,
            "ask_depth": ask_depth,
            "imbalance": imbalance,
            "bids": _json_dumps([level.model_dump(mode="json") for level in bids]),
            "asks": _json_dumps([level.model_dump(mode="json") for level in asks]),
        },
    )


def _build_trade_proposal_statement(message: NormalizedKafkaMessage) -> PersistenceStatement:
    try:
        proposal = TradeProposal.model_validate(message.payload)
    except ValidationError as exc:
        raise PersistenceMappingError(f"Invalid trade proposal payload: {exc}") from exc

    status = proposal.status
    if message.topic == KafkaTopic.PROPOSALS_APPROVED.value:
        status = TradeProposalStatus.APPROVED

    return PersistenceStatement(
        table="trading.trade_proposals",
        sql="""
            INSERT INTO trading.trade_proposals (
                proposal_id, created_at, strategy_id, agent_id, symbol, exchange,
                asset_class, side, order_type, size, size_usd, limit_price, stop_loss,
                take_profit, confidence_score, rationale, status, rejection_reason,
                kafka_offset
            ) VALUES (
                :proposal_id, :created_at, :strategy_id, :agent_id, :symbol, :exchange,
                :asset_class, :side, :order_type, :size, :size_usd, :limit_price,
                :stop_loss, :take_profit, :confidence_score, :rationale, :status,
                :rejection_reason, :kafka_offset
            )
            ON CONFLICT (proposal_id, created_at) DO UPDATE SET
                size = EXCLUDED.size,
                size_usd = EXCLUDED.size_usd,
                limit_price = EXCLUDED.limit_price,
                stop_loss = EXCLUDED.stop_loss,
                take_profit = EXCLUDED.take_profit,
                confidence_score = EXCLUDED.confidence_score,
                rationale = EXCLUDED.rationale,
                status = EXCLUDED.status,
                rejection_reason = EXCLUDED.rejection_reason,
                kafka_offset = EXCLUDED.kafka_offset
        """,
        params={
            "proposal_id": str(proposal.proposal_id),
            "created_at": proposal.created_at,
            "strategy_id": proposal.strategy_id,
            "agent_id": proposal.agent_id,
            "symbol": proposal.symbol,
            "exchange": _enum_value(proposal.exchange),
            "asset_class": _enum_value(proposal.asset_class),
            "side": _enum_value(proposal.side),
            "order_type": _enum_value(proposal.order_type),
            "size": proposal.size,
            "size_usd": proposal.size_usd,
            "limit_price": proposal.limit_price,
            "stop_loss": proposal.stop_loss,
            "take_profit": proposal.take_profit,
            "confidence_score": Decimal(str(proposal.confidence_score)),
            "rationale": proposal.rationale,
            "status": _enum_value(status),
            "rejection_reason": proposal.rejection_reason,
            "kafka_offset": message.kafka_offset,
        },
    )


def _build_order_statement(message: NormalizedKafkaMessage) -> PersistenceStatement:
    try:
        order = Order.model_validate(message.payload)
    except ValidationError as exc:
        raise PersistenceMappingError(f"Invalid order payload: {exc}") from exc

    updated_at = order.updated_at or order.created_at
    return PersistenceStatement(
        table="trading.orders",
        sql="""
            INSERT INTO trading.orders (
                order_id, created_at, updated_at, client_order_id, exchange_order_id,
                proposal_id, symbol, exchange, side, order_type, size, price,
                stop_price, time_in_force, status, filled_size, avg_fill_price,
                fees, strategy_id, agent_id
            ) VALUES (
                :order_id, :created_at, :updated_at, :client_order_id,
                :exchange_order_id, :proposal_id, :symbol, :exchange, :side,
                :order_type, :size, :price, :stop_price, :time_in_force, :status,
                :filled_size, :avg_fill_price, :fees, :strategy_id, :agent_id
            )
            ON CONFLICT (order_id, created_at) DO UPDATE SET
                updated_at = EXCLUDED.updated_at,
                exchange_order_id = COALESCE(EXCLUDED.exchange_order_id, trading.orders.exchange_order_id),
                status = EXCLUDED.status,
                filled_size = EXCLUDED.filled_size,
                avg_fill_price = EXCLUDED.avg_fill_price,
                fees = EXCLUDED.fees
        """,
        params={
            "order_id": str(order.order_id),
            "created_at": order.created_at,
            "updated_at": updated_at,
            "client_order_id": str(order.client_order_id),
            "exchange_order_id": order.exchange_order_id,
            "proposal_id": str(order.proposal_id) if order.proposal_id else None,
            "symbol": order.symbol,
            "exchange": _enum_value(order.exchange),
            "side": _enum_value(order.side),
            "order_type": _enum_value(order.order_type),
            "size": order.size,
            "price": order.price,
            "stop_price": order.stop_price,
            "time_in_force": order.time_in_force,
            "status": _enum_value(order.status),
            "filled_size": order.filled_size,
            "avg_fill_price": order.avg_fill_price,
            "fees": Decimal(str(message.payload.get("fees", "0"))),
            "strategy_id": order.strategy_id,
            "agent_id": order.agent_id,
        },
    )


def _build_fill_statement(message: NormalizedKafkaMessage) -> PersistenceStatement:
    try:
        fill = Fill.model_validate(message.payload)
    except ValidationError as exc:
        raise PersistenceMappingError(f"Invalid fill payload: {exc}") from exc

    return PersistenceStatement(
        table="trading.fills",
        sql="""
            INSERT INTO trading.fills (
                fill_id, fill_time, order_id, exchange_order_id, symbol, exchange,
                side, fill_size, fill_price, fee, fee_currency, is_maker, strategy_id
            ) VALUES (
                :fill_id, :fill_time, :order_id, :exchange_order_id, :symbol,
                :exchange, :side, :fill_size, :fill_price, :fee, :fee_currency,
                :is_maker, :strategy_id
            )
            ON CONFLICT (fill_id, fill_time) DO NOTHING
        """,
        params={
            "fill_id": _coerce_uuid(fill.fill_id, f"fill:{fill.exchange}:{fill.fill_id}"),
            "fill_time": fill.timestamp,
            "order_id": str(fill.order_id),
            "exchange_order_id": fill.exchange_order_id,
            "symbol": fill.symbol,
            "exchange": _enum_value(fill.exchange),
            "side": _enum_value(fill.side),
            "fill_size": fill.fill_size,
            "fill_price": fill.fill_price,
            "fee": fill.fee,
            "fee_currency": fill.fee_currency,
            "is_maker": fill.is_maker,
            "strategy_id": fill.strategy_id,
        },
    )


def _build_signal_statement(message: NormalizedKafkaMessage) -> PersistenceStatement:
    payload = message.payload
    confidence = (
        payload.get("confidence")
        or payload.get("confidence_score")
        or payload.get("sentiment_score")
        or payload.get("impact_score")
    )
    return PersistenceStatement(
        table="intelligence.signals",
        sql="""
            INSERT INTO intelligence.signals (
                created_at, signal_type, source_agent, symbol, direction, confidence,
                expires_at, payload
            ) VALUES (
                :created_at, :signal_type, :source_agent, :symbol, :direction,
                :confidence, :expires_at, CAST(:payload AS jsonb)
            )
        """,
        params={
            "created_at": _parse_datetime(payload.get("timestamp") or payload.get("created_at"), message.timestamp),
            "signal_type": _SIGNAL_TYPES_BY_TOPIC[message.topic],
            "source_agent": _int_or_zero(
                payload.get("source_agent_id") or payload.get("agent_id") or message.source_agent_id
            ),
            "symbol": payload.get("symbol"),
            "direction": _enum_value(
                payload.get("direction")
                or payload.get("signal")
                or payload.get("regime")
            ),
            "confidence": Decimal(str(confidence)) if confidence is not None else None,
            "expires_at": _parse_datetime(payload.get("expires_at"), None),
            "payload": _json_dumps(payload),
        },
    )


def _build_news_statement(message: NormalizedKafkaMessage) -> PersistenceStatement:
    payload = message.payload
    headline = payload.get("headline") or payload.get("title")
    if not headline:
        raise PersistenceMappingError("News payload missing headline")

    return PersistenceStatement(
        table="intelligence.news_items",
        sql="""
            INSERT INTO intelligence.news_items (
                published_at, processed_at, headline, summary, source, direction,
                impact_score, categories, entities, affected_syms, finbert_label,
                finbert_conf, url
            ) VALUES (
                :published_at, :processed_at, :headline, :summary, :source,
                :direction, :impact_score, :categories, :entities, :affected_syms,
                :finbert_label, :finbert_conf, :url
            )
        """,
        params={
            "published_at": _parse_datetime(payload.get("published_at"), message.timestamp),
            "processed_at": message.timestamp,
            "headline": str(headline),
            "summary": payload.get("summary"),
            "source": str(payload.get("source") or "unknown"),
            "direction": _enum_value(payload.get("direction")),
            "impact_score": _decimal_or_none(payload.get("impact_score")),
            "categories": list(payload.get("categories") or []),
            "entities": list(payload.get("entities") or []),
            "affected_syms": list(payload.get("affected_symbols") or payload.get("affected_syms") or []),
            "finbert_label": payload.get("finbert_label"),
            "finbert_conf": _decimal_or_none(payload.get("finbert_conf")),
            "url": payload.get("url"),
        },
    )


def _build_portfolio_statement(message: NormalizedKafkaMessage) -> PersistenceStatement:
    payload = message.payload
    total_capital = _decimal_or_zero(payload.get("total_capital") or payload.get("nav"))
    available_capital = _decimal_or_zero(payload.get("available_capital"), total_capital)
    open_positions = payload.get("open_positions")
    if open_positions is None and isinstance(payload.get("positions"), list):
        open_positions = len(payload["positions"])

    return PersistenceStatement(
        table="performance.portfolio_snapshots",
        sql="""
            INSERT INTO performance.portfolio_snapshots (
                snapshot_time, total_capital, available_capital, unrealized_pnl,
                realized_pnl_day, realized_pnl_total, open_positions, exposure_pct,
                leverage
            ) VALUES (
                :snapshot_time, :total_capital, :available_capital, :unrealized_pnl,
                :realized_pnl_day, :realized_pnl_total, :open_positions,
                :exposure_pct, :leverage
            )
            ON CONFLICT (snapshot_time) DO UPDATE SET
                total_capital = EXCLUDED.total_capital,
                available_capital = EXCLUDED.available_capital,
                unrealized_pnl = EXCLUDED.unrealized_pnl,
                realized_pnl_day = EXCLUDED.realized_pnl_day,
                realized_pnl_total = EXCLUDED.realized_pnl_total,
                open_positions = EXCLUDED.open_positions,
                exposure_pct = EXCLUDED.exposure_pct,
                leverage = EXCLUDED.leverage
        """,
        params={
            "snapshot_time": _parse_datetime(
                payload.get("snapshot_time") or payload.get("timestamp"),
                message.timestamp,
            ),
            "total_capital": total_capital,
            "available_capital": available_capital,
            "unrealized_pnl": _decimal_or_zero(payload.get("unrealized_pnl")),
            "realized_pnl_day": _decimal_or_zero(payload.get("realized_pnl_day") or payload.get("daily_pnl")),
            "realized_pnl_total": _decimal_or_zero(payload.get("realized_pnl_total")),
            "open_positions": _int_or_zero(open_positions),
            "exposure_pct": _decimal_or_none(payload.get("exposure_pct")),
            "leverage": _decimal_or_none(payload.get("leverage")),
        },
    )


def _build_risk_alert_statement(message: NormalizedKafkaMessage) -> PersistenceStatement:
    payload = message.payload
    alert_id = payload.get("alert_id") or message.message_id or payload.get("event_id")
    return PersistenceStatement(
        table="risk.alerts",
        sql="""
            INSERT INTO risk.alerts (
                alert_id, triggered_at, alert_type, risk_level, source_agent_id,
                message, triggered_value, threshold_value, auto_action_taken
            ) VALUES (
                :alert_id, :triggered_at, :alert_type, :risk_level, :source_agent_id,
                :message, :triggered_value, :threshold_value, :auto_action_taken
            )
            ON CONFLICT (alert_id, triggered_at) DO NOTHING
        """,
        params={
            "alert_id": _coerce_uuid(alert_id, f"risk-alert:{message.topic}:{message.timestamp.isoformat()}"),
            "triggered_at": _parse_datetime(payload.get("timestamp") or payload.get("triggered_at"), message.timestamp),
            "alert_type": _enum_value(payload.get("alert_type") or message.message_type),
            "risk_level": _enum_value(payload.get("risk_level") or payload.get("severity") or "MEDIUM"),
            "source_agent_id": _int_or_zero(
                payload.get("source_agent_id") or payload.get("agent_id") or message.source_agent_id
            ),
            "message": str(payload.get("message") or payload.get("reason") or message.message_type),
            "triggered_value": _decimal_or_zero(payload.get("triggered_value")),
            "threshold_value": _decimal_or_zero(payload.get("threshold_value")),
            "auto_action_taken": payload.get("auto_action_taken") or payload.get("recommended_action"),
        },
    )


def _build_kill_switch_statement(message: NormalizedKafkaMessage) -> PersistenceStatement:
    payload = message.payload
    event_id = payload.get("event_id") or message.message_id
    return PersistenceStatement(
        table="risk.kill_switch_events",
        sql="""
            INSERT INTO risk.kill_switch_events (
                event_id, triggered_at, resolved_at, triggered_by_agent,
                trigger_reason, drawdown_pct, scope, positions_closed,
                capital_preserved, resolution_notes
            ) VALUES (
                :event_id, :triggered_at, :resolved_at, :triggered_by_agent,
                :trigger_reason, :drawdown_pct, :scope, :positions_closed,
                :capital_preserved, :resolution_notes
            )
            ON CONFLICT (event_id, triggered_at) DO NOTHING
        """,
        params={
            "event_id": _coerce_uuid(event_id, f"kill-switch:{message.timestamp.isoformat()}"),
            "triggered_at": _parse_datetime(payload.get("timestamp") or payload.get("triggered_at"), message.timestamp),
            "resolved_at": _parse_datetime(payload.get("resolved_at"), None),
            "triggered_by_agent": _int_or_zero(
                payload.get("triggered_by_agent")
                or payload.get("source_agent_id")
                or payload.get("agent_id")
                or message.source_agent_id
            ),
            "trigger_reason": str(payload.get("trigger_reason") or payload.get("reason") or message.message_type),
            "drawdown_pct": _decimal_or_zero(payload.get("drawdown_pct")),
            "scope": str(payload.get("scope") or "system"),
            "positions_closed": _int_or_zero(payload.get("positions_closed")),
            "capital_preserved": _decimal_or_none(payload.get("capital_preserved")),
            "resolution_notes": payload.get("resolution_notes"),
        },
    )


def _enum_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value


def _parse_datetime(
    value: Any,
    default: datetime | None | object = _USE_CURRENT_TIME,
) -> datetime | None:
    if value is None:
        return datetime.utcnow() if default is _USE_CURRENT_TIME else default
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.utcnow() if default is _USE_CURRENT_TIME else default
    return datetime.utcnow() if default is _USE_CURRENT_TIME else default


def _coerce_uuid(value: Any, fallback_seed: str) -> str:
    if value is not None:
        try:
            return str(UUID(str(value)))
        except (TypeError, ValueError):
            return str(uuid5(NAMESPACE_URL, str(value)))
    return str(uuid5(NAMESPACE_URL, fallback_seed))


def _int_or_zero(value: Any) -> int:
    parsed = _int_or_none(value)
    return 0 if parsed is None else parsed


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _decimal_or_zero(value: Any, default: Decimal | None = None) -> Decimal:
    parsed = _decimal_or_none(value)
    if parsed is not None:
        return parsed
    if default is not None:
        return default
    return Decimal("0")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))
