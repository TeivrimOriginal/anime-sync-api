"""Проверка живости сервиса и состояния базы."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.schemas import HealthOut
from app.services import count_anime

router = APIRouter(tags=["health"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/health", response_model=HealthOut, summary="Healthcheck")
async def health(session: SessionDep) -> HealthOut:
    settings = get_settings()
    database = "up"
    items = 0
    try:
        await session.execute(text("SELECT 1"))
        items = await count_anime(session)
    except Exception:  # noqa: BLE001 - healthcheck не должен падать
        database = "down"

    return HealthOut(
        status="ok" if database == "up" else "degraded",
        version=settings.app_version,
        database=database,
        items=items,
    )