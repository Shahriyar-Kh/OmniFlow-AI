from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from tbos_renderer.content_engine.exceptions import ContentNotFoundError, DuplicateContentError
from tbos_renderer.content_engine.schemas import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResponse,
    ApprovalResultResponse,
    ContentGenerationRequest,
    ContentGenerationResult,
    ContentLanguage,
    ContentListResponse,
    ContentQualityReport,
    ContentSummary,
    ContentType,
    ContentVersionResponse,
    ManualContentRevisionRequest,
    PosterContent,
    PublishJobResponse,
    ReelContent,
    SourceReference,
    WeeklyPlan,
)
from tbos_renderer.models import (
    Approval,
    ContentItem,
    ContentSource,
    ContentStatus,
    ContentVersion,
    PromptTemplate,
    PublishJob,
)


def generation_external_key(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode()).hexdigest()[:40]
    return f"generation-{digest}"


class ContentRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def session(self) -> Session:
        return Session(self.engine)

    @staticmethod
    def _parse_content(version: ContentVersion) -> PosterContent | ReelContent:
        payload = version.script_data.get("content", version.script_data)
        if payload.get("metadata", {}).get("content_type") == ContentType.REEL.value:
            return ReelContent.model_validate(payload)
        return PosterContent.model_validate(payload)

    @staticmethod
    def _parse_report(version: ContentVersion) -> ContentQualityReport:
        return ContentQualityReport.model_validate(version.lineage["quality_report"])

    def _version_response(
        self, item: ContentItem, version: ContentVersion
    ) -> ContentVersionResponse:
        return ContentVersionResponse(
            content_id=item.id,
            version_id=version.id,
            version_number=version.version_number,
            status=item.status,
            origin=str(version.lineage.get("origin", "ai_generation")),
            content=self._parse_content(version),
            quality_report=self._parse_report(version),
            created_at=version.created_at,
        )

    def find_generation(self, idempotency_key: str) -> ContentGenerationResult | None:
        with self.session() as session:
            item = session.scalar(
                select(ContentItem).where(
                    ContentItem.external_key == generation_external_key(idempotency_key)
                )
            )
            if item is None:
                return None
            version = session.scalar(
                select(ContentVersion)
                .where(ContentVersion.content_item_id == item.id)
                .order_by(ContentVersion.version_number.desc())
            )
            if version is None:
                return None
            return ContentGenerationResult(
                content_id=item.id,
                version_id=version.id,
                version_number=version.version_number,
                status=item.status,
                content=self._parse_content(version),
                quality_report=self._parse_report(version),
                idempotent_replay=True,
            )

    @staticmethod
    def _template_id(session: Session, name: str, version: int) -> UUID | None:
        prompt = session.scalar(
            select(PromptTemplate).where(
                PromptTemplate.name == name,
                PromptTemplate.version == version,
            )
        )
        return prompt.id if prompt else None

    @staticmethod
    def _add_sources(session: Session, version_id: UUID, sources: list[SourceReference]) -> None:
        now = datetime.now(UTC)
        for source in sources:
            session.add(
                ContentSource(
                    content_version_id=version_id,
                    title=source.title,
                    url=source.url,
                    publisher=source.publisher,
                    retrieved_at=now,
                    verification_metadata={
                        "reviewed": source.reviewed,
                        "fact_id": str(source.fact_id or ""),
                    },
                )
            )

    def store_generation(
        self,
        request: ContentGenerationRequest,
        content: PosterContent | ReelContent,
        report: ContentQualityReport,
        *,
        origin: str = "ai_generation",
        reason: str | None = None,
    ) -> ContentGenerationResult:
        existing = self.find_generation(request.idempotency_key)
        if existing:
            return existing
        status = "QA_PASSED" if report.passed else "DRAFTED"
        metadata = content.metadata
        with self.session() as session, session.begin():
            item = ContentItem(
                external_key=generation_external_key(request.idempotency_key),
                content_type=metadata.content_type.value,
                primary_language=metadata.language.value,
                content_pillar=metadata.content_pillar,
                topic=metadata.topic,
                status=status,
                risk_classification=metadata.fact_sensitivity.value.casefold(),
                scheduled_at=(
                    datetime.combine(metadata.scheduled_date, datetime.min.time(), tzinfo=UTC)
                    if metadata.scheduled_date
                    else None
                ),
            )
            session.add(item)
            session.flush()
            version = self._new_version(
                session,
                item,
                content,
                report,
                version_number=1,
                idempotency_key=request.idempotency_key,
                origin=origin,
                reason=reason,
            )
            session.flush()
            self._add_sources(session, version.id, metadata.sources_used)
            result = ContentGenerationResult(
                content_id=item.id,
                version_id=version.id,
                version_number=1,
                status=status,
                content=content,
                quality_report=report,
            )
        return result

    def _new_version(
        self,
        session: Session,
        item: ContentItem,
        content: PosterContent | ReelContent,
        report: ContentQualityReport,
        *,
        version_number: int,
        idempotency_key: str,
        origin: str,
        reason: str | None,
    ) -> ContentVersion:
        prompt_id = self._template_id(
            session,
            content.metadata.prompt_template_name,
            content.metadata.prompt_template_version,
        )
        title = content.headline if isinstance(content, PosterContent) else content.cover_title
        hook = None if isinstance(content, PosterContent) else content.hook
        all_hashtags = list(
            dict.fromkeys(
                [
                    *content.hashtags.facebook,
                    *content.hashtags.instagram,
                    *content.hashtags.tiktok,
                ]
            )
        )
        version = ContentVersion(
            content_item_id=item.id,
            version_number=version_number,
            language=content.metadata.language.value,
            title=title,
            hook=hook,
            cta=content.cta,
            caption=content.captions.facebook,
            hashtags=all_hashtags,
            scene_data=(
                {"scenes": [scene.model_dump(mode="json") for scene in content.scenes]}
                if isinstance(content, ReelContent)
                else {
                    "teaching_points": content.teaching_points,
                    "visual_concept": content.visual_concept,
                }
            ),
            script_data={"content": content.model_dump(mode="json")},
            prompt_template_id=prompt_id,
            model_name=content.metadata.model_name,
            model_version=None,
            lineage={
                "idempotency_key": idempotency_key,
                "origin": origin,
                "reason": reason,
                "content_hash": content.metadata.content_hash,
                "prompt_name": content.metadata.prompt_template_name,
                "prompt_version": content.metadata.prompt_template_version,
                "generation_parameters": content.metadata.generation_parameters,
                "quality_report": report.model_dump(mode="json"),
                "source_references": [
                    source.model_dump(mode="json") for source in content.metadata.sources_used
                ],
            },
        )
        session.add(version)
        return version

    def add_version(
        self,
        content_id: UUID,
        idempotency_key: str,
        content: PosterContent | ReelContent,
        report: ContentQualityReport,
        *,
        origin: str,
        reason: str,
    ) -> ContentGenerationResult:
        with self.session() as session, session.begin():
            item = session.scalar(
                select(ContentItem).where(ContentItem.id == content_id).with_for_update()
            )
            if item is None:
                raise ContentNotFoundError("Content item was not found.")
            versions = list(
                session.scalars(
                    select(ContentVersion)
                    .where(ContentVersion.content_item_id == content_id)
                    .order_by(ContentVersion.version_number)
                )
            )
            replay = next(
                (
                    version
                    for version in versions
                    if version.lineage.get("idempotency_key") == idempotency_key
                ),
                None,
            )
            if replay:
                return ContentGenerationResult(
                    content_id=item.id,
                    version_id=replay.id,
                    version_number=replay.version_number,
                    status=item.status,
                    content=self._parse_content(replay),
                    quality_report=self._parse_report(replay),
                    idempotent_replay=True,
                )
            if content.metadata.topic.casefold() != item.topic.casefold():
                raise DuplicateContentError("A revision cannot change the stable content topic.")
            number = (versions[-1].version_number if versions else 0) + 1
            status = "QA_PASSED" if report.passed else "DRAFTED"
            item.status = status
            version = self._new_version(
                session,
                item,
                content,
                report,
                version_number=number,
                idempotency_key=idempotency_key,
                origin=origin,
                reason=reason,
            )
            session.flush()
            self._add_sources(session, version.id, content.metadata.sources_used)
            result = ContentGenerationResult(
                content_id=item.id,
                version_id=version.id,
                version_number=number,
                status=status,
                content=content,
                quality_report=report,
            )
        return result

    def get_item(self, content_id: UUID) -> ContentItem:
        with self.session() as session:
            item = session.get(ContentItem, content_id)
            if item is None:
                raise ContentNotFoundError("Content item was not found.")
            session.expunge(item)
            return item

    def get_version(self, content_id: UUID, version_number: int) -> ContentVersionResponse:
        with self.session() as session:
            item = session.get(ContentItem, content_id)
            if item is None:
                raise ContentNotFoundError("Content item was not found.")
            version = session.scalar(
                select(ContentVersion).where(
                    ContentVersion.content_item_id == content_id,
                    ContentVersion.version_number == version_number,
                )
            )
            if version is None:
                raise ContentNotFoundError("Content version was not found.")
            return self._version_response(item, version)

    def list_versions(self, content_id: UUID) -> list[ContentVersionResponse]:
        with self.session() as session:
            item = session.get(ContentItem, content_id)
            if item is None:
                raise ContentNotFoundError("Content item was not found.")
            versions = session.scalars(
                select(ContentVersion)
                .where(ContentVersion.content_item_id == content_id)
                .order_by(ContentVersion.version_number)
            )
            return [self._version_response(item, version) for version in versions]

    def list_content(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        content_type: ContentType | None = None,
        pillar: str | None = None,
        status: str | None = None,
        language: ContentLanguage | None = None,
        scheduled_date: date | None = None,
    ) -> ContentListResponse:
        filters = []
        if content_type:
            filters.append(ContentItem.content_type == content_type.value)
        if pillar:
            filters.append(ContentItem.content_pillar == pillar)
        if status:
            filters.append(ContentItem.status == status)
        if language:
            filters.append(ContentItem.primary_language == language.value)
        if scheduled_date:
            start = datetime.combine(scheduled_date, datetime.min.time(), tzinfo=UTC)
            filters.extend(
                [
                    ContentItem.scheduled_at >= start,
                    ContentItem.scheduled_at < start + timedelta(days=1),
                ]
            )
        with self.session() as session:
            total = (
                session.scalar(select(func.count()).select_from(ContentItem).where(*filters)) or 0
            )
            items = list(
                session.scalars(
                    select(ContentItem)
                    .where(*filters)
                    .order_by(ContentItem.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            summaries: list[ContentSummary] = []
            for item in items:
                current = session.scalar(
                    select(func.max(ContentVersion.version_number)).where(
                        ContentVersion.content_item_id == item.id
                    )
                )
                summaries.append(
                    ContentSummary(
                        id=item.id,
                        external_key=item.external_key,
                        content_type=ContentType(item.content_type),
                        language=ContentLanguage(item.primary_language),
                        pillar=item.content_pillar,
                        topic=item.topic,
                        status=item.status,
                        scheduled_at=item.scheduled_at,
                        current_version=current,
                    )
                )
            return ContentListResponse(items=summaries, page=page, page_size=page_size, total=total)

    def recent_topic_ids(self, days: int = 60) -> set[str]:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        with self.session() as session:
            keys = session.scalars(
                select(ContentItem.external_key).where(
                    ContentItem.external_key.like("weekly-%:%:%"),
                    ContentItem.created_at >= cutoff,
                )
            )
            return {key.split(":", 2)[2] for key in keys}

    def persist_plan(self, plan: WeeklyPlan, *, regenerate: bool = False) -> WeeklyPlan:
        replay = True
        nonce = datetime.now(UTC).strftime("%H%M%S%f") if regenerate else ""
        with self.session() as session, session.begin():
            for plan_item in plan.items:
                base = f"{plan.plan_id}:{plan_item.slot}:{plan_item.topic_id}"
                key = f"{base}:{nonce}" if nonce else base
                existing = session.scalar(
                    select(ContentItem).where(ContentItem.external_key == key)
                )
                if existing:
                    continue
                replay = False
                session.add(
                    ContentItem(
                        external_key=key,
                        content_type=plan_item.content_type.value,
                        primary_language=ContentLanguage.ROMAN_URDU.value,
                        content_pillar=plan_item.pillar,
                        topic=plan_item.title,
                        status="IDEA",
                        risk_classification=plan_item.fact_sensitivity.value.casefold(),
                        scheduled_at=plan_item.scheduled_at,
                    )
                )
        return plan.model_copy(update={"idempotent_replay": replay})

    def store_manual_revision(
        self, content_id: UUID, request: ManualContentRevisionRequest
    ) -> ContentGenerationResult:
        from tbos_renderer.content_engine.qa import evaluate_content

        report = evaluate_content(request.content)
        return self.add_version(
            content_id,
            request.idempotency_key,
            request.content,
            report,
            origin="manual_revision",
            reason=request.reason,
        )

    def record_approval(self, content_id: UUID, request: ApprovalRequest) -> ApprovalResultResponse:
        with self.session() as session, session.begin():
            item = session.get(ContentItem, content_id)
            if item is None:
                raise ContentNotFoundError(f"Content item {content_id} not found.")

            if request.version_number is not None:
                version = session.scalar(
                    select(ContentVersion).where(
                        ContentVersion.content_item_id == content_id,
                        ContentVersion.version_number == request.version_number,
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

            now = datetime.now(UTC)
            approval = Approval(
                content_version_id=version.id,
                decision=request.decision.value,
                reviewer_reference=request.reviewer_reference,
                notes=request.notes,
                decided_at=now,
            )
            session.add(approval)
            session.flush()

            publish_jobs: list[PublishJob] = []
            if request.decision == ApprovalDecision.APPROVED:
                item.status = ContentStatus.APPROVED.value
                # Generate platform-specific publish jobs with unique idempotency keys
                platforms = ["facebook", "instagram", "tiktok_handoff"]
                for platform in platforms:
                    idempotency_key = f"{platform}:{version.id}:{int(now.timestamp())}"
                    payload = {
                        "content_id": str(content_id),
                        "version_id": str(version.id),
                        "version_number": version.version_number,
                        "title": version.title,
                        "hook": version.hook,
                        "caption": version.caption,
                        "hashtags": version.hashtags,
                        "platform": platform,
                    }
                    job = PublishJob(
                        content_version_id=version.id,
                        platform=platform,
                        state="pending",
                        idempotency_key=idempotency_key,
                        scheduled_at=item.scheduled_at,
                        request_payload=payload,
                    )
                    session.add(job)
                    publish_jobs.append(job)
                session.flush()
            else:
                item.status = ContentStatus.CHANGES_REQUESTED.value

            approval_resp = ApprovalResponse(
                id=approval.id,
                content_version_id=approval.content_version_id,
                decision=approval.decision,
                reviewer_reference=approval.reviewer_reference,
                notes=approval.notes,
                decided_at=approval.decided_at,
                created_at=approval.created_at,
            )
            jobs_resp = [
                PublishJobResponse(
                    id=j.id,
                    content_version_id=j.content_version_id,
                    platform=j.platform,
                    state=j.state,
                    idempotency_key=j.idempotency_key,
                    retry_count=j.retry_count,
                    scheduled_at=j.scheduled_at,
                    request_payload=j.request_payload,
                    created_at=j.created_at,
                )
                for j in publish_jobs
            ]

            return ApprovalResultResponse(
                content_id=content_id,
                version_id=version.id,
                version_number=version.version_number,
                status=item.status,
                approval=approval_resp,
                publish_jobs=jobs_resp,
            )

    def list_approvals(self, content_id: UUID) -> list[ApprovalResponse]:
        with self.session() as session:
            stmt = (
                select(Approval)
                .join(ContentVersion, ContentVersion.id == Approval.content_version_id)
                .where(ContentVersion.content_item_id == content_id)
                .order_by(Approval.created_at.desc())
            )
            records = session.scalars(stmt).all()
            return [
                ApprovalResponse(
                    id=rec.id,
                    content_version_id=rec.content_version_id,
                    decision=rec.decision,
                    reviewer_reference=rec.reviewer_reference,
                    notes=rec.notes,
                    decided_at=rec.decided_at,
                    created_at=rec.created_at,
                )
                for rec in records
            ]

    def list_publish_jobs(
        self,
        content_id: UUID | None = None,
        content_version_id: UUID | None = None,
    ) -> list[PublishJobResponse]:
        with self.session() as session:
            stmt = select(PublishJob)
            if content_version_id:
                stmt = stmt.where(PublishJob.content_version_id == content_version_id)
            elif content_id:
                stmt = stmt.join(
                    ContentVersion, ContentVersion.id == PublishJob.content_version_id
                ).where(ContentVersion.content_item_id == content_id)
            stmt = stmt.order_by(PublishJob.created_at.asc())
            records = session.scalars(stmt).all()
            return [
                PublishJobResponse(
                    id=rec.id,
                    content_version_id=rec.content_version_id,
                    platform=rec.platform,
                    state=rec.state,
                    idempotency_key=rec.idempotency_key,
                    retry_count=rec.retry_count,
                    scheduled_at=rec.scheduled_at,
                    request_payload=rec.request_payload,
                    created_at=rec.created_at,
                )
                for rec in records
            ]
