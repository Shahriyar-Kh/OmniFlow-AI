from __future__ import annotations

import os
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tbos_renderer.config import get_settings
from tbos_renderer.models import ContentItem, ContentVersion, PublishJob, SystemSetting

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def database_engine():  # type: ignore[no-untyped-def]
    if os.getenv("RUN_DB_TESTS") != "1":
        pytest.skip("Set RUN_DB_TESTS=1 inside the Compose network to run database tests")
    engine = create_engine(get_settings().sqlalchemy_url)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        yield engine
    finally:
        engine.dispose()


def _item(key: str) -> ContentItem:
    return ContentItem(
        external_key=key,
        content_type="poster",
        primary_language="roman_urdu",
        content_pillar="Python and Automation",
        topic="Integration test",
        status="IDEA",
        risk_classification="low",
    )


def test_database_connectivity_and_seed_data(database_engine) -> None:  # type: ignore[no-untyped-def]
    with Session(database_engine) as session:
        assert session.scalar(select(SystemSetting).where(SystemSetting.key == "brand")) is not None


def test_alembic_is_at_head_with_all_required_tables(database_engine) -> None:  # type: ignore[no-untyped-def]
    config = Config("database/alembic.ini")
    expected_revision = ScriptDirectory.from_config(config).get_current_head()
    with database_engine.connect() as connection:
        actual_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one()
    assert actual_revision == expected_revision
    expected_tables = {
        "content_items",
        "content_versions",
        "assets",
        "approvals",
        "publish_jobs",
        "published_posts",
        "metrics_snapshots",
        "comments",
        "workflow_events",
        "prompt_templates",
        "approved_facts",
        "content_sources",
        "system_settings",
    }
    assert expected_tables <= set(inspect(database_engine).get_table_names())


def test_content_external_key_uniqueness(database_engine) -> None:  # type: ignore[no-untyped-def]
    key = f"test-{uuid4()}"
    with Session(database_engine) as session:
        session.add(_item(key))
        session.commit()
        session.add(_item(key))
        with pytest.raises(IntegrityError):
            session.commit()


def test_content_version_uniqueness(database_engine) -> None:  # type: ignore[no-untyped-def]
    key = f"version-{uuid4()}"
    with Session(database_engine) as session:
        item = _item(key)
        session.add(item)
        session.flush()
        values = {
            "content_item_id": item.id,
            "version_number": 1,
            "language": "roman_urdu",
            "title": "Version one",
        }
        session.add(ContentVersion(**values))
        session.commit()
        session.add(ContentVersion(**values))
        with pytest.raises(IntegrityError):
            session.commit()


def test_publish_idempotency_key_uniqueness(database_engine) -> None:  # type: ignore[no-untyped-def]
    key = f"publish-{uuid4()}"
    with Session(database_engine) as session:
        item = _item(f"job-{uuid4()}")
        session.add(item)
        session.flush()
        version = ContentVersion(
            content_item_id=item.id,
            version_number=1,
            language="simple_english",
            title="Publish test",
        )
        session.add(version)
        session.flush()
        session.add(
            PublishJob(
                content_version_id=version.id,
                platform="facebook",
                state="pending",
                idempotency_key=key,
            )
        )
        session.commit()
        session.add(
            PublishJob(
                content_version_id=version.id,
                platform="facebook",
                state="pending",
                idempotency_key=key,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
