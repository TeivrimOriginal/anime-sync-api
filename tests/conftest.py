"""Фикстуры pytest.

БД выбирается из переменной DATABASE_URL:
- если она указывает на PostgreSQL (в CI это сервис-контейнер), тесты идут
  против настоящего сервера;
- иначе используется SQLite в памяти, чтобы набор можно было гонять
  без установленного PostgreSQL.

Брать SQLite «на автомате» нельзя: тогда шаг CI с названием «Тесты на PostgreSQL»
тестировал бы SQLite и проверка была бы фикцией.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base, get_session
from app.main import app

DEFAULT_TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


def test_db_url() -> str:
    return os.environ.get("DATABASE_URL") or DEFAULT_TEST_DB_URL


@pytest_asyncio.fixture
async def engine():
    """Движок тестовой БД: схема создаётся один раз на прогон."""
    url = test_db_url()
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}

    test_engine = create_async_engine(url, **kwargs)

    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


async def _clean(engine) -> None:
    """Очищает таблицы перед каждым тестом.

    На SQLite в памяти база и так новая на каждый тест, но на PostgreSQL это
    общий сервер: без очистки данные прошлого теста протекают в следующий, и
    падают проверки вроде «после двух вставок их ровно две». Заметно только
    на сервере, поэтому очистка обязательна, а не косметика.
    """
    from sqlalchemy import text

    url = test_db_url()
    if url.startswith("postgresql"):
        statements = (
            "TRUNCATE TABLE anime_links, sync_runs, anime RESTART IDENTITY CASCADE",
        )
    else:
        statements = (
            "DELETE FROM anime_links",
            "DELETE FROM sync_runs",
            "DELETE FROM anime",
        )

    async with engine.begin() as connection:
        for statement in statements:
            await connection.execute(text(statement))


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    await _clean(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """HTTP-клиент поверх ASGI-приложения, без сокета и портов."""

    async def _override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    app.dependency_overrides.clear()