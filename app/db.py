"""Движок и сессия SQLAlchemy 2.0 (async)."""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Общий декларативный базовый класс для всех моделей."""


def make_engine(url: str | None = None):
    """Создаёт async-движок.

    Для SQLite включаем foreign_keys, иначе REFERENCES не проверяется
    и часть тестов проходила бы вхолостую.
    """
    settings = get_settings()
    target = url or settings.database_url
    kwargs: dict = {"echo": False, "future": True}

    if target.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}

    new_engine = create_async_engine(target, **kwargs)

    if target.startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(new_engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return new_engine


engine = make_engine()
SessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI-зависимость: отдаёт сессию на время запроса."""
    async with SessionFactory() as session:
        yield session


async def dispose_engine() -> None:
    """Корректно закрывает пул соединений (нужно при завершении приложения)."""
    await engine.dispose()