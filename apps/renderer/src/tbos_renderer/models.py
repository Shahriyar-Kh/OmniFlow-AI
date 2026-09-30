from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ContentStatus(str, enum.Enum):
    IDEA = "IDEA"
    DRAFTED = "DRAFTED"
    QA_PASSED = "QA_PASSED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    APPROVED = "APPROVED"
    RENDERED = "RENDERED"
    SCHEDULED = "SCHEDULED"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class UuidTimestampMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PromptTemplate(UuidTimestampMixin, Base):
    __tablename__ = "prompt_templates"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_prompt_template_version"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(120), nullable=False)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    language_style: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    model_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ContentItem(UuidTimestampMixin, Base):
    __tablename__ = "content_items"
    __table_args__ = (
        CheckConstraint("content_type IN ('poster','reel')", name="ck_content_item_type"),
        CheckConstraint(
            "primary_language IN ('roman_urdu','urdu','simple_english')",
            name="ck_content_item_language",
        ),
        CheckConstraint(
            "status IN ('IDEA','DRAFTED','QA_PASSED','APPROVAL_PENDING',"
            "'CHANGES_REQUESTED','APPROVED','RENDERED','SCHEDULED','PUBLISHING',"
            "'PUBLISHED','FAILED','ARCHIVED')",
            name="ck_content_item_status",
        ),
        CheckConstraint(
            "risk_classification IN ('low','medium','high','restricted')",
            name="ck_content_item_risk",
        ),
        Index("ix_content_items_status", "status"),
        Index("ix_content_items_scheduled_at", "scheduled_at"),
        Index("ix_content_items_created_at", "created_at"),
    )

    external_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    primary_language: Mapped[str] = mapped_column(String(30), nullable=False)
    content_pillar: Mapped[str] = mapped_column(String(120), nullable=False)
    topic: Mapped[str] = mapped_column(String(250), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default=ContentStatus.IDEA.value, nullable=False
    )
    risk_classification: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContentVersion(UuidTimestampMixin, Base):
    __tablename__ = "content_versions"
    __table_args__ = (
        UniqueConstraint("content_item_id", "version_number", name="uq_content_version_number"),
        CheckConstraint("version_number > 0", name="ck_content_version_positive"),
        CheckConstraint(
            "language IN ('roman_urdu','urdu','simple_english')",
            name="ck_content_version_language",
        ),
        Index("ix_content_versions_item_created", "content_item_id", "created_at"),
    )

    content_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    hook: Mapped[str | None] = mapped_column(Text)
    cta: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    hashtags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    scene_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    script_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    prompt_template_id: Mapped[UUID | None] = mapped_column(ForeignKey("prompt_templates.id"))
    model_name: Mapped[str | None] = mapped_column(String(120))
    model_version: Mapped[str | None] = mapped_column(String(120))
    lineage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Asset(UuidTimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('poster','reel','subtitle','audio','thumbnail','source')",
            name="ck_asset_type",
        ),
        CheckConstraint("sha256 IS NULL OR length(sha256) = 64", name="ck_asset_sha256_length"),
        Index("ix_assets_version", "content_version_id"),
    )

    content_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_versions.id", ondelete="CASCADE"), nullable=False
    )
    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)
    local_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    sha256: Mapped[str | None] = mapped_column(String(64))
    temporary_public_url: Mapped[str | None] = mapped_column(Text)
    public_url_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )


class Approval(UuidTimestampMixin, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('pending','approved','changes_requested','rejected')",
            name="ck_approval_decision",
        ),
        Index("ix_approvals_version_created", "content_version_id", "created_at"),
    )

    content_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_versions.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    reviewer_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PublishJob(UuidTimestampMixin, Base):
    __tablename__ = "publish_jobs"
    __table_args__ = (
        CheckConstraint(
            "platform IN ('facebook','instagram','tiktok_handoff')", name="ck_publish_platform"
        ),
        CheckConstraint(
            "state IN ('pending','scheduled','running','retry_wait','succeeded','failed','cancelled')",  # noqa: E501
            name="ck_publish_job_state",
        ),
        CheckConstraint("retry_count >= 0", name="ck_publish_retry_count"),
        Index("ix_publish_jobs_state", "state"),
        Index("ix_publish_jobs_next_retry", "next_retry_at"),
        Index("ix_publish_jobs_scheduled", "scheduled_at"),
        Index("ix_publish_jobs_created_at", "created_at"),
    )

    content_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_versions.id", ondelete="RESTRICT"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(30), nullable=False)
    state: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class PublishedPost(UuidTimestampMixin, Base):
    __tablename__ = "published_posts"
    __table_args__ = (
        UniqueConstraint("platform", "external_post_id", name="uq_published_platform_post"),
        Index("ix_published_posts_published_at", "published_at"),
    )

    publish_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("publish_jobs.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    platform: Mapped[str] = mapped_column(String(30), nullable=False)
    external_post_id: Mapped[str] = mapped_column(String(250), nullable=False)
    permalink: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MetricsSnapshot(UuidTimestampMixin, Base):
    __tablename__ = "metrics_snapshots"
    __table_args__ = (
        UniqueConstraint("published_post_id", "captured_at", name="uq_metrics_post_capture"),
        Index("ix_metrics_captured_at", "captured_at"),
    )

    published_post_id: Mapped[UUID] = mapped_column(
        ForeignKey("published_posts.id", ondelete="CASCADE"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Comment(UuidTimestampMixin, Base):
    __tablename__ = "comments"
    __table_args__ = (
        UniqueConstraint("platform", "external_comment_id", name="uq_comment_platform_external"),
        CheckConstraint(
            "risk_classification IN ('low','medium','high','restricted')",
            name="ck_comment_risk",
        ),
        CheckConstraint(
            "reply_state IN ('none','drafted','review_required','approved','posted','discarded')",
            name="ck_comment_reply_state",
        ),
        Index("ix_comments_imported_at", "imported_at"),
        Index("ix_comments_risk", "risk_classification"),
    )

    published_post_id: Mapped[UUID] = mapped_column(
        ForeignKey("published_posts.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(30), nullable=False)
    external_comment_id: Mapped[str] = mapped_column(String(250), nullable=False)
    external_author_reference: Mapped[str | None] = mapped_column(String(250))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    risk_classification: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    reply_draft: Mapped[str | None] = mapped_column(Text)
    reply_state: Mapped[str] = mapped_column(String(30), default="none", nullable=False)


class WorkflowEvent(UuidTimestampMixin, Base):
    __tablename__ = "workflow_events"
    __table_args__ = (
        Index("ix_workflow_events_correlation", "correlation_id"),
        Index("ix_workflow_events_type_created", "event_type", "created_at"),
    )

    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(80))
    entity_id: Mapped[UUID | None] = mapped_column()
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ContentSource(UuidTimestampMixin, Base):
    __tablename__ = "content_sources"
    __table_args__ = (Index("ix_content_sources_version", "content_version_id"),)

    content_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_versions.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(200))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_hash: Mapped[str | None] = mapped_column(String(64))
    verification_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )


class ApprovedFact(UuidTimestampMixin, Base):
    __tablename__ = "approved_facts"
    __table_args__ = (
        CheckConstraint(
            "risk_classification IN ('low','medium','high','restricted')",
            name="ck_approved_fact_risk",
        ),
        Index("ix_approved_facts_verified_at", "verified_at"),
    )

    statement: Mapped[str] = mapped_column(Text, nullable=False)
    content_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("content_sources.id", ondelete="SET NULL")
    )
    verified_by: Mapped[str] = mapped_column(String(160), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    risk_classification: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    verification_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )


class SystemSetting(UuidTimestampMixin, Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
