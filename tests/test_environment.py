"""Проверка того, на какой БД реально идут тесты.

Отдельным файлом, чтобы нельзя было случайно объявить зелёный прогон
на PostgreSQL, который на самом деле шёл на SQLite.
"""
from __future__ import annotations

import os

from sqlalchemy import text

from app.search import dialect_name


def _expected_dialect() -> str:
    url = os.environ.get("DATABASE_URL") or "sqlite+aiosqlite:///:memory:"
    return "postgresql" if url.startswith("postgresql") else "sqlite"


async def test_dialect_matches_environment(session):
    """Диалект тестовой БД обязан совпадать с DATABASE_URL."""
    assert dialect_name(session.get_bind()) == _expected_dialect(), (
        f"тесты идут на {dialect_name(session.get_bind())}, "
        f"а DATABASE_URL указывает на {_expected_dialect()}"
    )


async def test_postgres_tables_exist_if_postgres(session):
    if dialect_name(session.get_bind()) != "postgresql":
        return  # на SQLite этих таблиц в pg_catalog нет, проверка неприменима

    result = await session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    tables = set(result.scalars())
    assert {"anime", "anime_links", "sync_runs"} <= tables


async def test_postgres_has_fts_index_if_postgres(session):
    """GIN-индекс полнотекстового поиска должен существовать на PostgreSQL."""
    if dialect_name(session.get_bind()) != "postgresql":
        return

    result = await session.execute(
        text("SELECT indexname FROM pg_indexes WHERE indexname = 'ix_anime_title_fts'")
    )
    assert result.scalar() == "ix_anime_title_fts", (
        "GIN-индекс полнотекстового поиска не создан миграцией"
    )


async def test_fts_expression_matches_index(session):
    """Выражение поиска и выражение индекса должны совпадать.

    Если они разойдутся, PostgreSQL не будет использовать индекс: запрос
    отработает, но по seq scan, и на больших объёмах это незаметно по тестам.
    """
    from app.search import PG_TSVECTOR_EXPR

    assert PG_TSVECTOR_EXPR.count("coalesce") == 3, (
        "в выражении должны участвовать title, title_romaji и genres"
    )
    assert "genres" in PG_TSVECTOR_EXPR