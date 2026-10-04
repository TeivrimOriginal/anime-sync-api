"""Тесты синхронизации: успешный запуск, повторный апсерт, недоступный источник.

Сеть в тестах не используется: внешние клиенты подменяются заглушкой,
которая отдаёт заранее заданный ответ и умеет падать по требованию.
"""
from __future__ import annotations

from typing import Iterable

import pytest

from app.clients import UpstreamAnime, UpstreamError

pytestmark = pytest.mark.asyncio

SAMPLE: list[UpstreamAnime] = [
    UpstreamAnime(
        external_id="1",
        title="Cowboy Bebop",
        title_romaji="Cowboy Bebop",
        episodes=26,
        score=8.8,
        genres=["Action", "Drama"],
        status="FINISHED",
    ),
    UpstreamAnime(
        external_id="2",
        title="Trigun",
        title_romaji="Trigun Stampede",
        episodes=36,
        score=8.3,
        genres=["Action", "Sci-Fi"],
        status="FINISHED",
    ),
]


class StubClient:
    """Заглушка внешнего источника."""

    source = "stub"

    def __init__(self, items: Iterable[UpstreamAnime] | None = None, error: Exception | None = None):
        self._items = list(items or [])
        self._error = error
        self.calls: list[int] = []

    async def fetch(self, limit: int) -> list[UpstreamAnime]:
        self.calls.append(limit)
        if self._error is not None:
            raise self._error
        return self._items[:limit]


async def test_upsert_inserts_then_updates(session):
    from app.services import upsert_anime

    first = await upsert_anime(session, SAMPLE[0], "anilist")
    await session.commit()
    assert first == "created"

    changed = SAMPLE[0]
    changed.title = "Cowboy Bebop (remaster)"
    second = await upsert_anime(session, changed, "anilist")
    await session.commit()
    assert second == "updated"

    from sqlalchemy import func, select

    from app.models import Anime

    total = await session.scalar(select(func.count()).select_from(Anime))
    assert total == 1, "повторный апсерт не должен плодить дубли"


async def test_run_sync_success(session, monkeypatch):
    from app import services

    stub = StubClient(SAMPLE)
    monkeypatch.setattr(services, "run_sync", services.run_sync)  # noqa: F841
    result = await services.run_sync(session, "anilist", stub, limit=10)

    assert result.run.status == "success"
    assert result.run.fetched == 2
    assert result.run.created == 2
    assert result.run.updated == 0
    assert stub.calls == [10]


async def test_run_sync_second_pass_counts_updates(session):
    from app import services

    await services.run_sync(session, "anilist", StubClient(SAMPLE), limit=10)
    second = await services.run_sync(session, "anilist", StubClient(SAMPLE), limit=10)

    assert second.run.created == 0
    assert second.run.updated == 2


async def test_run_sync_records_failure(session):
    from app import services

    broken = StubClient(error=UpstreamError("jikan: HTTP 503"))
    result = await services.run_sync(session, "jikan", broken, limit=5)

    assert result.run.status == "failed"
    assert "HTTP 503" in result.run.error


async def test_run_sync_skips_records_without_id(session):
    from app import services

    stub = StubClient([UpstreamAnime(external_id="", title="Без id"), SAMPLE[0]])
    result = await services.run_sync(session, "anilist", stub, limit=10)

    assert result.run.status == "success"
    assert result.run.skipped == 1
    assert result.run.created == 1


async def test_runs_history_is_paginated(session, client):
    from app import services

    await services.run_sync(session, "anilist", StubClient(SAMPLE[:1]), limit=1)
    await services.run_sync(session, "jikan", StubClient(SAMPLE[:1]), limit=1)

    response = await client.get("/api/sync/runs", params={"limit": 1})
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_unknown_source_is_rejected(client):
    response = await client.post("/api/sync", params={"source": "нетакого"})
    assert response.status_code == 400


async def test_anilist_client_maps_payload():
    from app.clients import AniListClient

    payload = {
        "data": {
            "Page": {
                "media": [
                    {
                        "id": 1,
                        "title": {"english": "Cowboy Bebop", "romaji": "Cowboy Bebop"},
                        "description": "<p>Bounty hunters.</p>",
                        "episodes": 26,
                        "averageScore": 88,
                        "status": "FINISHED",
                        "genres": ["Action", "Drama"],
                    }
                ]
            }
        }
    }
    mapped = AniListClient._to_upstream(payload["data"]["Page"]["media"][0])

    assert mapped.external_id == "1"
    assert mapped.title == "Cowboy Bebop"
    assert mapped.description == "Bounty hunters.", "HTML-обёртка должна быть срезана"
    assert mapped.score == 8.8, "средний балл 0-100 приводим к шкале 0-10"


async def test_jikan_client_maps_payload():
    from app.clients import JikanClient

    payload = {
        "mal_id": 1,
        "titles": [
            {"type": "English", "title": "Cowboy Bebop"},
            {"type": "Japanese", "title": "カウボーイビバップ"},
        ],
        "synopsis": "Bounty hunters.",
        "episodes": 26,
        "score": 8.75,
        "genres": [{"name": "Action"}],
        "status": "Finished Airing",
    }
    mapped = JikanClient._to_upstream(payload)

    assert mapped.external_id == "1"
    assert mapped.title == "Cowboy Bebop"
    assert mapped.genres == ["Action"]
    assert mapped.episodes == 26