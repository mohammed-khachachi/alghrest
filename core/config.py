"""
ALGHREST — Central Configuration
Single source of truth for all environment settings across all 32 agents.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── SYSTEM ────────────────────────────────────────────
    environment: str = "development"    # development | paper_trading | live
    log_level: str = "INFO"
    system_capital_usd: float = 10_000.0

    # ── API SECURITY ─────────────────────────────────────
    api_auth_enabled: bool = True
    alghrest_api_key: str = "change-me"
    api_allowed_origins: str = "http://localhost:5173,http://localhost:8000"

    # ── DeFi SAFETY ──────────────────────────────────────
    # 🚨 CRITICAL: Tier 6 DeFi agents contain mock logic and are HIGH RISK
    # Only enable after implementing proper protocol integrations
    enable_defi_agents: bool = False   # Force disable DeFi agents (safety override)

    # ── AI ────────────────────────────────────────────────
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
    ibkr_port: int = 7497        # 7497=paper, 7496=live
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
    kafka_schema_registry_url: str = "http://localhost:8081"
    kafka_consumer_group_prefix: str = "alghrest"

    redis_url: str = "redis://localhost:6379"
    redis_db_cache: int = 0
    redis_db_celery: int = 1
    redis_db_state: int = 2

    database_url: str = "postgresql+asyncpg://alghrest:alghrest_secure_pass_2024@localhost:5432/alghrest"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # ── MONITORING ────────────────────────────────────────
    prometheus_port: int = 9090
    sentry_dsn: str = ""
    pagerduty_api_key: str = ""
    pagerduty_integration_key: str = ""   # PagerDuty Events API v2 integration key

    # ── TELEGRAM ─────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_channel_id: str = ""
    telegram_chat_id: str = ""            # Chat ID for bot alerts
    telegram_admin_id: str = ""

    # ── ML ───────────────────────────────────────────────
    model_checkpoint_dir: str = "./ml/checkpoints"
    cuda_device: int = -1     # -1 = CPU

    # ── COMPUTED PROPERTIES ───────────────────────────────
    @field_validator("environment")
    @classmethod
    def validate_env(cls, v: str) -> str:
        allowed = {"development", "paper_trading", "live"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v

    @model_validator(mode="after")
    def validate_api_security(self) -> "Settings":
        non_development = self.environment in {"paper_trading", "live"}

        if non_development and not self.api_auth_enabled:
            raise ValueError(
                "API_AUTH_ENABLED cannot be false when ENVIRONMENT is paper_trading or live"
            )

        if self.api_auth_enabled and not self.alghrest_api_key.strip():
            raise ValueError("ALGHREST_API_KEY must be set when API authentication is enabled")

        if non_development and self.alghrest_api_key.strip() == "change-me":
            raise ValueError(
                "ALGHREST_API_KEY must be changed when ENVIRONMENT is paper_trading or live"
            )

        if non_development and "*" in self.api_allowed_origins_list:
            raise ValueError("API_ALLOWED_ORIGINS cannot contain '*' outside development")

        return self

    @property
    def is_live(self) -> bool:
        return self.environment == "live"

    @property
    def is_paper(self) -> bool:
        return self.environment == "paper_trading"

    @property
    def kafka_servers_list(self) -> list[str]:
        return self.kafka_bootstrap_servers.split(",")

    @property
    def api_allowed_origins_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.api_allowed_origins.split(",")
            if origin.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
