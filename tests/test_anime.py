"""Тесты каталога: CRUD, фильтры, пагинация, полнотекстовый поиск."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

NEW = {
    "source": "anilist",
    "external_id": "1",
    "title": "Cowboy Bebop",
    "title_romaji": "Cowboy Bebop",
    "episodes": 26,
    "score": 8.75,
    "genres": "Action, Drama, Sci-Fi",
    "status": "FINISHED",
    "description": "Bounty hunters in space.",
}


async def test_create_and_read(client):
    created = await client.post("/api/anime", json=NEW)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["title"] == "Cowboy Bebop"
    assert body["id"] > 0

    fetched = await client.get(f"/api/anime/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["source"] == "anilist"


async def test_duplicate_external_id_is_rejected(client):
    first = await client.post("/api/anime", json=NEW)
    assert first.status_code == 201

    second = await client.post("/api/anime", json=NEW)
    assert second.status_code == 409
    assert "external_id" in second.json()["detail"]


async def test_same_external_id_from_another_source_is_allowed(client):
    first = await client.post("/api/anime", json=NEW)
    assert first.status_code == 201

    other = dict(NEW, source="jikan")
    second = await client.post("/api/anime", json=other)
    assert second.status_code == 201, "внешний id уникален только в пределах источника"


async def test_validation_rejects_bad_score(client):
    bad = dict(NEW, score=99)
    response = await client.post("/api/anime", json=bad)
    assert response.status_code == 422


async def test_validation_rejects_empty_title(client):
    bad = dict(NEW, title="")
    response = await client.post("/api/anime", json=bad)
    assert response.status_code == 422


async def test_patch_updates_only_given_fields(client):
    created = await client.post("/api/anime", json=NEW)
    anime_id = created.json()["id"]

    patched = await client.patch(f"/api/anime/{anime_id}", json={"status": "RELEASING"})
    assert patched.status_code == 200
    body = patched.json()
    assert body["status"] == "RELEASING"
    # остальные поля не затерлись
    assert body["title"] == "Cowboy Bebop"
    assert body["episodes"] == 26


async def test_delete_then_404(client):
    created = await client.post("/api/anime", json=NEW)
    anime_id = created.json()["id"]

    deleted = await client.delete(f"/api/anime/{anime_id}")
    assert deleted.status_code == 204

    missing = await client.get(f"/api/anime/{anime_id}")
    assert missing.status_code == 404


async def test_search_by_title(client):
    await client.post("/api/anime", json=NEW)
    # romaji задаём свой, иначе поиск по названию найдёт первую запись
    await client.post(
        "/api/anime",
        json=dict(NEW, external_id="2", title="Trigun", title_romaji="Trigun"),
    )

    found = await client.get("/api/anime", params={"q": "bebop"})
    assert found.status_code == 200
    body = found.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Cowboy Bebop"


async def test_search_is_case_insensitive(client):
    await client.post("/api/anime", json=NEW)
    found = await client.get("/api/anime", params={"q": "COWBOY"})
    assert found.json()["total"] == 1


async def test_search_by_genre(client):
    await client.post("/api/anime", json=NEW)
    found = await client.get("/api/anime", params={"q": "Drama"})
    assert found.json()["total"] == 1


async def test_filter_by_source(client):
    await client.post("/api/anime", json=NEW)
    await client.post("/api/anime", json=dict(NEW, source="jikan", title="Only Jikan"))

    only_jikan = await client.get("/api/anime", params={"source": "jikan"})
    body = only_jikan.json()
    assert body["total"] == 1
    assert body["items"][0]["source"] == "jikan"


async def test_pagination_splits_results(client):
    for index in range(5):
        await client.post("/api/anime", json=dict(NEW, external_id=str(index), title=f"Title {index}"))

    first = await client.get("/api/anime", params={"page": 1, "page_size": 2})
    second = await client.get("/api/anime", params={"page": 2, "page_size": 2})

    assert first.json()["total"] == 5
    assert len(first.json()["items"]) == 2
    assert len(second.json()["items"]) == 2
    first_ids = {item["id"] for item in first.json()["items"]}
    second_ids = {item["id"] for item in second.json()["items"]}
    assert not (first_ids & second_ids), "страницы не должны пересекаться"


async def test_page_size_is_capped(client):
    response = await client.get("/api/anime", params={"page_size": 100000})
    assert response.status_code == 200
    assert response.json()["page_size"] <= 100


async def test_negative_page_rejected(client):
    response = await client.get("/api/anime", params={"page": 0})
    assert response.status_code == 422


async def test_stats_by_source(client):
    await client.post("/api/anime", json=NEW)
    await client.post("/api/anime", json=dict(NEW, source="jikan"))

    response = await client.get("/api/anime/-/sources")
    assert response.status_code == 200
    assert response.json() == {"anilist": 1, "jikan": 1}


async def test_health_reports_item_count(client):
    await client.post("/api/anime", json=NEW)
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] == "up"
    assert body["items"] == 1