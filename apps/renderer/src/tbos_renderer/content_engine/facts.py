from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from tbos_renderer.content_engine.schemas import FactRecord, FactSensitivity, SourceReference
from tbos_renderer.models import ApprovedFact, ContentSource

NUMBER_PATTERN = re.compile(r"(?<!\w)(?:\d+(?:\.\d+)?%?|PKR\s*\d+|\$\d+)(?!\w)", re.IGNORECASE)


def find_numerical_claims(text: str) -> list[str]:
    return NUMBER_PATTERN.findall(text)


def needs_approved_facts(sensitivity: FactSensitivity, text: str) -> bool:
    return sensitivity is FactSensitivity.HIGH or (
        sensitivity is FactSensitivity.MEDIUM and bool(find_numerical_claims(text))
    )


def retrieve_approved_facts(session: Session, limit: int = 10) -> list[FactRecord]:
    now = datetime.now(UTC)
    statement = (
        select(ApprovedFact, ContentSource)
        .outerjoin(ContentSource, ApprovedFact.content_source_id == ContentSource.id)
        .where(or_(ApprovedFact.expires_at.is_(None), ApprovedFact.expires_at > now))
        .order_by(ApprovedFact.verified_at.desc())
        .limit(limit)
    )
    records: list[FactRecord] = []
    for fact, source in session.execute(statement):
        reference = None
        if source is not None:
            reference = SourceReference(
                fact_id=UUID(str(fact.id)),
                title=source.title,
                url=source.url,
                publisher=source.publisher,
                reviewed=True,
            )
        records.append(
            FactRecord(
                id=UUID(str(fact.id)),
                statement=fact.statement,
                sensitivity=FactSensitivity(fact.risk_classification.upper()),
                source=reference,
                expires_at=fact.expires_at,
            )
        )
    return records
