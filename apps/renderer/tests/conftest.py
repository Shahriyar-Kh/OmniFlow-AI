from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from tbos_renderer.config import Settings
from tbos_renderer.main import create_app
from tbos_renderer.models import Base

TEST_API_KEY = "test-internal-api-key-32-characters"


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def settings(project_root: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=SecretStr("sqlite+pysqlite:///:memory:"),
        internal_api_key=SecretStr(TEST_API_KEY),
        n8n_internal_url=None,
        ollama_base_url=None,
        brand_config_path=project_root / "config/brand/techbuilt_open_school.yaml",
        content_policy_path=project_root / "config/content_policy.yaml",
        schedule_config_path=project_root / "config/schedules.yaml",
        topic_library_path=project_root / "config/topics.yaml",
        prompt_templates_path=project_root / "config/prompts",
        model_profiles_path=project_root / "config/model_profiles.yaml",
    )


@pytest.fixture
def engine() -> Iterator[Engine]:
    value = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(value)
    yield value
    Base.metadata.drop_all(value)
    value.dispose()


@pytest.fixture
def client(settings: Settings, engine: Engine) -> Iterator[TestClient]:
    with TestClient(create_app(settings=settings, engine=engine)) as test_client:
        yield test_client
