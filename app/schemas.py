"""Схемы Pydantic v2: валидация входных данных и сериализация ответов."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    target_source: str
    target_external_id: str
    relation: str


class AnimeBase(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    title_romaji: str | None = None
    description: str | None = None
    episodes: int | None = Field(default=None, ge=0)
    score: float | None = Field(default=None, ge=0, le=10)
    genres: str = ""
    status: str = ""


class AnimeCreate(AnimeBase):
    external_id: str = Field(min_length=1, max_length=64)
    source: str = Field(default="anilist", min_length=1, max_length=32)


class AnimeUpdate(BaseModel):
    """Частичное обновление: все поля опциональны."""

    title: str | None = Field(default=None, min_length=1, max_length=512)
    title_romaji: str | None = None
    description: str | None = None
    episodes: int | None = Field(default=None, ge=0)
    score: float | None = Field(default=None, ge=0, le=10)
    genres: str | None = None
    status: str | None = None


class AnimeOut(AnimeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    source: str
    created_at: datetime
    updated_at: datetime
    links: list[LinkOut] = Field(default_factory=list)


class AnimeList(BaseModel):
    """Пагинированный ответ."""

    items: list[AnimeOut]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class SyncRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    status: str
    fetched: int
    created: int
    updated: int
    skipped: int
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class SyncResult(BaseModel):
    run: SyncRunOut
    processed: int = Field(ge=0)


class HealthOut(BaseModel):
    status: str
    version: str
    database: str
    items: int = Field(ge=0)


class HealthCheck(BaseModel):
    """Валидатор имени источника для ручного запуска синхронизации."""

    source: str = Field(default="anilist", min_length=1, max_length=32)
    limit: int = Field(default=50, ge=1, le=500)

    @field_validator("source")
    @classmethod
    def _known_source(cls, value: str) -> str:
        allowed = {"anilist", "jikan"}
        if value not in allowed:
            raise ValueError(f"источник должен быть одним из {sorted(allowed)}")
        return value