"""Create the Phase 01 application schema.

Revision ID: 20260922_0001
Revises: None
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260922_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def upgrade() -> None:
    op.create_table(
        "prompt_templates",
        _id(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(120), nullable=False),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.Column("language_style", sa.String(200)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "model_metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        *_timestamps(),
        sa.UniqueConstraint("name", "version", name="uq_prompt_template_version"),
    )

    op.create_table(
        "content_items",
        _id(),
        sa.Column("external_key", sa.String(100), nullable=False),
        sa.Column("content_type", sa.String(20), nullable=False),
        sa.Column("primary_language", sa.String(30), nullable=False),
        sa.Column("content_pillar", sa.String(120), nullable=False),
        sa.Column("topic", sa.String(250), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="IDEA"),
        sa.Column("risk_classification", sa.String(20), nullable=False, server_default="low"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint("external_key", name="uq_content_items_external_key"),
        sa.CheckConstraint("content_type IN ('poster','reel')", name="ck_content_item_type"),
        sa.CheckConstraint(
            "primary_language IN ('roman_urdu','urdu','simple_english')",
            name="ck_content_item_language",
        ),
        sa.CheckConstraint(
            "status IN ('IDEA','DRAFTED','QA_PASSED','APPROVAL_PENDING',"
            "'CHANGES_REQUESTED','APPROVED','RENDERED','SCHEDULED','PUBLISHING',"
            "'PUBLISHED','FAILED','ARCHIVED')",
            name="ck_content_item_status",
        ),
        sa.CheckConstraint(
            "risk_classification IN ('low','medium','high','restricted')",
            name="ck_content_item_risk",
        ),
    )
    op.create_index("ix_content_items_status", "content_items", ["status"])
    op.create_index("ix_content_items_scheduled_at", "content_items", ["scheduled_at"])
    op.create_index("ix_content_items_created_at", "content_items", ["created_at"])

    op.create_table(
        "content_versions",
        _id(),
        sa.Column(
            "content_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(30), nullable=False),
        sa.Column("title", sa.String(250), nullable=False),
        sa.Column("hook", sa.Text()),
        sa.Column("cta", sa.Text()),
        sa.Column("caption", sa.Text()),
        sa.Column("hashtags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("scene_data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("script_data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "prompt_template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompt_templates.id", ondelete="SET NULL"),
        ),
        sa.Column("model_name", sa.String(120)),
        sa.Column("model_version", sa.String(120)),
        sa.Column("lineage", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
        sa.UniqueConstraint("content_item_id", "version_number", name="uq_content_version_number"),
        sa.CheckConstraint("version_number > 0", name="ck_content_version_positive"),
        sa.CheckConstraint(
            "language IN ('roman_urdu','urdu','simple_english')",
            name="ck_content_version_language",
        ),
    )
    op.create_index(
        "ix_content_versions_item_created", "content_versions", ["content_item_id", "created_at"]
    )

    op.create_table(
        "assets",
        _id(),
        sa.Column(
            "content_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_type", sa.String(30), nullable=False),
        sa.Column("local_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(120)),
        sa.Column("sha256", sa.String(64)),
        sa.Column("temporary_public_url", sa.Text()),
        sa.Column("public_url_expires_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
        sa.CheckConstraint(
            "asset_type IN ('poster','reel','subtitle','audio','thumbnail','source')",
            name="ck_asset_type",
        ),
        sa.CheckConstraint("sha256 IS NULL OR length(sha256) = 64", name="ck_asset_sha256_length"),
    )
    op.create_index("ix_assets_version", "assets", ["content_version_id"])

    op.create_table(
        "approvals",
        _id(),
        sa.Column(
            "content_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("reviewer_reference", sa.String(160), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.CheckConstraint(
            "decision IN ('pending','approved','changes_requested','rejected')",
            name="ck_approval_decision",
        ),
    )
    op.create_index(
        "ix_approvals_version_created", "approvals", ["content_version_id", "created_at"]
    )

    op.create_table(
        "publish_jobs",
        _id(),
        sa.Column(
            "content_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("state", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
        sa.UniqueConstraint("idempotency_key", name="uq_publish_jobs_idempotency_key"),
        sa.CheckConstraint(
            "platform IN ('facebook','instagram','tiktok_handoff')", name="ck_publish_platform"
        ),
        sa.CheckConstraint(
            "state IN ('pending','scheduled','running','retry_wait','succeeded','failed','cancelled')",
            name="ck_publish_job_state",
        ),
        sa.CheckConstraint("retry_count >= 0", name="ck_publish_retry_count"),
    )
    op.create_index("ix_publish_jobs_state", "publish_jobs", ["state"])
    op.create_index("ix_publish_jobs_next_retry", "publish_jobs", ["next_retry_at"])
    op.create_index("ix_publish_jobs_scheduled", "publish_jobs", ["scheduled_at"])
    op.create_index("ix_publish_jobs_created_at", "publish_jobs", ["created_at"])

    op.create_table(
        "published_posts",
        _id(),
        sa.Column(
            "publish_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publish_jobs.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("external_post_id", sa.String(250), nullable=False),
        sa.Column("permalink", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("platform", "external_post_id", name="uq_published_platform_post"),
    )
    op.create_index("ix_published_posts_published_at", "published_posts", ["published_at"])

    op.create_table(
        "metrics_snapshots",
        _id(),
        sa.Column(
            "published_post_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("published_posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
        sa.UniqueConstraint("published_post_id", "captured_at", name="uq_metrics_post_capture"),
    )
    op.create_index("ix_metrics_captured_at", "metrics_snapshots", ["captured_at"])

    op.create_table(
        "comments",
        _id(),
        sa.Column(
            "published_post_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("published_posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("external_comment_id", sa.String(250), nullable=False),
        sa.Column("external_author_reference", sa.String(250)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("risk_classification", sa.String(20), nullable=False, server_default="low"),
        sa.Column("reply_draft", sa.Text()),
        sa.Column("reply_state", sa.String(30), nullable=False, server_default="none"),
        *_timestamps(),
        sa.UniqueConstraint("platform", "external_comment_id", name="uq_comment_platform_external"),
        sa.CheckConstraint(
            "risk_classification IN ('low','medium','high','restricted')",
            name="ck_comment_risk",
        ),
        sa.CheckConstraint(
            "reply_state IN ('none','drafted','review_required','approved','posted','discarded')",
            name="ck_comment_reply_state",
        ),
    )
    op.create_index("ix_comments_imported_at", "comments", ["imported_at"])
    op.create_index("ix_comments_risk", "comments", ["risk_classification"])

    op.create_table(
        "workflow_events",
        _id(),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(80)),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
    )
    op.create_index("ix_workflow_events_correlation", "workflow_events", ["correlation_id"])
    op.create_index(
        "ix_workflow_events_type_created", "workflow_events", ["event_type", "created_at"]
    )

    op.create_table(
        "content_sources",
        _id(),
        sa.Column(
            "content_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("publisher", sa.String(200)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_hash", sa.String(64)),
        sa.Column(
            "verification_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "source_hash IS NULL OR length(source_hash) = 64", name="ck_source_hash_length"
        ),
    )
    op.create_index("ix_content_sources_version", "content_sources", ["content_version_id"])

    op.create_table(
        "approved_facts",
        _id(),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column(
            "content_source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_sources.id", ondelete="SET NULL"),
        ),
        sa.Column("verified_by", sa.String(160), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("risk_classification", sa.String(20), nullable=False, server_default="low"),
        sa.Column(
            "verification_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "risk_classification IN ('low','medium','high','restricted')",
            name="ck_approved_fact_risk",
        ),
    )
    op.create_index("ix_approved_facts_verified_at", "approved_facts", ["verified_at"])

    op.create_table(
        "system_settings",
        _id(),
        sa.Column("key", sa.String(160), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("description", sa.Text()),
        *_timestamps(),
        sa.UniqueConstraint("key", name="uq_system_settings_key"),
    )


def downgrade() -> None:
    op.drop_table("system_settings")
    op.drop_index("ix_approved_facts_verified_at", table_name="approved_facts")
    op.drop_table("approved_facts")
    op.drop_index("ix_content_sources_version", table_name="content_sources")
    op.drop_table("content_sources")
    op.drop_index("ix_workflow_events_type_created", table_name="workflow_events")
    op.drop_index("ix_workflow_events_correlation", table_name="workflow_events")
    op.drop_table("workflow_events")
    op.drop_index("ix_comments_risk", table_name="comments")
    op.drop_index("ix_comments_imported_at", table_name="comments")
    op.drop_table("comments")
    op.drop_index("ix_metrics_captured_at", table_name="metrics_snapshots")
    op.drop_table("metrics_snapshots")
    op.drop_index("ix_published_posts_published_at", table_name="published_posts")
    op.drop_table("published_posts")
    op.drop_index("ix_publish_jobs_created_at", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_scheduled", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_next_retry", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_state", table_name="publish_jobs")
    op.drop_table("publish_jobs")
    op.drop_index("ix_approvals_version_created", table_name="approvals")
    op.drop_table("approvals")
    op.drop_index("ix_assets_version", table_name="assets")
    op.drop_table("assets")
    op.drop_index("ix_content_versions_item_created", table_name="content_versions")
    op.drop_table("content_versions")
    op.drop_index("ix_content_items_created_at", table_name="content_items")
    op.drop_index("ix_content_items_scheduled_at", table_name="content_items")
    op.drop_index("ix_content_items_status", table_name="content_items")
    op.drop_table("content_items")
    op.drop_table("prompt_templates")

