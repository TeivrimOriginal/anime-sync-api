"""Модели SQLAlchemy 2.0.

Схема рассчитана на PostgreSQL: уникальные индексы, внешние ключи,
CHECK-ограничения и полнотекстовый индекс GIN.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Anime(Base):
    """Аниме в каталоге."""

    __tablename__ = "anime"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="anilist")

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    title_romaji: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)

    episodes: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[float | None] = mapped_column(Float)
    genres: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    links: Mapped[list["AnimeLink"]] = relationship(
        back_populates="anime", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        # Внешний id уникален только в пределах источника: у AniList и Jikan
        # нумерация разная, и без источника они бы склеивались.
        UniqueConstraint("source", "external_id", name="uq_anime_source_external"),
        CheckConstraint("episodes IS NULL OR episodes >= 0", name="ck_anime_episodes"),
        CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 10)", name="ck_anime_score"
        ),
        Index("ix_anime_title", "title"),
        Index("ix_anime_source_status", "source", "status"),
    )


class AnimeLink(Base):
    """Связь между аниме из разных источников."""

    __tablename__ = "anime_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    anime_id: Mapped[int] = mapped_column(
        ForeignKey("anime.id", ondelete="CASCADE"), nullable=False
    )
    target_source: Mapped[str] = mapped_column(String(32), nullable=False)
    target_external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    relation: Mapped[str] = mapped_column(String(32), nullable=False, default="sequel")

    anime: Mapped[Anime] = relationship(back_populates="links")

    __table_args__ = (
        UniqueConstraint(
            "anime_id", "target_source", "target_external_id", name="uq_link_target"
        ),
        Index("ix_links_target", "target_source", "target_external_id"),
    )


class SyncRun(Base):
    """Журнал запусков синхронизации: что, когда и с каким итогом."""

    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'success', 'failed')", name="ck_sync_run_status"
        ),
        Index("ix_sync_runs_source_started", "source", "started_at"),
    )