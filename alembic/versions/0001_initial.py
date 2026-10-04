"""Начальная схема: anime, anime_links, sync_runs + полнотекстовый индекс.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "anime",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("title_romaji", sa.String(length=512)),
        sa.Column("description", sa.Text()),
        sa.Column("episodes", sa.Integer()),
        sa.Column("score", sa.Float()),
        sa.Column("genres", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("source", "external_id", name="uq_anime_source_external"),
        sa.CheckConstraint("episodes IS NULL OR episodes >= 0", name="ck_anime_episodes"),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 10)", name="ck_anime_score"
        ),
    )
    op.create_index("ix_anime_title", "anime", ["title"])
    op.create_index("ix_anime_source_status", "anime", ["source", "status"])

    op.create_table(
        "anime_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "anime_id",
            sa.Integer(),
            sa.ForeignKey("anime.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_source", sa.String(length=32), nullable=False),
        sa.Column("target_external_id", sa.String(length=64), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=False, server_default="sequel"),
        sa.UniqueConstraint(
            "anime_id", "target_source", "target_external_id", name="uq_link_target"
        ),
    )
    op.create_index(
        "ix_links_target", "anime_links", ["target_source", "target_external_id"]
    )

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
        sa.Column("fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'failed')", name="ck_sync_run_status"
        ),
    )
    op.create_index("ix_sync_runs_source_started", "sync_runs", ["source", "started_at"])

    # Полнотекстовый индекс только на PostgreSQL: GIN поверх tsvector.
    # Выражение обязано совпадать с app.search.PG_SEARCH_SQL, иначе индекс
    # не будет использоваться планировщиком запросов.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_anime_title_fts ON anime USING GIN "
            "(to_tsvector('simple', "
            "coalesce(title, '') || ' ' || coalesce(title_romaji, '') || ' ' || "
            "coalesce(genres, '')))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_anime_title_fts")
    op.drop_index("ix_sync_runs_source_started", table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_index("ix_links_target", table_name="anime_links")
    op.drop_table("anime_links")
    op.drop_index("ix_anime_source_status", table_name="anime")
    op.drop_index("ix_anime_title", table_name="anime")
    op.drop_table("anime")