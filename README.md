# anime-sync-api

REST API каталога аниме: агрегирует внешние источники, раскладывает в PostgreSQL,
отдаёт список с фильтрами, пагинацией и полнотекстовым поиском.

**Стек:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL 16, Alembic,
Pydantic v2, httpx, Docker, pytest.

---

## Что внутри

| Слой | Файлы | Что делает |
|---|---|---|
| Конфигурация | `app/config.py` | Pydantic Settings, чтение `.env`, дефолт на SQLite |
| База | `app/db.py` | async-движок, фабрика сессий, FastAPI-зависимость |
| Модели | `app/models.py` | `anime`, `anime_links`, `sync_runs`, ограничения и индексы |
| Схемы | `app/schemas.py` | Pydantic v2: create / partial update / paginated list |
| Поиск | `app/search.py` | tsvector + GIN на PostgreSQL, LIKE на SQLite |
| Клиенты | `app/clients.py` | AniList GraphQL и Jikan REST, нормализация в общий формат |
| Логика | `app/services.py` | апсерт, запуск синхронизации, журнал прогонов |
| Роутеры | `app/routers/` | `anime`, `sync`, `health` |
| Миграции | `alembic/` | начальная схема + GIN-индекс |

## Эндпоинты

```
GET    /health                      проверка живости и состояния БД
GET    /api/anime                   список: q, source, genre, page, page_size
GET    /api/anime/{id}              одна запись
POST   /api/anime                   создать (409 при повторе source+external_id)
PATCH  /api/anime/{id}              частичное обновление
DELETE /api/anime/{id}              удалить
GET    /api/anime/-/sources         сколько записей по источникам
POST   /api/sync?source=&limit=     запустить синхронизацию
GET    /api/sync/runs               журнал прогонов
```

Интерактивная документация: `/docs`.

## Запуск

```bash
cp .env.example .env
docker compose up --build
```

Compose поднимает `postgres:16-alpine`, накатывает миграции
(`alembic upgrade head`) и стартует uvicorn на :8000.

Без Docker и без PostgreSQL — на SQLite в памяти:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
uvicorn app.main:app --reload
```

## Тесты

```bash
pytest              # 28 тестов
pytest -v
ruff check app tests alembic
```

Тесты не ходят в сеть: внешние источники подменяются заглушкой `StubClient`,
HTTP проверяется через `httpx.ASGITransport` без сокета и портов.

**Где проверяется PostgreSQL.** Тесты берут БД из `DATABASE_URL`: если там
PostgreSQL — идут против него, иначе берут SQLite в памяти. В CI `DATABASE_URL`
указывает на сервис-контейнер `postgres:16`, поэтому один и тот же набор
тестов реально выполняется против сервера, а не делает вид.

Отдельно перед прогоном выполняется `alembic upgrade head` и проверяется, что
созданы все три таблицы и GIN-индекс `ix_anime_title_fts`. Тест
`test_dialect_matches_environment` падает, если заявленный диалект не совпадает
с `DATABASE_URL` — объявить зелёный прогон на PostgreSQL, который на самом деле
шёл на SQLite, невозможно.

## Принятые решения

**Внешний id уникален в пределах источника.** У AniList и Jikan нумерация разная,
поэтому `UNIQUE (source, external_id)`, а не просто `external_id`.

**Ветка полнотекстового поиска выбирается по диалекту, а не по флагу.** На
PostgreSQL — `to_tsvector @@ plainto_tsquery` с индексом GIN: `LIKE` по трём
колонкам этот индекс не использует. На SQLite — `ILIKE`. Одна сборка работает
в обоих случаях, переезд на PostgreSQL не требует правок кода.

**Ошибка внешнего источника не роняет запрос.** Синхронизация пишет в `sync_runs`
запуск со статусом `failed` и текстом ошибки. Иначе одна недоступность внешнего
API стирала бы всю статистику прогонов.

**Синхронизация идемпотентна.** Повторный запуск обновляет существующие записи, а
не плодит дубли: это проверяется тестом `test_run_sync_second_pass_counts_updates`.

**`PATCH` не затирает неотправленные поля.** Используется `exclude_unset=True`,
поэтому частичное обновление меняет ровно то, что прислал клиент.

**Апсерт сделан на `SELECT` + `INSERT/UPDATE`, а не на `INSERT ... ON CONFLICT`.**
На SQLite и PostgreSQL синтаксис `excluded.*` различается; вариант с двумя
запросами одинаков на обеих СУБД и читается проще.

## Чего нет и почему

* **Аутентификации нет.** Для учебного каталога это лишний слой; в бою потребовался бы
  JWT и проверка прав на запись.
* **Фонового планировщика нет.** Синхронизация запускается ручным `POST /api/sync`.
  Планировщик добавил бы APScheduler и отдельную таблицу расписаний.
* **Связи `anime_links` заполняются, но в эндпоинтах не отдаются.** Поле готово,
  ручное связывание не сделано.
* **Docker не проверен на этой машине** — `docker` и `psql` не установлены.
  Сборка образа и `docker compose up` не запускались, Dockerfile написан по
  стандартной схеме и не фактически собран.

## Автор

Данила Аринов — <teivrim@gmail.com>, <https://github.com/TeivrimOriginal>