from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from tbos_renderer.config import Settings
from tbos_renderer.content_engine.repository import ContentRepository
from tbos_renderer.models import (
    Asset,
    ContentItem,
    ContentStatus,
    ContentVersion,
    PublishedPost,
    PublishJob,
)
from tbos_renderer.publishing.meta import MetaGraphPublisher
from tbos_renderer.publishing.schemas import (
    HandoffPackageResult,
    PublishedPostResponse,
    PublishJobExecutionResult,
    PublishResult,
)
from tbos_renderer.publishing.tiktok import TikTokHandoffPackager

LOGGER = logging.getLogger(__name__)


class PublishingService:
    """Orchestrates multi-platform publishing, retries, and persistence."""

    def __init__(
        self,
        settings: Settings,
        repository: ContentRepository,
        meta_publisher: MetaGraphPublisher | None = None,
        tiktok_packager: TikTokHandoffPackager | None = None,
        max_job_retries: int = 3,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.meta_publisher = meta_publisher or MetaGraphPublisher(settings)
        self.tiktok_packager = tiktok_packager or TikTokHandoffPackager(settings)
        self.max_job_retries = max_job_retries

    async def execute_publish_job(self, job_id: UUID) -> PublishJobExecutionResult:
        """Execute a specific publishing job with idempotency and retry protection."""
        with self.repository.session() as session, session.begin():
            job = session.get(PublishJob, job_id)
            if job is None:
                raise ValueError(f"Publish job {job_id} not found.")

            # Idempotency safety: if job already succeeded, return existing post without duplicating
            if job.state == "succeeded":
                existing_post = session.scalar(
                    select(PublishedPost).where(PublishedPost.publish_job_id == job_id)
                )
                return PublishJobExecutionResult(
                    job_id=job.id,
                    status="succeeded",
                    platform=job.platform,
                    published_post_id=existing_post.id if existing_post else None,
                    external_post_id=existing_post.external_post_id if existing_post else None,
                    permalink=existing_post.permalink if existing_post else None,
                )

            version = session.get(ContentVersion, job.content_version_id)
            if version is None:
                raise ValueError(f"Content version {job.content_version_id} not found.")

            item = session.get(ContentItem, version.content_item_id)
            if item is None:
                raise ValueError(f"Content item {version.content_item_id} not found.")

            assets = session.scalars(
                select(Asset).where(Asset.content_version_id == version.id)
            ).all()

            job.state = "running"
            item.status = ContentStatus.PUBLISHING.value
            session.flush()

        # Execute publishing outside transaction to prevent holding database locks
        # during network I/O
        try:
            publish_result = await self._dispatch_platform(job, version, item, assets)
        except Exception as exc:
            LOGGER.exception("Publish job %s failed: %s", job_id, exc)
            return self._handle_job_failure(job_id, exc)

        # Record success inside transaction
        with self.repository.session() as session, session.begin():
            job = session.get(PublishJob, job_id)
            if job is None:
                raise ValueError(f"Publish job {job_id} missing during completion.")

            post = PublishedPost(
                publish_job_id=job.id,
                platform=publish_result.platform,
                external_post_id=publish_result.external_post_id,
                permalink=publish_result.permalink,
                published_at=publish_result.published_at,
            )
            session.add(post)
            session.flush()

            job.state = "succeeded"
            job.last_error = None

            # Check if all sibling jobs for this content version have succeeded
            sibling_jobs = session.scalars(
                select(PublishJob).where(PublishJob.content_version_id == version.id)
            ).all()
            all_succeeded = all(j.state == "succeeded" for j in sibling_jobs)

            if all_succeeded:
                item = session.get(ContentItem, version.content_item_id)
                if item:
                    item.status = ContentStatus.PUBLISHED.value

            return PublishJobExecutionResult(
                job_id=job.id,
                status="succeeded",
                platform=job.platform,
                published_post_id=post.id,
                external_post_id=post.external_post_id,
                permalink=post.permalink,
            )

    async def _dispatch_platform(
        self,
        job: PublishJob,
        version: ContentVersion,
        item: ContentItem,
        assets: Sequence[Asset],
    ) -> PublishResult:
        is_reel = item.content_type == "reel"
        target_type = "reel" if is_reel else "poster"
        primary_asset = next((a for a in assets if a.asset_type == target_type), None)
        if not primary_asset and assets:
            primary_asset = assets[0]

        if not primary_asset or not Path(primary_asset.local_path).exists():
            raise FileNotFoundError(
                f"Rendered media asset for version {version.id} was not found on disk."
            )

        caption = version.caption or version.hook or version.title

        if job.platform == "facebook":
            return await self.meta_publisher.publish_facebook(
                media_path=primary_asset.local_path,
                caption=caption,
                is_video=is_reel,
            )

        if job.platform == "instagram":
            media_url = (
                primary_asset.temporary_public_url
                or f"http://renderer-api:8080/api/v1/assets/{primary_asset.id}/download"
            )
            return await self.meta_publisher.publish_instagram(
                media_url=media_url,
                caption=caption,
                is_video=is_reel,
            )

        if job.platform == "tiktok_handoff":
            thumb_asset = next((a for a in assets if a.asset_type == "thumbnail"), None)
            thumb_path = thumb_asset.local_path if thumb_asset else None
            handoff = self.tiktok_packager.create_handoff_package(
                content_id=item.id,
                version=version,
                video_source_path=primary_asset.local_path,
                thumbnail_source_path=thumb_path,
            )
            return PublishResult(
                platform="tiktok_handoff",
                external_post_id=f"handoff:{job.id}",
                permalink=handoff.bundle_dir,
                published_at=datetime.now(UTC),
                metadata={"bundle_dir": handoff.bundle_dir, "caption": handoff.ready_caption},
            )

        raise ValueError(f"Unsupported publish platform: {job.platform}")

    def _handle_job_failure(self, job_id: UUID, error: Exception) -> PublishJobExecutionResult:
        with self.repository.session() as session, session.begin():
            job = session.get(PublishJob, job_id)
            if job is None:
                raise ValueError(f"Publish job {job_id} not found.")

            job.retry_count += 1
            job.last_error = str(error)

            if job.retry_count < self.max_job_retries:
                job.state = "retry_wait"
                backoff_seconds = min(300, (2**job.retry_count) * 5)
                job.next_retry_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds)
            else:
                job.state = "failed"

            return PublishJobExecutionResult(
                job_id=job.id,
                status=job.state,
                platform=job.platform,
                error=str(error),
            )

    async def process_pending_jobs(self) -> list[PublishJobExecutionResult]:
        """Process all jobs that are pending or ready for retry."""
        now = datetime.now(UTC)
        with self.repository.session() as session:
            stmt = select(PublishJob.id).where(
                (PublishJob.state == "pending")
                | ((PublishJob.state == "retry_wait") & (PublishJob.next_retry_at <= now))
            )
            job_ids = session.scalars(stmt).all()

        results: list[PublishJobExecutionResult] = []
        for j_id in job_ids:
            res = await self.execute_publish_job(j_id)
            results.append(res)
        return results

    def list_published_posts(self, platform: str | None = None) -> list[PublishedPostResponse]:
        with self.repository.session() as session:
            stmt = select(PublishedPost)
            if platform:
                stmt = stmt.where(PublishedPost.platform == platform)
            stmt = stmt.order_by(PublishedPost.published_at.desc())
            records = session.scalars(stmt).all()
            return [
                PublishedPostResponse(
                    id=p.id,
                    publish_job_id=p.publish_job_id,
                    platform=p.platform,
                    external_post_id=p.external_post_id,
                    permalink=p.permalink,
                    published_at=p.published_at,
                    created_at=p.created_at,
                )
                for p in records
            ]

    def create_tiktok_handoff_for_content(self, content_id: UUID) -> HandoffPackageResult:
        with self.repository.session() as session:
            item = session.get(ContentItem, content_id)
            if not item:
                raise ValueError(f"Content item {content_id} not found.")

            version = session.scalar(
                select(ContentVersion)
                .where(ContentVersion.content_item_id == content_id)
                .order_by(ContentVersion.version_number.desc())
            )
            if not version:
                raise ValueError(f"No version found for content {content_id}.")

            assets = session.scalars(
                select(Asset).where(Asset.content_version_id == version.id)
            ).all()

            reel_asset = next((a for a in assets if a.asset_type == "reel"), None)
            if not reel_asset:
                if assets:
                    reel_asset = assets[0]
                else:
                    raise ValueError(f"No media asset found for content {content_id}.")

            thumb_asset = next((a for a in assets if a.asset_type == "thumbnail"), None)
            thumb_path = thumb_asset.local_path if thumb_asset else None

            return self.tiktok_packager.create_handoff_package(
                content_id=content_id,
                version=version,
                video_source_path=reel_asset.local_path,
                thumbnail_source_path=thumb_path,
            )
