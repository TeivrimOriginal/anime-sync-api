"""Полнотекстовый поиск по названию.

PostgreSQL использует tsvector и индекс GIN, SQLite — LIKE, чтобы тесты
и локальный запуск не требовали установленного сервера. Ветка выбирается
по диалекту подключения, а не по флагу окружения: одна сборка работает в обоих
случаях, и переезд на PostgreSQL не требует правок кода.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import or_, text

# GIN-индекс создаётся только на PostgreSQL.
PG_TSVECTOR_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS ix_anime_title_fts "
    "ON anime USING GIN (to_tsvector('simple', "
    "coalesce(title, '') || ' ' || coalesce(title_romaji, '')))"
)

PG_SEARCH_SQL = (
    "to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(title_romaji, '')) "
    "@@ plainto_tsquery('simple', :q)"
)


def dialect_name(bind: Any) -> str:
    """Имя диалекта подключения ('' — если определить не удалось)."""
    try:
        return bind.dialect.name
    except AttributeError:
        return ""


def build_title_search(bind: Any, query: str | None):
    """Возвращает условие поиска по названию или None, если поиск не задан."""
    if not query or not query.strip():
        return None

    cleaned = query.strip()
    if dialect_name(bind) == "postgresql":
        # LIKE по трём колонкам на PostgreSQL не использует индекс GIN,
        # поэтому здесь полнотекстовый оператор.
        return text(PG_SEARCH_SQL).bindparams(q=cleaned.lower())

    from app.models import Anime

    needle = f"%{cleaned.lower()}%"
    return or_(
        Anime.title.ilike(needle),
        Anime.title_romaji.ilike(needle),
        Anime.genres.ilike(needle),
    )


def create_postgres_fts_index(bind: Any) -> bool:
    """Создаёт GIN-индекс полнотекстового поиска. False, если не PostgreSQL."""
    if dialect_name(bind) != "postgresql":
        return False
    bind.execute(text(PG_TSVECTOR_INDEX_SQL))
    return True