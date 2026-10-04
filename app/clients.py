"""Клиенты внешних источников: AniList (GraphQL) и Jikan (REST).

Оба клиента на httpx.AsyncClient, с таймаутом и нормализацией ответа
в единый внутренний формат, чтобы сервису не приходилось знать
о различиях источников.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass(slots=True)
class UpstreamAnime:
    """Единое представление записи из любого источника."""

    external_id: str
    title: str
    title_romaji: str | None = None
    description: str | None = None
    episodes: int | None = None
    score: float | None = None
    genres: list[str] = field(default_factory=list)
    status: str = ""


class UpstreamError(RuntimeError):
    """Внешний источник ответил ошибкой или неожиданным телом."""


ANILIST_QUERY = """
query ($page: Int, $perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { hasNextPage }
    media(type: ANIME, sort: POPULARITY_DESC) {
      id
      title { romaji english }
      description(asHtml: false)
      episodes
      averageScore
      status
      genres
    }
  }
}
"""


class AniListClient:
    """AniList GraphQL."""

    source = "anilist"

    def __init__(self, url: str, timeout: float = 20.0) -> None:
        self._url = url
        self._timeout = timeout

    async def fetch(self, limit: int) -> list[UpstreamAnime]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self._url,
                json={"query": ANILIST_QUERY, "variables": {"page": 1, "perPage": limit}},
                headers={"Accept": "application/json"},
            )
            if response.status_code != 200:
                raise UpstreamError(f"anilist: HTTP {response.status_code}")
            payload = response.json()

        media = (payload.get("data") or {}).get("Page", {}).get("media")
        if not isinstance(media, list):
            raise UpstreamError("anilist: неожиданная структура ответа")

        return [self._to_upstream(item) for item in media]

    @staticmethod
    def _to_upstream(item: dict[str, Any]) -> UpstreamAnime:
        title_block = item.get("title") or {}
        description = item.get("description")
        if isinstance(description, str) and description.startswith("<p>"):
            description = description[3:-4] if description.endswith("</p>") else description[3:]
        score = item.get("averageScore")
        return UpstreamAnime(
            external_id=str(item["id"]),
            title=title_block.get("english") or title_block.get("romaji") or "",
            title_romaji=title_block.get("romaji"),
            description=description,
            episodes=item.get("episodes"),
            score=round(score / 10, 1) if isinstance(score, (int, float)) else None,
            genres=list(item.get("genres") or []),
            status=item.get("status") or "",
        )


class JikanClient:
    """Jikan REST API (MyAnimeList-агрегатор)."""

    source = "jikan"

    def __init__(self, url: str, timeout: float = 20.0) -> None:
        self._url = url.rstrip("/")
        self._timeout = timeout

    async def fetch(self, limit: int) -> list[UpstreamAnime]:
        page_size = min(limit, 25)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{self._url}/anime", params={"page": 1, "limit": page_size})
            if response.status_code != 200:
                raise UpstreamError(f"jikan: HTTP {response.status_code}")
            payload = response.json()

        data = payload.get("data")
        if not isinstance(data, list):
            raise UpstreamError("jikan: неожиданная структура ответа")

        return [self._to_upstream(item) for item in data]

    @staticmethod
    def _to_upstream(item: dict[str, Any]) -> UpstreamAnime:
        titles = item.get("titles") or []
        english = next((t["title"] for t in titles if t.get("type") == "English"), None)
        japanese = next((t["title"] for t in titles if t.get("type") == "Japanese"), None)
        score = item.get("score")
        genres = [g["name"] for g in (item.get("genres") or [])]
        episodes = item.get("episodes")
        return UpstreamAnime(
            external_id=str(item["mal_id"]),
            title=english or (titles[0]["title"] if titles else ""),
            title_romaji=japanese,
            description=item.get("synopsis"),
            episodes=episodes if isinstance(episodes, int) else None,
            score=float(score) if isinstance(score, (int, float)) else None,
            genres=genres,
            status=item.get("status") or "",
        )


def build_clients(anilist_url: str, jikan_url: str, timeout: float) -> dict[str, Any]:
    """Возвращает клиенты по имени источника."""
    return {
        "anilist": AniListClient(anilist_url, timeout),
        "jikan": JikanClient(jikan_url, timeout),
    }