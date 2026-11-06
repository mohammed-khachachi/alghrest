"""OpenBB financial data acquisition and normalization adapter.

Provides an asynchronous, non-blocking integration layer between OpenBB
data providers (yfinance, fmp, polygon, tiingo, intrinio, alpha_vantage, fred)
and Alghrest's normalized domain models (`OHLCVBar`, `Quote`, `HistoricalBar`,
`Candle`, `MarketSnapshot`, `TerminalCandle`).

This module strictly performs read-only market/macro data collection and
validation; it has no order-execution capability.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields as dataclass_fields, is_dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from pydantic import HttpUrl

from connectors.data_providers.base import (
    AssetClass as ProviderAssetClass,
    HistoricalBar,
    Quote,
    QuoteProvider,
)
from core.advisory.models import (
    Candle,
    Interval as AdvisoryInterval,
    MarketDataEvidence,
    MarketSnapshot,
)
from core.advisory.openterminal_research import TerminalCandle
from core.config import Settings, settings as default_settings
from core.data.models import Exchange, OHLCVBar, Timeframe

try:
    from openbb import obb as _static_obb
except ImportError:  # pragma: no cover - static wrapper may not be generated yet
    _static_obb = None

try:
    from openbb_core.app.command_runner import CommandRunner as _OpenBBCommandRunner
except ImportError:  # pragma: no cover - handled gracefully when SDK is absent
    _OpenBBCommandRunner = None


class _RouteNamespace:
    """Hierarchical route proxy mapping `obb.<domain>.<subpath>` to `CommandRunner`."""

    def __init__(self, runner: Any, prefix: str = "") -> None:
        self._runner = runner
        self._prefix = prefix

    def __getattr__(self, name: str) -> _RouteNamespace:
        return _RouteNamespace(self._runner, f"{self._prefix}/{name}")

    def __call__(self, **kwargs: Any) -> Any:
        # `openbb_core.app.command_runner.CommandRunner.sync_run` binds parameters by name
        # (`provider_choices`, `standard_params`, `extra_params`). Partition flat kwargs
        # automatically based on the target command's dataclass signature.
        if not ({"provider_choices", "standard_params", "extra_params"} & kwargs.keys()):
            remaining = dict(kwargs)
            provider = remaining.pop("provider", None)
            provider_choices: dict[str, Any] = {"provider": provider} if provider is not None else {}

            standard_keys: set[str] = set()
            cmd_map = getattr(self._runner, "command_map", None)
            if cmd_map is not None and hasattr(cmd_map, "get_command"):
                func = cmd_map.get_command(self._prefix)
                if func is not None:
                    import inspect
                    from typing import get_type_hints

                    std_cls: Any = None
                    try:
                        hints = get_type_hints(func)
                        std_cls = hints.get("standard_params")
                    except Exception:
                        pass
                    if std_cls is None:
                        sig = inspect.signature(func)
                        std_param = sig.parameters.get("standard_params")
                        if std_param is not None:
                            std_cls = std_param.annotation
                    if std_cls is not None and is_dataclass(std_cls):
                        standard_keys = {f.name for f in dataclass_fields(std_cls)}
                    elif std_cls is not None and hasattr(std_cls, "__dataclass_fields__"):
                        standard_keys = set(std_cls.__dataclass_fields__.keys())

            if standard_keys:
                standard_params = {k: v for k, v in remaining.items() if k in standard_keys}
                extra_params = {k: v for k, v in remaining.items() if k not in standard_keys}
            else:
                standard_params = remaining
                extra_params = {}

            return self._runner.sync_run(
                self._prefix,
                provider_choices=provider_choices,
                standard_params=standard_params,
                extra_params=extra_params,
            )
        return self._runner.sync_run(self._prefix, **kwargs)


class _CommandRunnerOBBClient:
    """Lightweight OpenBB SDK client backed directly by `openbb_core.app.command_runner.CommandRunner`."""

    def __init__(self, runner: Any) -> None:
        self._runner = runner
        self.equity = _RouteNamespace(runner, "/equity")
        self.crypto = _RouteNamespace(runner, "/crypto")
        self.currency = _RouteNamespace(runner, "/currency")
        self.economy = _RouteNamespace(runner, "/economy")

    @property
    def user(self) -> Any:
        return self._runner.user_settings


def _get_default_obb_client() -> Any | None:
    if _static_obb is not None:
        return _static_obb
    if _OpenBBCommandRunner is not None:
        try:
            return _CommandRunnerOBBClient(_OpenBBCommandRunner())
        except Exception:
            return None
    return None

logger = structlog.get_logger(__name__)


class OpenBBAdapterError(RuntimeError):
    """Base error for OpenBB adapter failures."""


class OpenBBUnavailableError(OpenBBAdapterError):
    """Raised when the OpenBB SDK is not installed or is disabled."""


class OpenBBProviderError(OpenBBAdapterError):
    """Raised when an OpenBB provider does not support an endpoint or fails."""


class OpenBBDataValidationError(OpenBBAdapterError):
    """Raised when OpenBB returns empty or malformed financial data."""


# Explicit capability matrix so we never assume all OpenBB providers support the same endpoints.
PROVIDER_CAPABILITIES: dict[str, frozenset[str]] = {
    "yfinance": frozenset(
        {
            "equity.historical",
            "equity.quote",
            "crypto.historical",
            "forex.historical",
        }
    ),
    "fmp": frozenset(
        {
            "equity.historical",
            "equity.quote",
            "crypto.historical",
            "forex.historical",
        }
    ),
    "polygon": frozenset(
        {
            "equity.historical",
            "crypto.historical",
            "forex.historical",
        }
    ),
    "tiingo": frozenset(
        {
            "equity.historical",
            "crypto.historical",
            "forex.historical",
        }
    ),
    "intrinio": frozenset(
        {
            "equity.historical",
            "equity.quote",
        }
    ),
    "alpha_vantage": frozenset(
        {
            "equity.historical",
            "equity.quote",
            "crypto.historical",
            "forex.historical",
        }
    ),
    "fred": frozenset(
        {
            "macro.fred_series",
        }
    ),
}

_TIMEFRAME_TO_OPENBB_INTERVAL: dict[Timeframe, str] = {
    Timeframe.M1: "1m",
    Timeframe.M5: "5m",
    Timeframe.M15: "15m",
    Timeframe.M30: "30m",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1d",
    Timeframe.W1: "1W",
}


@dataclass(frozen=True, slots=True)
class MacroObservation:
    """Normalized macroeconomic time-series observation from OpenBB."""

    series_id: str
    date: date
    value: Decimal
    provider: str


def _to_finite_decimal(value: Any, *, field_name: str, allow_zero: bool = False) -> Decimal:
    """Convert raw numeric value to a finite Decimal, rejecting booleans/NaN/Inf."""
    if value is None or isinstance(value, bool):
        raise OpenBBDataValidationError(f"Missing or invalid {field_name}: {value!r}")
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise OpenBBDataValidationError(f"Non-numeric {field_name}: {value!r}") from exc
    if not dec.is_finite():
        raise OpenBBDataValidationError(f"Non-finite {field_name}: {value!r}")
    if allow_zero:
        if dec < Decimal("0"):
            raise OpenBBDataValidationError(f"Negative {field_name}: {dec}")
    elif dec <= Decimal("0"):
        raise OpenBBDataValidationError(f"Non-positive {field_name}: {dec}")
    return dec


def _normalize_timestamp_utc(value: Any) -> datetime:
    """Normalize a date, datetime, or ISO-8601 string into an aware UTC datetime."""
    if value is None:
        raise OpenBBDataValidationError("Missing timestamp in OpenBB record")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, int | float) and not isinstance(value, bool):
        ts = float(value)
        if ts > 1e11:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=UTC)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise OpenBBDataValidationError("Blank timestamp string in OpenBB record")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            try:
                parsed_date = date.fromisoformat(text[:10])
                return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=UTC)
            except ValueError:
                raise OpenBBDataValidationError(f"Malformed timestamp: {value!r}") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    # Support pandas.Timestamp without importing pandas at module top-level if duck-typed
    if hasattr(value, "to_pydatetime"):
        py_dt = value.to_pydatetime()
        return _normalize_timestamp_utc(py_dt)
    raise OpenBBDataValidationError(f"Unsupported timestamp type: {type(value).__name__}")


def normalize_provider_symbol(
    symbol: str,
    asset_class: ProviderAssetClass,
    provider: str,
) -> str:
    """Translate Alghrest symbol conventions into provider-specific tickers."""
    cleaned = symbol.strip().upper()
    if not cleaned or not any(ch.isalnum() for ch in cleaned):
        raise OpenBBDataValidationError(f"Invalid symbol: {symbol!r}")

    prov = provider.strip().lower()
    if asset_class == ProviderAssetClass.CRYPTO:
        # Internal symbols can be "BTC", "BTC/USDT", "BTC/USD", "BTC-USD"
        base = cleaned.split("/")[0].split("-")[0]
        quote = "USD"
        if "/" in cleaned:
            raw_quote = cleaned.split("/", 1)[1]
            quote = "USD" if raw_quote in {"USDT", "USDC", "USD"} else raw_quote
        elif "-" in cleaned:
            raw_quote = cleaned.split("-", 1)[1]
            quote = "USD" if raw_quote in {"USDT", "USDC", "USD"} else raw_quote
        if prov == "yfinance":
            return f"{base}-{quote}"
        return f"{base}{quote}"

    if asset_class == ProviderAssetClass.FOREX:
        # Internal symbols like "EUR/USD", "XAU/USD"
        pair = cleaned.replace("/", "").replace("-", "")
        if prov == "yfinance":
            if pair.endswith("=X"):
                return pair
            return f"{pair}=X"
        return pair

    # Equities ("AAPL", "MSFT", "BRK.B")
    return cleaned


def _extract_records(obb_response: Any) -> list[dict[str, Any]]:
    """Extract a list of dictionary rows from an OpenBB OBBject or list/DataFrame."""
    if obb_response is None:
        raise OpenBBDataValidationError("OpenBB returned None response")

    results = getattr(obb_response, "results", obb_response)
    if results is None:
        raise OpenBBDataValidationError("OpenBB response contained no results")

    if isinstance(results, Sequence) and not isinstance(results, str | bytes):
        rows: list[dict[str, Any]] = []
        for item in results:
            if isinstance(item, Mapping):
                rows.append(dict(item))
            elif hasattr(item, "model_dump"):
                rows.append(item.model_dump())
            elif hasattr(item, "dict"):
                rows.append(item.dict())
            elif hasattr(item, "__dict__"):
                rows.append(
                    {k: v for k, v in vars(item).items() if not k.startswith("_")}
                )
            else:
                raise OpenBBDataValidationError(
                    f"Unsupported OpenBB record type: {type(item).__name__}"
                )
        return rows

    if hasattr(obb_response, "to_df"):
        df = obb_response.to_df()
        if df is None or df.empty:
            return []
        reset_df = df.reset_index()
        return [dict(row) for row in reset_df.to_dict(orient="records")]

    raise OpenBBDataValidationError(
        f"Unsupported OpenBB response container: {type(obb_response).__name__}"
    )


class OpenBBAdapter:
    """Asynchronous adapter encapsulating OpenBB SDK providers and data quality rules."""

    def __init__(
        self,
        *,
        config: Settings | None = None,
        obb_client: Any | None = None,
    ) -> None:
        self._settings = config or default_settings
        self._obb = obb_client if obb_client is not None else _get_default_obb_client()
        self._credentials_configured = False

    @property
    def is_available(self) -> bool:
        """Return True when the OpenBB SDK client is available."""
        return self._obb is not None

    @property
    def timeout_seconds(self) -> float:
        return float(self._settings.openbb_timeout_seconds)

    def default_provider_for(self, asset_class: ProviderAssetClass | str) -> str:
        """Return the configured default OpenBB provider for an asset class."""
        ac_val = (
            asset_class.value
            if isinstance(asset_class, ProviderAssetClass)
            else str(asset_class).lower()
        )
        if ac_val == ProviderAssetClass.CRYPTO.value:
            return self._settings.openbb_default_crypto_provider.strip().lower()
        if ac_val == ProviderAssetClass.FOREX.value:
            return self._settings.openbb_default_forex_provider.strip().lower()
        if ac_val == "macro":
            return self._settings.openbb_default_macro_provider.strip().lower()
        return self._settings.openbb_default_equity_provider.strip().lower()

    def supported_providers(self, capability: str | None = None) -> list[str]:
        """List supported providers, optionally filtered by endpoint capability."""
        if capability is None:
            return sorted(PROVIDER_CAPABILITIES.keys())
        return sorted(
            prov for prov, caps in PROVIDER_CAPABILITIES.items() if capability in caps
        )

    def _ensure_client(self) -> Any:
        if self._obb is None:
            raise OpenBBUnavailableError(
                "OpenBB SDK is not installed or client was not provided."
            )
        if not self._credentials_configured:
            self._configure_credentials(self._obb)
            self._credentials_configured = True
        return self._obb

    def _configure_credentials(self, obb_client: Any) -> None:
        """Apply non-empty API keys from Settings into OpenBB user credentials in memory."""
        user_obj = getattr(obb_client, "user", None)
        creds = getattr(user_obj, "credentials", None)
        if creds is None:
            return

        pat = self._settings.openbb_pat.get_secret_value().strip()
        if pat and hasattr(obb_client, "account") and hasattr(obb_client.account, "login"):
            try:
                obb_client.account.login(pat=pat)
            except Exception as exc:
                logger.warning("openbb.pat_login_failed", error_type=type(exc).__name__)

        credential_mapping = {
            "fmp_api_key": self._settings.openbb_fmp_api_key.get_secret_value().strip(),
            "polygon_api_key": self._settings.openbb_polygon_api_key.get_secret_value().strip(),
            "tiingo_token": self._settings.openbb_tiingo_api_key.get_secret_value().strip(),
            "intrinio_api_key": self._settings.openbb_intrinio_api_key.get_secret_value().strip(),
            "alpha_vantage_api_key": (
                self._settings.openbb_alpha_vantage_api_key.get_secret_value().strip()
            ),
            "fred_api_key": self._settings.fred_api_key.strip(),
        }
        for attr_name, secret_val in credential_mapping.items():
            if secret_val:
                try:
                    setattr(creds, attr_name, secret_val)
                except Exception as exc:
                    logger.warning(
                        "openbb.credential_set_failed",
                        credential=attr_name,
                        error_type=type(exc).__name__,
                    )

    @staticmethod
    def _validate_capability(provider: str, capability: str) -> str:
        prov = provider.strip().lower()
        caps = PROVIDER_CAPABILITIES.get(prov)
        if caps is None:
            raise OpenBBProviderError(
                f"Unsupported OpenBB provider '{prov}'. "
                f"Supported providers: {sorted(PROVIDER_CAPABILITIES)}"
            )
        if capability not in caps:
            raise OpenBBProviderError(
                f"OpenBB provider '{prov}' does not support '{capability}'. "
                f"Supported capabilities for '{prov}': {sorted(caps)}"
            )
        return prov

    async def fetch_historical_ohlcv(
        self,
        symbol: str,
        *,
        asset_class: ProviderAssetClass = ProviderAssetClass.EQUITY,
        timeframe: Timeframe = Timeframe.D1,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        provider: str | None = None,
        exchange: Exchange = Exchange.OPENBB,
    ) -> list[OHLCVBar]:
        """Fetch historical OHLCV bars via OpenBB, validate, deduplicate, and normalize."""
        obb_client = self._ensure_client()
        resolved_provider = self._validate_capability(
            provider or self.default_provider_for(asset_class),
            f"{asset_class.value}.historical",
        )
        provider_symbol = normalize_provider_symbol(symbol, asset_class, resolved_provider)
        interval_str = _TIMEFRAME_TO_OPENBB_INTERVAL.get(timeframe, "1d")

        start_str = (
            start_date.isoformat()
            if isinstance(start_date, date)
            else str(start_date).strip() if start_date else None
        )
        end_str = (
            end_date.isoformat()
            if isinstance(end_date, date)
            else str(end_date).strip() if end_date else None
        )

        def _call_openbb() -> Any:
            kwargs: dict[str, Any] = {
                "symbol": provider_symbol,
                "provider": resolved_provider,
                "interval": interval_str,
            }
            if start_str:
                kwargs["start_date"] = start_str
            if end_str:
                kwargs["end_date"] = end_str

            if asset_class == ProviderAssetClass.CRYPTO:
                endpoint = obb_client.crypto.price.historical
            elif asset_class == ProviderAssetClass.FOREX:
                endpoint = obb_client.currency.price.historical
            else:
                endpoint = obb_client.equity.price.historical

            last_exc: Exception | None = None
            for attempt in range(2):
                try:
                    try:
                        return endpoint(**kwargs)
                    except TypeError:
                        # Some providers do not accept `interval` on daily endpoints
                        kwargs.pop("interval", None)
                        return endpoint(**kwargs)
                except Exception as exc:
                    last_exc = exc
                    err_msg = str(exc).lower()
                    is_transient = any(
                        s in err_msg
                        for s in (
                            "connection reset",
                            "recv failure",
                            "connection error",
                            "56",
                            "closed abruptly",
                        )
                    ) or type(exc).__name__ == "EmptyDataError"
                    if attempt == 0 and is_transient:
                        time.sleep(0.3)
                        continue
                    raise
            if last_exc is not None:
                raise last_exc

        try:
            async with asyncio.timeout(self.timeout_seconds):
                response = await asyncio.to_thread(_call_openbb)
        except TimeoutError as exc:
            raise OpenBBProviderError(
                f"OpenBB historical request timed out after {self.timeout_seconds}s "
                f"(symbol={symbol}, provider={resolved_provider})"
            ) from exc
        except OpenBBAdapterError:
            raise
        except Exception as exc:
            if type(exc).__name__ == "EmptyDataError":
                raise OpenBBDataValidationError(
                    f"OpenBB returned 0 historical records for symbol '{symbol}' "
                    f"(provider={resolved_provider}): {exc}"
                ) from exc
            raise OpenBBProviderError(
                f"OpenBB provider '{resolved_provider}' failed for symbol '{symbol}': {exc}"
            ) from exc

        raw_rows = _extract_records(response)
        if not raw_rows:
            raise OpenBBDataValidationError(
                f"OpenBB returned 0 historical records for symbol '{symbol}' "
                f"(provider={resolved_provider})"
            )

        return self.normalize_ohlcv_records(
            raw_rows,
            symbol=symbol.strip().upper(),
            timeframe=timeframe,
            exchange=exchange,
        )

    @staticmethod
    def normalize_ohlcv_records(
        records: Sequence[Mapping[str, Any]],
        *,
        symbol: str,
        timeframe: Timeframe = Timeframe.D1,
        exchange: Exchange = Exchange.OPENBB,
    ) -> list[OHLCVBar]:
        """Validate, normalize, deduplicate, and sort raw OpenBB OHLCV records."""
        clean_symbol = symbol.strip().upper()
        if not clean_symbol or not any(ch.isalnum() for ch in clean_symbol):
            raise OpenBBDataValidationError(f"Invalid symbol: {symbol!r}")
        if not records:
            raise OpenBBDataValidationError(f"No OHLCV records provided for {clean_symbol}")

        deduped_by_time: dict[datetime, OHLCVBar] = {}
        duplicate_count = 0
        now_utc = datetime.now(UTC) + timedelta(days=1)

        for idx, row in enumerate(records):
            raw_date = row.get("date") if "date" in row else row.get("timestamp", row.get("time"))
            ts_utc = _normalize_timestamp_utc(raw_date)
            if ts_utc > now_utc:
                raise OpenBBDataValidationError(
                    f"Future timestamp in OpenBB record #{idx} for {clean_symbol}: {ts_utc.isoformat()}"
                )

            open_p = _to_finite_decimal(row.get("open"), field_name="open")
            high_p = _to_finite_decimal(row.get("high"), field_name="high")
            low_p = _to_finite_decimal(row.get("low"), field_name="low")
            close_p = _to_finite_decimal(row.get("close"), field_name="close")

            raw_vol = row.get("volume", 0)
            volume = (
                Decimal("0")
                if raw_vol is None
                else _to_finite_decimal(raw_vol, field_name="volume", allow_zero=True)
            )

            if high_p < low_p:
                raise OpenBBDataValidationError(
                    f"Invalid OHLC envelope in record #{idx} for {clean_symbol}: "
                    f"open={open_p}, high={high_p}, low={low_p}, close={close_p}"
                )
            max_oc = max(open_p, close_p)
            min_oc = min(open_p, close_p)
            if low_p > min_oc or high_p < max_oc:
                # Allow minor upstream float/inverse-quote precision drift (<=0.5%),
                # clamping high/low to the valid OHLC envelope; reject gross corruption.
                tolerance = max_oc * Decimal("0.005")
                if (low_p - min_oc) > tolerance or (max_oc - high_p) > tolerance:
                    raise OpenBBDataValidationError(
                        f"Invalid OHLC envelope in record #{idx} for {clean_symbol}: "
                        f"open={open_p}, high={high_p}, low={low_p}, close={close_p}"
                    )
                high_p = max(high_p, max_oc)
                low_p = min(low_p, min_oc)

            vwap_raw = row.get("vwap")
            vwap = (
                _to_finite_decimal(vwap_raw, field_name="vwap")
                if vwap_raw is not None
                else None
            )
            trades_raw = row.get("transactions", row.get("trade_count", 0))
            trade_count = int(trades_raw) if isinstance(trades_raw, int | float) and trades_raw >= 0 else 0

            # OHLCVBar in core.data.models uses UTC timestamps
            if ts_utc in deduped_by_time:
                duplicate_count += 1
            deduped_by_time[ts_utc] = OHLCVBar(
                time=ts_utc,
                symbol=clean_symbol,
                exchange=exchange,
                timeframe=timeframe,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=volume,
                vwap=vwap,
                trade_count=trade_count,
                is_closed=True,
            )

        if duplicate_count > 0:
            logger.warning(
                "openbb.duplicate_ohlcv_records_deduplicated",
                symbol=clean_symbol,
                duplicates=duplicate_count,
                unique_bars=len(deduped_by_time),
            )

        return [deduped_by_time[ts] for ts in sorted(deduped_by_time)]

    async def fetch_quote(
        self,
        symbol: str,
        *,
        asset_class: ProviderAssetClass = ProviderAssetClass.EQUITY,
        provider: str | None = None,
    ) -> Quote:
        """Fetch a normalized Quote for the symbol using OpenBB."""
        resolved_provider = provider or self.default_provider_for(asset_class)
        # For equity providers supporting equity.quote, attempt direct quote first;
        # otherwise derive latest quote from recent daily bars.
        if (
            asset_class == ProviderAssetClass.EQUITY
            and "equity.quote" in PROVIDER_CAPABILITIES.get(resolved_provider.lower(), frozenset())
        ):
            try:
                return await self._fetch_equity_quote_direct(symbol, resolved_provider)
            except OpenBBAdapterError:
                logger.debug(
                    "openbb.direct_quote_fallback_to_historical",
                    symbol=symbol,
                    provider=resolved_provider,
                )

        end_dt = datetime.now(UTC).date()
        start_dt = end_dt - timedelta(days=10)
        bars = await self.fetch_historical_ohlcv(
            symbol,
            asset_class=asset_class,
            timeframe=Timeframe.D1,
            start_date=start_dt,
            end_date=end_dt,
            provider=resolved_provider,
        )
        latest = bars[-1]
        prev_close = bars[-2].close if len(bars) >= 2 else latest.open
        change_pct = (
            float(((latest.close - prev_close) / prev_close) * Decimal("100"))
            if prev_close > 0
            else 0.0
        )
        price_f = float(latest.close)
        spread = max(price_f * 0.0002, 0.00001)
        decimals = 5 if asset_class == ProviderAssetClass.FOREX else (4 if asset_class == ProviderAssetClass.CRYPTO else 2)
        return Quote(
            symbol=symbol.strip().upper(),
            asset_class=asset_class,
            price=round(price_f, decimals),
            open=round(float(latest.open), decimals),
            high=round(float(latest.high), decimals),
            low=round(float(latest.low), decimals),
            change_24h_pct=round(change_pct, 3 if asset_class == ProviderAssetClass.FOREX else 2),
            bid=round(price_f - spread, decimals),
            ask=round(price_f + spread, decimals),
            volume_24h=float(latest.volume) if latest.volume > 0 else None,
            ts=latest.time.astimezone(UTC).isoformat(),
        )

    async def _fetch_equity_quote_direct(self, symbol: str, provider: str) -> Quote:
        obb_client = self._ensure_client()
        resolved_provider = self._validate_capability(provider, "equity.quote")
        provider_symbol = normalize_provider_symbol(
            symbol, ProviderAssetClass.EQUITY, resolved_provider
        )

        def _call_quote() -> Any:
            return obb_client.equity.price.quote(
                symbol=provider_symbol, provider=resolved_provider
            )

        try:
            async with asyncio.timeout(self.timeout_seconds):
                response = await asyncio.to_thread(_call_quote)
        except TimeoutError as exc:
            raise OpenBBProviderError(
                f"OpenBB quote request timed out after {self.timeout_seconds}s"
            ) from exc
        except Exception as exc:
            if type(exc).__name__ == "EmptyDataError":
                raise OpenBBDataValidationError(f"Empty quote response for {symbol}: {exc}") from exc
            raise OpenBBProviderError(
                f"OpenBB equity.price.quote failed ({resolved_provider}): {exc}"
            ) from exc

        rows = _extract_records(response)
        if not rows:
            raise OpenBBDataValidationError(f"Empty quote response for {symbol}")
        row = rows[0]

        raw_price = (
            row.get("last_price")
            or row.get("price")
            or row.get("close")
            or row.get("prev_close")
        )
        price_dec = _to_finite_decimal(raw_price, field_name="last_price")
        open_dec = (
            _to_finite_decimal(row["open"], field_name="open")
            if row.get("open") is not None
            else price_dec
        )
        high_dec = (
            _to_finite_decimal(row["high"], field_name="high")
            if row.get("high") is not None
            else max(open_dec, price_dec)
        )
        low_dec = (
            _to_finite_decimal(row["low"], field_name="low")
            if row.get("low") is not None
            else min(open_dec, price_dec)
        )
        high_dec = max(high_dec, open_dec, price_dec)
        low_dec = min(low_dec, open_dec, price_dec)

        prev_close_dec = (
            _to_finite_decimal(row["prev_close"], field_name="prev_close")
            if row.get("prev_close") is not None
            else open_dec
        )
        change_pct = (
            float(((price_dec - prev_close_dec) / prev_close_dec) * Decimal("100"))
            if prev_close_dec > 0
            else 0.0
        )

        bid_raw = row.get("bid")
        ask_raw = row.get("ask")
        bid_dec = (
            _to_finite_decimal(bid_raw, field_name="bid", allow_zero=True)
            if bid_raw is not None
            else Decimal("0")
        )
        ask_dec = (
            _to_finite_decimal(ask_raw, field_name="ask", allow_zero=True)
            if ask_raw is not None
            else Decimal("0")
        )
        bid_f = (
            float(bid_dec)
            if bid_dec > Decimal("0")
            else round(float(price_dec) * 0.9998, 2)
        )
        ask_f = (
            float(ask_dec)
            if ask_dec > Decimal("0") and ask_dec >= bid_dec
            else round(max(float(price_dec) * 1.0002, bid_f + 0.01), 2)
        )
        vol_raw = row.get("volume")
        vol_f = (
            float(_to_finite_decimal(vol_raw, field_name="volume", allow_zero=True))
            if vol_raw is not None
            else None
        )
        raw_ts = row.get("last_timestamp") or row.get("timestamp") or datetime.now(UTC)
        ts_utc = _normalize_timestamp_utc(raw_ts)

        return Quote(
            symbol=symbol.strip().upper(),
            asset_class=ProviderAssetClass.EQUITY,
            price=round(float(price_dec), 2),
            open=round(float(open_dec), 2),
            high=round(float(high_dec), 2),
            low=round(float(low_dec), 2),
            change_24h_pct=round(change_pct, 2),
            bid=round(bid_f, 2),
            ask=round(ask_f, 2),
            volume_24h=vol_f,
            ts=ts_utc.isoformat(),
        )

    async def fetch_macro_series(
        self,
        series_id: str,
        *,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        provider: str | None = None,
    ) -> list[MacroObservation]:
        """Fetch macroeconomic series observations (e.g. FRED) via OpenBB."""
        obb_client = self._ensure_client()
        clean_series = series_id.strip().upper()
        if not clean_series:
            raise OpenBBDataValidationError("Macro series_id must be non-empty")

        resolved_provider = self._validate_capability(
            provider or self.default_provider_for("macro"),
            "macro.fred_series",
        )
        start_str = (
            start_date.isoformat()
            if isinstance(start_date, date)
            else str(start_date).strip() if start_date else None
        )
        end_str = (
            end_date.isoformat()
            if isinstance(end_date, date)
            else str(end_date).strip() if end_date else None
        )

        def _call_macro() -> Any:
            kwargs: dict[str, Any] = {
                "symbol": clean_series,
                "provider": resolved_provider,
            }
            if start_str:
                kwargs["start_date"] = start_str
            if end_str:
                kwargs["end_date"] = end_str
            return obb_client.economy.fred_series(**kwargs)

        try:
            async with asyncio.timeout(self.timeout_seconds):
                response = await asyncio.to_thread(_call_macro)
        except TimeoutError as exc:
            raise OpenBBProviderError(
                f"OpenBB macro series '{clean_series}' timed out after {self.timeout_seconds}s"
            ) from exc
        except Exception as exc:
            if type(exc).__name__ == "EmptyDataError":
                raise OpenBBDataValidationError(
                    f"OpenBB returned 0 observations for macro series '{clean_series}': {exc}"
                ) from exc
            raise OpenBBProviderError(
                f"OpenBB macro provider '{resolved_provider}' failed for '{clean_series}': {exc}"
            ) from exc

        rows = _extract_records(response)
        if not rows:
            raise OpenBBDataValidationError(
                f"OpenBB returned 0 observations for macro series '{clean_series}'"
            )

        deduped: dict[date, MacroObservation] = {}
        for row in rows:
            raw_dt = row.get("date") or row.get("timestamp")
            ts_utc = _normalize_timestamp_utc(raw_dt)
            # OpenBB fred_series stores the value under the series_id column or "value"
            raw_val = row.get("value", row.get(clean_series))
            if raw_val is None or raw_val == ".":
                continue
            try:
                dec_val = Decimal(str(raw_val))
            except (InvalidOperation, ValueError, TypeError):
                continue
            if not dec_val.is_finite():
                continue
            deduped[ts_utc.date()] = MacroObservation(
                series_id=clean_series,
                date=ts_utc.date(),
                value=dec_val,
                provider=resolved_provider,
            )

        if not deduped:
            raise OpenBBDataValidationError(
                f"No valid numeric observations in macro series '{clean_series}'"
            )
        return [deduped[d] for d in sorted(deduped)]

    @staticmethod
    def to_historical_bars(bars: Sequence[OHLCVBar], *, price_decimals: int = 4) -> list[HistoricalBar]:
        """Convert normalized `OHLCVBar` records to dashboard `HistoricalBar` models."""
        result: list[HistoricalBar] = []
        for bar in bars:
            ts_utc = _normalize_timestamp_utc(bar.time)
            result.append(
                HistoricalBar(
                    date=ts_utc.date().isoformat(),
                    open=round(float(bar.open), price_decimals),
                    high=round(float(bar.high), price_decimals),
                    low=round(float(bar.low), price_decimals),
                    close=round(float(bar.close), price_decimals),
                    volume=round(float(bar.volume), 2) if bar.volume > 0 else None,
                )
            )
        return result

    @staticmethod
    def to_terminal_candles(bars: Sequence[OHLCVBar]) -> tuple[TerminalCandle, ...]:
        """Convert normalized `OHLCVBar` records to research `TerminalCandle` models."""
        candles: list[TerminalCandle] = []
        for bar in bars:
            ts_utc = _normalize_timestamp_utc(bar.time)
            candles.append(
                TerminalCandle(
                    time=ts_utc,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                )
            )
        return tuple(candles)

    @staticmethod
    def to_advisory_snapshot(
        bars: Sequence[OHLCVBar],
        *,
        instrument_id: str,
        interval: AdvisoryInterval = "1d",
        provider: str = "yfinance",
        fetched_at: datetime | None = None,
    ) -> MarketSnapshot:
        """Convert normalized `OHLCVBar` records into a validated `MarketSnapshot`."""
        if not bars:
            raise OpenBBDataValidationError("Cannot build MarketSnapshot from empty OHLCVBar sequence")

        interval_delta = {
            "1m": timedelta(minutes=1),
            "5m": timedelta(minutes=5),
            "15m": timedelta(minutes=15),
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
            "1d": timedelta(days=1),
        }.get(interval, timedelta(days=1))

        now_utc = _normalize_timestamp_utc(fetched_at or datetime.now(UTC))
        candles: list[Candle] = []
        for bar in bars:
            open_time = _normalize_timestamp_utc(bar.time)
            close_time = open_time + interval_delta
            if close_time > now_utc:
                close_time = now_utc
            if close_time <= open_time:
                open_time = close_time - interval_delta
            candles.append(
                Candle(
                    open_time=open_time,
                    close_time=close_time,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                )
            )

        return MarketSnapshot(
            instrument_id=instrument_id,
            interval=interval,
            source=HttpUrl(f"https://openbb.co/providers/{provider.strip().lower()}"),
            fetched_at=now_utc,
            candles=candles,
            data_mode="public_exchange",
            quality=MarketDataEvidence(
                provider_id=f"openbb-{provider.strip().lower()}",
                provider_state="active",
                heartbeat_at=now_utc,
                sequence_mode="not_applicable",
            ),
        )


class OpenBBQuoteProvider(QuoteProvider):
    """`QuoteProvider` implementation backed by `OpenBBAdapter` with safe fallback."""

    def __init__(
        self,
        asset_class: ProviderAssetClass,
        *,
        adapter: OpenBBAdapter | None = None,
        fallback_provider: QuoteProvider | None = None,
        provider_name: str | None = None,
        fallback_to_mock: bool = True,
    ) -> None:
        self.asset_class = asset_class
        self._adapter = adapter or OpenBBAdapter()
        self._fallback = fallback_provider
        self._provider_name = provider_name
        self._fallback_to_mock = fallback_to_mock

    async def quote(self, symbol: str) -> Quote:
        try:
            return await self._adapter.fetch_quote(
                symbol,
                asset_class=self.asset_class,
                provider=self._provider_name,
            )
        except OpenBBAdapterError as exc:
            if self._fallback_to_mock and self._fallback is not None:
                logger.warning(
                    "openbb.quote_fallback_to_mock",
                    symbol=symbol,
                    asset_class=self.asset_class.value,
                    reason=str(exc),
                )
                return await self._fallback.quote(symbol)
            raise

    async def history(self, symbol: str, days: int) -> list[HistoricalBar]:
        try:
            end_dt = datetime.now(UTC).date()
            # Request calendar window padded for weekends/holidays so at least `days` trading bars return
            start_dt = end_dt - timedelta(days=max(int(days * 1.6), days + 7))
            bars = await self._adapter.fetch_historical_ohlcv(
                symbol,
                asset_class=self.asset_class,
                timeframe=Timeframe.D1,
                start_date=start_dt,
                end_date=end_dt,
                provider=self._provider_name,
            )
            decimals = (
                5
                if self.asset_class == ProviderAssetClass.FOREX
                else (4 if self.asset_class == ProviderAssetClass.CRYPTO else 2)
            )
            hist = self._adapter.to_historical_bars(bars[-days:], price_decimals=decimals)
            if len(hist) < 2 and self._fallback_to_mock and self._fallback is not None:
                return await self._fallback.history(symbol, days)
            return hist
        except OpenBBAdapterError as exc:
            if self._fallback_to_mock and self._fallback is not None:
                logger.warning(
                    "openbb.history_fallback_to_mock",
                    symbol=symbol,
                    asset_class=self.asset_class.value,
                    reason=str(exc),
                )
                return await self._fallback.history(symbol, days)
            raise
