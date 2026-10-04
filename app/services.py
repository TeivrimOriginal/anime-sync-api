"""Сервисный слой: апсерт аниме и запуск синхронизации."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import UpstreamAnime
from app.models import Anime, SyncRun
from app.schemas import SyncResult


async def upsert_anime(session: AsyncSession, item: UpstreamAnime, source: str) -> str:
    """Создаёт или обновляет запись. Возвращает 'created' или 'updated'."""
    existing = await session.scalar(
        select(Anime).where(
            Anime.source == source, Anime.external_id == item.external_id
        )
    )

    payload = {
        "title": item.title,
        "title_romaji": item.title_romaji,
        "description": item.description,
        "episodes": item.episodes,
        "score": item.score,
        "genres": ", ".join(item.genres)[:256],
        "status": item.status[:32],
    }

    if existing is None:
        session.add(Anime(source=source, external_id=item.external_id, **payload))
        return "created"

    for key, value in payload.items():
        setattr(existing, key, value)
    return "updated"


async def run_sync(
    session: AsyncSession,
    source: str,
    client,
    limit: int,
) -> SyncResult:
    """Забирает данные из источника и раскладывает по таблице.

    Источник недоступен -- не роняем запрос, а пишем неуспешный запуск в журнал:
    иначе одна недоступность внешнего API стирала бы всю статистику синхронизаций.
    """
    run = SyncRun(source=source, status="running", fetched=0)
    session.add(run)
    await session.commit()

    counts = {"created": 0, "updated": 0, "skipped": 0}
    try:
        items = await client.fetch(limit)
        run.fetched = len(items)
        for item in items:
            if not item.external_id or not item.title:
                counts["skipped"] += 1
                continue
            action = await upsert_anime(session, item, source)
            counts[action] += 1
        run.status = "success"
    except Exception as exc:  # noqa: BLE001 - внешний источник может упасть как угодно
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"[:2000]
        await session.commit()
        return SyncResult(run=_to_out(run), processed=0)

    run.created = counts["created"]
    run.updated = counts["updated"]
    run.skipped = counts["skipped"]
    run.finished_at = datetime.now(timezone.utc)
    await session.commit()
    return SyncResult(run=_to_out(run), processed=run.fetched)


def _to_out(run: SyncRun):
    from app.schemas import SyncRunOut

    return SyncRunOut.model_validate(run)


async def count_anime(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(Anime)) or 0)