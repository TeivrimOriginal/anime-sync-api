"""Точка входа FastAPI."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import Base, engine
from app.routers import anime, health, sync

logger = logging.getLogger("anime_sync_api")
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Создаёт таблицы на старте и закрывает пул соединений на остановке.

    ``create_all`` здесь осознанно: для локального запуска и тестов этого
    достаточно, а в Docker схему создаёт Alembic-миграция.
    """
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    logger.info("старт %s v%s", settings.app_name, settings.app_version)
    yield
    await engine.dispose()
    logger.info("останов")


app = FastAPI(
    title="anime-sync-api",
    version=settings.app_version,
    description=(
        "REST API каталога аниме: агрегация внешних источников, "
        "фильтры, полнотекстовый поиск, пагинация."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(anime.router, prefix=settings.api_prefix)
app.include_router(sync.router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": settings.app_name, "docs": "/docs", "version": settings.app_version}