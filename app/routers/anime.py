"""CRUD-роутер каталога аниме."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import Anime
from app.schemas import AnimeCreate, AnimeList, AnimeOut, AnimeUpdate
from app.search import build_title_search

router = APIRouter(prefix="/anime", tags=["anime"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=AnimeList, summary="Список аниме с фильтрами")
async def list_anime(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=120)] = None,
    source: Annotated[str | None, Query(max_length=32)] = None,
    genre: Annotated[str | None, Query(max_length=64)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> AnimeList:
    settings = get_settings()
    size = page_size or settings.default_page_size
    # limit пользователя не должен уводить нас в полный дамп таблицы
    size = min(size, settings.max_page_size)

    conditions = []
    search = build_title_search(session.get_bind(), q)
    if search is not None:
        conditions.append(search)
    if source:
        conditions.append(Anime.source == source)
    if genre:
        conditions.append(Anime.genres.ilike(f"%{genre}%"))

    total = int(
        await session.scalar(select(func.count()).select_from(Anime).where(*conditions)) or 0
    )
    rows = await session.scalars(
        select(Anime)
        .where(*conditions)
        .order_by(Anime.id)
        .limit(size)
        .offset((page - 1) * size)
    )

    return AnimeList(
        items=[AnimeOut.model_validate(row) for row in rows.all()],
        total=total,
        page=page,
        page_size=size,
    )


@router.get("/{anime_id}", response_model=AnimeOut, summary="Одна запись")
async def get_anime(anime_id: int, session: SessionDep) -> AnimeOut:
    row = await session.get(Anime, anime_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")
    return AnimeOut.model_validate(row)


@router.post(
    "",
    response_model=AnimeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать запись",
)
async def create_anime(payload: AnimeCreate, session: SessionDep) -> AnimeOut:
    duplicate = await session.scalar(
        select(Anime).where(
            Anime.source == payload.source,
            Anime.external_id == payload.external_id,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Запись с таким source и external_id уже есть",
        )

    row = Anime(**payload.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return AnimeOut.model_validate(row)


@router.patch("/{anime_id}", response_model=AnimeOut, summary="Частичное обновление")
async def update_anime(
    anime_id: int, payload: AnimeUpdate, session: SessionDep
) -> AnimeOut:
    row = await session.get(Anime, anime_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")

    # exclude_unset: не затираем поля, которых клиент не касался
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)

    await session.commit()
    await session.refresh(row)
    return AnimeOut.model_validate(row)


@router.delete(
    "/{anime_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить запись"
)
async def delete_anime(anime_id: int, session: SessionDep) -> None:
    row = await session.get(Anime, anime_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")
    await session.delete(row)
    await session.commit()


@router.get("/-/sources", summary="Сколько записей по источникам")
async def stats_by_source(session: SessionDep) -> dict[str, int]:
    rows = await session.execute(
        select(Anime.source, func.count()).group_by(Anime.source)
    )
    return {source: int(count) for source, count in rows.all()}