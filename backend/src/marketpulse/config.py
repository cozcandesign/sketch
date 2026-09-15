"""Konfigürasyon: `.env` ve ortam değişkenlerinden pydantic-settings ile okunur.

Koddan `os.environ` okunmaz (CLAUDE.md §6). Anahtar listesi ARCHITECTURE.md §16.
"""

import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from marketpulse.core.errors import ConfigError
from marketpulse.core.types import parse_symbol

ENV_FILE_NAME = ".env"


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return value


class Settings(BaseSettings):
    """Tüm ayarlar. `MP_` ön ekiyle ortamdan okunur.

    İki anahtar ön eksizdir: ANTHROPIC_API_KEY, CRYPTOPANIC_TOKEN.
    """

    model_config = SettingsConfigDict(
        env_prefix="MP_",
        env_file=None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["dev", "prod"] = "dev"
    db_url: str = "sqlite+aiosqlite:///./data/marketpulse.db"
    data_dir: Path = Path("./data")
    symbols: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    )
    timezone: str = "Europe/Istanbul"
    log_level: str = "INFO"

    api_host: str = "0.0.0.0"  # yerel ağ / container içi dinleme
    api_port: int = 8000
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    news_ingest_latency_sec: int = 300

    llm_tier1_model: str = "claude-haiku-4-5"
    llm_tier2_model: str = "claude-sonnet-5"
    llm_tier2_threshold: float = 0.6
    llm_daily_budget_usd: float = 3.0
    llm_prices_json: dict[str, tuple[float, float]] = Field(
        default_factory=lambda: {
            "claude-haiku-4-5": (1.0, 5.0),
            "claude-sonnet-5": (2.0, 10.0),
        }
    )
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    cryptopanic_token: SecretStr | None = Field(default=None, validation_alias="CRYPTOPANIC_TOKEN")

    binance_spot_base: str = "https://api.binance.com"
    binance_futures_base: str = "https://fapi.binance.com"
    binance_ws_spot: str = "wss://stream.binance.com:9443/stream"
    binance_ws_futures: str = "wss://fstream.binance.com/stream"

    outbox_poll_interval_sec: float = 0.5
    heartbeat_interval_sec: float = 30.0
    heartbeat_stale_after_sec: float = 60.0

    @field_validator("symbols", mode="before")
    @classmethod
    def _parse_symbols(cls, value: object) -> object:
        parts = _split_csv(value)
        if isinstance(parts, list):
            return [parse_symbol(str(p)) for p in parts]
        return parts

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: object) -> object:
        return _split_csv(value)

    @field_validator("llm_daily_budget_usd")
    @classmethod
    def _positive_budget(cls, value: float) -> float:
        if value <= 0:
            msg = "MP_LLM_DAILY_BUDGET_USD pozitif olmalı"
            raise ValueError(msg)
        return value

    @property
    def sqlite_path(self) -> Path | None:
        """SQLite dosya yolu (URL sqlite ise), aksi halde None."""
        prefix = "sqlite+aiosqlite:///"
        if self.db_url.startswith(prefix):
            return Path(self.db_url[len(prefix) :])
        return None

    @property
    def sync_db_url(self) -> str:
        """Alembic için senkron sürücü URL'i."""
        return self.db_url.replace("sqlite+aiosqlite://", "sqlite://", 1)


def find_env_file(start: Path | None = None) -> Path | None:
    """`.env` dosyasını cwd ve iki üst dizinde arar (repo kökü / backend / frontend'den çalışma)."""
    base = (start or Path.cwd()).resolve()
    for candidate in (base, *base.parents[:2]):
        path = candidate / ENV_FILE_NAME
        if path.is_file():
            return path
    return None


def load_settings(env_file: Path | None = None) -> Settings:
    """Ayarları yükler.

    Kural: ya bir `.env` dosyası bulunur ya da `MP_ENV` ortam değişkeni tanımlıdır (Docker'da
    compose `env_file` ile ortam değişkenleri gelir). İkisi de yoksa anlaşılır bir hata verilir.
    """
    path = env_file or find_env_file()
    if path is None and "MP_ENV" not in os.environ:
        msg = (
            ".env dosyası bulunamadı ve MP_ENV ortam değişkeni tanımlı değil.\n"
            "Yapılacak: depo kökünde `cp .env.example .env` komutunu çalıştırın, sonra dosyayı "
            "açıp ANTHROPIC_API_KEY satırını doldurun (haber modülü için gerekir; diğer alanlar "
            "varsayılanlarıyla çalışır)."
        )
        raise ConfigError(msg)
    return Settings(_env_file=path)
