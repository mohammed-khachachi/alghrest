"""
ALGHREST — Central Configuration
Single source of truth for all environment settings across all 32 agents.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.execution.contracts import AccountScope


class OrderExecutionDisabledError(RuntimeError):
    """The selected operating profile has no order-execution capability."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── SYSTEM ────────────────────────────────────────────
    environment: str = "development"  # development | paper_trading | live
    operating_profile: Literal["general", "earn2trade_tcp25"] = "general"
    log_level: str = "INFO"
    system_capital_usd: float = 10_000.0
    api_access_token: SecretStr = SecretStr("")
    advisory_access_token: SecretStr = SecretStr("")
    api_allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:80",
        "http://localhost",
        "http://127.0.0.1",
    ]
    advisory_allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # ── DeFi SAFETY ──────────────────────────────────────
    # 🚨 CRITICAL: Tier 6 DeFi agents contain mock logic and are HIGH RISK
    # Only enable after implementing proper protocol integrations
    enable_defi_agents: bool = False  # Force disable DeFi agents (safety override)

    # ── AI ────────────────────────────────────────────────
    ai_daily_budget_usd: Decimal = Field(default=Decimal("1"), ge=0, le=1000, allow_inf_nan=False)
    ai_daily_max_calls: int = Field(default=200, ge=0, le=10000)
    ai_request_timeout_seconds: float = Field(default=30, ge=1, le=120)
    ai_max_prompt_bytes: int = Field(default=32768, ge=1024, le=65536)
    ai_decision_refresh_seconds: int = Field(default=900, ge=300, le=3600)
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    # ── EXCHANGE APIs ─────────────────────────────────────
    binance_api_key: str = ""
    binance_secret: str = ""
    binance_testnet: bool = True
    binance_testnet_api_key: str = ""
    binance_testnet_secret: str = ""

    bybit_api_key: str = ""
    bybit_secret: str = ""
    bybit_testnet: bool = True

    coinbase_api_key: str = ""
    coinbase_secret: str = ""

    kraken_api_key: str = ""
    kraken_secret: str = ""

    alpaca_api_key: str = ""
    alpaca_secret: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    okx_api_key: str = ""
    okx_secret: str = ""
    okx_passphrase: str = ""

    deribit_api_key: str = ""
    deribit_secret: str = ""
    deribit_testnet: bool = True

    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497  # 7497=paper, 7496=live
    ibkr_client_id: int = 1

    # ── DATA PROVIDERS ────────────────────────────────────
    glassnode_api_key: str = ""
    nansen_api_key: str = ""
    fred_api_key: str = ""
    dune_api_key: str = ""
    coingecko_api_key: str = ""

    twitter_bearer_token: str = ""
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_secret: str = ""

    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "ALGHREST/1.0"

    # ── BLOCKCHAIN RPCs ───────────────────────────────────
    ethereum_rpc_url: str = ""
    ethereum_ws_url: str = ""
    arbitrum_rpc_url: str = ""
    optimism_rpc_url: str = ""
    polygon_rpc_url: str = ""
    base_rpc_url: str = ""
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com"

    private_key_hot_wallet: str = ""
    flashbots_auth_key: str = ""

    # ── INFRASTRUCTURE ────────────────────────────────────
    kafka_bootstrap_servers: str = "localhost:9092,localhost:9093,localhost:9094"
    kafka_security_protocol: Literal["PLAINTEXT", "SASL_PLAINTEXT", "SASL_SSL"] = "PLAINTEXT"
    kafka_sasl_username: str = ""
    kafka_sasl_password: SecretStr = SecretStr("")
    kafka_ssl_cafile: str = ""
    kafka_schema_registry_url: str = "http://localhost:8081"
    kafka_consumer_group_prefix: str = "alghrest"

    redis_url: str = "redis://localhost:6379"
    redis_db_cache: int = 0
    redis_db_celery: int = 1
    redis_db_state: int = 2

    database_url: str = ""  # Explicit DSN; never fall back to a published password.
    accounting_book: str = "main"
    accounting_usd_pegs: list[str] = Field(default_factory=list)
    accounting_mark_max_age_seconds: int = Field(default=120, ge=1, le=300)
    execution_accounts: list[AccountScope] = Field(default_factory=list)
    execution_balance_tolerances: dict[str, Decimal] = Field(default_factory=dict)
    execution_reconciliation_ttl: int = Field(default=30, ge=5, le=60)
    execution_recovery_page_budget: int = Field(default=30, ge=1, le=1000)
    execution_overlap_seconds: int = Field(default=86400, ge=60)
    execution_full_scan_seconds: int = Field(default=86400, ge=60)
    paper_fee_bps: Decimal = Field(default=Decimal("10"), ge=0, le=1000, allow_inf_nan=False)

    @field_validator("execution_balance_tolerances")
    @classmethod
    def validate_execution_tolerances(cls, values: dict[str, Decimal]) -> dict[str, Decimal]:
        if any(not v.is_finite() or v < 0 for v in values.values()):
            raise ValueError("Execution tolerances must be finite and nonnegative")
        return values

    @property
    def accounting_book_id(self) -> str:
        return f"{self.environment}:{self.accounting_book}"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # Independent manual-research process; no broker/LLM credentials are used.
    advisory_db_path: str = "artifacts/advisory/research.sqlite3"
    advisory_kafka_servers: str = ""  # opt-in read-only intelligence tap
    advisory_kafka_security_protocol: Literal["PLAINTEXT", "SASL_PLAINTEXT", "SASL_SSL"] = (
        "PLAINTEXT"
    )
    advisory_kafka_sasl_username: str = ""
    advisory_kafka_sasl_password: SecretStr = SecretStr("")
    advisory_kafka_ssl_cafile: str = ""

    # ── MONITORING ────────────────────────────────────────
    prometheus_port: int = 9090
    metrics_base_port: int = Field(default=9200, ge=1024, le=65000)
    metrics_bind_host: str = "0.0.0.0"
    sentry_dsn: str = ""
    pagerduty_api_key: str = ""
    pagerduty_integration_key: str = ""  # PagerDuty Events API v2 integration key

    # ── TELEGRAM ─────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_channel_id: str = ""
    telegram_chat_id: str = ""  # Chat ID for bot alerts
    telegram_admin_id: str = ""

    # ── ML ───────────────────────────────────────────────
    model_checkpoint_dir: str = "./artifacts/checkpoints"
    cuda_device: int = -1  # -1 = CPU

    # ── COMPUTED PROPERTIES ───────────────────────────────
    @field_validator("environment")
    @classmethod
    def validate_env(cls, v: str) -> str:
        allowed = {"development", "paper_trading", "live"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v

    def require_order_execution(self) -> None:
        """Deny order-capable workflows independently of the environment.

        Only the general profile has this capability. Unknown values introduced
        through unvalidated internal copies also fail closed.
        """
        if self.operating_profile != "general":
            raise OrderExecutionDisabledError(
                "Order execution is disabled for this advisory operating profile"
            )

    @property
    def is_live(self) -> bool:
        return self.environment == "live"

    @property
    def is_paper(self) -> bool:
        return self.environment == "paper_trading"

    @property
    def kafka_servers_list(self) -> list[str]:
        return self.kafka_bootstrap_servers.split(",")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
