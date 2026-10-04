"""Проверка того, на какой БД реально идут тесты.

Отдельным тестом, чтобы нельзя было случайно объявить зелёный прогон
на PostgreSQL, который на самом деле шёл на SQLite.
"""
from __future__ import annotations

import os

from app.search import dialect_name


def test_dialect_matches_environment(session):
    """Диалект тестовой БД обязан совпадать с DATABASE_URL."""
    url = os.environ.get("DATABASE_URL") or "sqlite+aiosqlite:///:memory:"
    expected = "postgresql" if url.startswith("postgresql") else "sqlite"

    bind = session.get_bind()
    assert dialect_name(bind) == expected, (
        f"тесты идут на {dialect_name(bind)}, а DATABASE_URL указывает на {expected}"
    )


def test_postgres_has_fts_index_if_postgres(session):
    """GIN-индекс полнотекстового поиска должен существовать на PostgreSQL."""
    if dialect_name(session.get_bind()) != "postgresql":
        return  # на SQLite этого индекса быть не может, проверка неприменима

    from sqlalchemy import text

    found = session.execute(
        text("SELECT indexname FROM pg_indexes WHERE indexname = 'ix_anime_title_fts'")
    ).scalar()
    assert found == "ix_anime_title_fts", "GIN-индекс полнотекстового поиска не создан миграцией"


def test_postgres_tables_exist_if_postgres(session):
    if dialect_name(session.get_bind()) != "postgresql":
        return

    from sqlalchemy import text

    tables = set(
        session.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars()
    )
    assert {"anime", "anime_links", "sync_runs"} <= tables