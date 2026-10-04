"""Роутер синхронизации с внешними источниками."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import build_clients
from app.config import get_settings
from app.db import get_session
from app.models import SyncRun
from app.schemas import SyncResult, SyncRunOut
from app.services import run_sync

router = APIRouter(prefix="/sync", tags=["sync"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=SyncResult, summary="Запустить синхронизацию")
async def trigger_sync(
    session: SessionDep,
    source: Annotated[str, Query(max_length=32)] = "anilist",
    limit: Annotated[int | None, Query(ge=1, le=500)] = None,
) -> SyncResult:
    settings = get_settings()
    clients = build_clients(settings.anilist_url, settings.jikan_url, settings.request_timeout)
    client = clients.get(source)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неизвестный источник: {source}. Доступны: {sorted(clients)}",
        )

    batch = limit or settings.sync_batch_size
    return await run_sync(session, source, client, batch)


@router.get("/runs", response_model=list[SyncRunOut], summary="История запусков")
async def list_runs(
    session: SessionDep,
    source: Annotated[str | None, Query(max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[SyncRunOut]:
    stmt = select(SyncRun).order_by(SyncRun.id.desc()).limit(limit)
    if source:
        stmt = stmt.where(SyncRun.source == source)
    rows = await session.scalars(stmt)
    return [SyncRunOut.model_validate(row) for row in rows.all()]