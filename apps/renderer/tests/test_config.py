from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError
from tbos_renderer.config import Settings, load_brand_config, load_schedule_config
from tbos_renderer.models import ContentStatus


def test_settings_load_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:secret@db/example")
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-test-key-that-is-long-enough")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("FEATURE_META_ENABLED", "true")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.app_env == "test"
    assert settings.feature_meta_enabled is True
    assert settings.ollama_model == "qwen3:4b"
    assert settings.database_url == SecretStr("postgresql+psycopg://user:secret@db/example")
    assert "secret" not in repr(settings.database_url)
    assert "internal-test" not in repr(settings.internal_api_key)


def test_brand_configuration_parses(settings: Settings) -> None:
    brand = load_brand_config(settings.brand_config_path).brand
    assert brand.slug == "techbuilt-open-school"
    assert brand.weekly_targets.poster == 4
    assert brand.weekly_targets.reel == 3
    assert len(brand.content_pillars) == 5


def test_schedule_configuration_parses(settings: Settings) -> None:
    schedule = load_schedule_config(settings.schedule_config_path)
    assert schedule.timezone == "Asia/Karachi"
    assert schedule.publishing_enabled is False
    assert sum(slot.content_type == "poster" for slot in schedule.weekly_plan) == 4
    assert sum(slot.content_type == "reel" for slot in schedule.weekly_plan) == 3


def test_schedule_rejects_invalid_target_count(tmp_path: Path) -> None:
    path = tmp_path / "bad-schedule.yaml"
    path.write_text(
        "schema_version: 1\ntimezone: Asia/Karachi\npublishing_enabled: false\n"
        "weekly_plan:\n  - {day: Monday, time: '18:00', content_type: poster, slot: only}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_schedule_config(path)


def test_content_status_validation() -> None:
    assert ContentStatus("APPROVED") is ContentStatus.APPROVED
    with pytest.raises(ValueError):
        ContentStatus("NOT_A_REAL_STATUS")
