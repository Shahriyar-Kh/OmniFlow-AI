from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from tbos_renderer.config import BrandConfig, Settings, load_brand_config
from tbos_renderer.content_engine.exceptions import ContentNotFoundError
from tbos_renderer.content_engine.repository import ContentRepository
from tbos_renderer.content_engine.schemas import PosterContent, ReelContent
from tbos_renderer.models import Asset, ContentItem, ContentVersion
from tbos_renderer.rendering.poster import PosterRenderer
from tbos_renderer.rendering.schemas import AssetResponse, RenderResultResponse
from tbos_renderer.rendering.video import FfmpegVideoCompositor, VideoCompositorEngine
from tbos_renderer.rendering.voiceover import EdgeTtsVoiceoverEngine, VoiceoverEngine

LOGGER = logging.getLogger(__name__)


class RenderingService:
    """Service orchestrating Poster and Reel rendering, storage, and asset persistence."""

    def __init__(
        self,
        settings: Settings,
        repository: ContentRepository,
        *,
        brand_config: BrandConfig | None = None,
        voiceover_engine: VoiceoverEngine | None = None,
        video_compositor: VideoCompositorEngine | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.brand_config = brand_config or load_brand_config(settings.brand_config_path)
        self.poster_renderer = PosterRenderer(self.brand_config)
        self.voiceover_engine = voiceover_engine or EdgeTtsVoiceoverEngine()
        self.video_compositor = video_compositor or FfmpegVideoCompositor(self.brand_config)

    def _get_storage_dir(self, content_id: UUID, version_number: int) -> Path:
        base = (
            self.settings.shared_storage_path / "renders" / str(content_id) / f"v{version_number}"
        )
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _to_asset_response(self, asset: Asset) -> AssetResponse:
        return AssetResponse(
            id=asset.id,
            content_version_id=asset.content_version_id,
            asset_type=asset.asset_type,
            local_path=asset.local_path,
            mime_type=asset.mime_type,
            sha256=asset.sha256,
            temporary_public_url=asset.temporary_public_url,
            public_url_expires_at=asset.public_url_expires_at,
            metadata=asset.metadata_json,
            created_at=asset.created_at,
        )

    async def render(
        self,
        content_id: UUID,
        version_number: int | None = None,
        *,
        force: bool = False,
    ) -> RenderResultResponse:
        """Render media assets for a given content item and version."""
        with self.repository.session() as session, session.begin():
            item = session.get(ContentItem, content_id)
            if item is None:
                raise ContentNotFoundError(f"Content item {content_id} not found.")

            if version_number is not None:
                version = session.scalar(
                    select(ContentVersion).where(
                        ContentVersion.content_item_id == content_id,
                        ContentVersion.version_number == version_number,
                    )
                )
            else:
                version = session.scalar(
                    select(ContentVersion)
                    .where(ContentVersion.content_item_id == content_id)
                    .order_by(ContentVersion.version_number.desc())
                )

            if version is None:
                raise ContentNotFoundError(f"Content version for item {content_id} was not found.")

            content = ContentRepository._parse_content(version)
            storage_dir = self._get_storage_dir(content_id, version.version_number)
            created_assets: list[Asset] = []

            if isinstance(content, PosterContent):
                poster_path = storage_dir / "poster.png"
                meta = self.poster_renderer.render_to_file(content, poster_path)
                asset = self._upsert_asset(
                    session=session,
                    content_version_id=version.id,
                    asset_type="poster",
                    local_path=str(poster_path),
                    mime_type="image/png",
                    sha256=meta["sha256"],
                    metadata_json=meta,
                )
                created_assets.append(asset)

            elif isinstance(content, ReelContent):
                # 1. Generate Voiceover Audio
                audio_path = storage_dir / "narration.mp3"
                vo_result = await self.voiceover_engine.generate_voiceover(
                    text=content.narration,
                    language=content.metadata.language,
                    output_path=audio_path,
                )
                audio_asset = self._upsert_asset(
                    session=session,
                    content_version_id=version.id,
                    asset_type="audio",
                    local_path=str(audio_path),
                    mime_type=vo_result.mime_type,
                    sha256=vo_result.sha256,
                    metadata_json={
                        "duration_seconds": vo_result.duration_seconds,
                        "voice": vo_result.voice,
                        "size_bytes": vo_result.size_bytes,
                    },
                )
                created_assets.append(audio_asset)

                # 2. Compose Short Video
                video_path = storage_dir / "reel.mp4"
                video_result = await self.video_compositor.compose_reel(
                    content=content,
                    audio_path=audio_path,
                    output_path=video_path,
                )
                video_asset = self._upsert_asset(
                    session=session,
                    content_version_id=version.id,
                    asset_type="reel",
                    local_path=str(video_path),
                    mime_type=video_result.mime_type,
                    sha256=video_result.sha256,
                    metadata_json={
                        "duration_seconds": video_result.duration_seconds,
                        "width": video_result.width,
                        "height": video_result.height,
                        "fps": video_result.fps,
                        "size_bytes": video_result.size_bytes,
                    },
                )
                created_assets.append(video_asset)

            # Update item status to RENDERED
            item.status = "RENDERED"
            session.flush()

            asset_responses = [self._to_asset_response(a) for a in created_assets]
            return RenderResultResponse(
                content_id=item.id,
                version_id=version.id,
                version_number=version.version_number,
                content_type=item.content_type,
                assets=asset_responses,
                status=item.status,
            )

    def _upsert_asset(
        self,
        session: Session,
        content_version_id: UUID,
        asset_type: str,
        local_path: str,
        mime_type: str | None,
        sha256: str | None,
        metadata_json: dict[str, Any],
    ) -> Asset:
        existing = session.scalar(
            select(Asset).where(
                Asset.content_version_id == content_version_id,
                Asset.asset_type == asset_type,
            )
        )
        if existing:
            existing.local_path = local_path
            existing.mime_type = mime_type
            existing.sha256 = sha256
            existing.metadata_json = metadata_json
            return existing

        asset = Asset(
            content_version_id=content_version_id,
            asset_type=asset_type,
            local_path=local_path,
            mime_type=mime_type,
            sha256=sha256,
            metadata_json=metadata_json,
        )
        session.add(asset)
        session.flush()
        return asset

    def list_assets(
        self,
        content_id: UUID,
        version_number: int | None = None,
    ) -> list[AssetResponse]:
        """List all rendered assets for a content item."""
        with self.repository.session() as session:
            stmt = (
                select(Asset)
                .join(ContentVersion)
                .where(ContentVersion.content_item_id == content_id)
            )
            if version_number is not None:
                stmt = stmt.where(ContentVersion.version_number == version_number)
            stmt = stmt.order_by(Asset.created_at.desc())
            assets = session.scalars(stmt).all()
            return [self._to_asset_response(a) for a in assets]

    def get_asset(self, asset_id: UUID) -> Asset | None:
        """Fetch asset entity by ID."""
        with self.repository.session() as session:
            asset = session.get(Asset, asset_id)
            if asset:
                session.expunge(asset)
            return asset
