"""Конфигурация приложения через переменные окружения."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки API. Значения берутся из окружения, файл .env опционален."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "anime-sync-api"
    app_version: str = "0.1.0"
    debug: bool = False

    # Строка подключения. По умолчанию — SQLite, чтобы тесты и локальный запуск
    # не требовали установленного PostgreSQL. В Docker собирается из переменных.
    database_url: str = "sqlite+aiosqlite:///./anime.db"

    # Строка для Alembic: sync-драйвер вместо async.
    alembic_database_url: str = ""

    api_prefix: str = "/api"
    default_page_size: int = 20
    max_page_size: int = 100

    # Внешние источники данных.
    anilist_url: str = "https://graphql.anilist.co"
    jikan_url: str = "https://api.jikan.moe/v4"
    sync_batch_size: int = 50
    request_timeout: float = 20.0

    @property
    def sync_database_url(self) -> str:
        """URL для синхронного подключения (Alembic требует sync-драйвера)."""
        if self.alembic_database_url:
            return self.alembic_database_url
        return self.database_url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg")


@lru_cache
def get_settings() -> Settings:
    return Settings()