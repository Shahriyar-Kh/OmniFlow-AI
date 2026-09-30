from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WeeklyTargets(BaseModel):
    poster: int = Field(ge=0)
    reel: int = Field(ge=0)


class MediaSize(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class BrandDetails(BaseModel):
    name: str
    slug: str
    description: str
    audience: list[str]
    voice_and_tone: list[str]
    default_language_style: str
    content_pillars: list[str]
    weekly_targets: WeeklyTargets
    sizes: dict[Literal["poster", "reel"], MediaSize]
    palette: dict[str, str]
    typography: dict[str, str]
    cta_examples: list[str]
    prohibited_claims: list[str]
    human_review: dict[str, bool]


class BrandConfig(BaseModel):
    schema_version: int
    brand: BrandDetails


class ScheduleSlot(BaseModel):
    day: Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    time: str
    content_type: Literal["poster", "reel"]
    slot: str

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError("time must use HH:MM")
        hour, minute = (int(part) for part in parts)
        if hour not in range(24) or minute not in range(60):
            raise ValueError("time must use a valid 24-hour value")
        return value


class ScheduleConfig(BaseModel):
    schema_version: int
    timezone: str
    publishing_enabled: bool
    weekly_plan: list[ScheduleSlot]

    @field_validator("weekly_plan")
    @classmethod
    def validate_weekly_targets(cls, value: list[ScheduleSlot]) -> list[ScheduleSlot]:
        poster_count = sum(slot.content_type == "poster" for slot in value)
        reel_count = sum(slot.content_type == "reel" for slot in value)
        if (poster_count, reel_count) != (4, 3):
            raise ValueError("weekly plan must contain four posters and three reels")
        return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_log_level: str = "INFO"
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    app_timezone: str = "Asia/Karachi"
    app_openapi_enabled: bool = True
    app_version: str = "0.2.0"
    database_url: SecretStr
    internal_api_key: SecretStr
    n8n_internal_url: str | None = "http://n8n:5678"
    ollama_base_url: str | None = "http://host.docker.internal:11434"
    ollama_model: str = "qwen3:4b"
    ollama_fallback_model: str | None = None
    ollama_timeout_seconds: float = Field(default=180, gt=0, le=600)
    ollama_max_retries: int = Field(default=2, ge=0, le=5)
    ollama_max_concurrency: int = Field(default=1, ge=1, le=4)
    ollama_temperature: float = Field(default=0.2, ge=0, le=1)
    ollama_context_length: int = Field(default=4096, ge=2048, le=32768)
    ollama_enabled: bool = False
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_fallback_model: str | None = "gemini-2.5-pro"
    gemini_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    ai_primary_provider: Literal["gemini", "ollama"] = "gemini"
    shared_storage_path: Path = Path("storage")
    feature_telegram_enabled: bool = False
    feature_meta_enabled: bool = False
    feature_r2_enabled: bool = False
    feature_ollama_enabled: bool = False
    brand_config_path: Path = Path("config/brand/techbuilt_open_school.yaml")
    content_policy_path: Path = Path("config/content_policy.yaml")
    schedule_config_path: Path = Path("config/schedules.yaml")
    topic_library_path: Path = Path("config/topics.yaml")
    prompt_templates_path: Path = Path("config/prompts")
    model_profiles_path: Path = Path("config/model_profiles.yaml")
    qa_pass_threshold: int = Field(default=85, ge=0, le=100)
    facebook_hashtag_limit: int = Field(default=15, ge=0, le=30)
    instagram_hashtag_limit: int = Field(default=5, ge=0, le=30)
    tiktok_hashtag_limit: int = Field(default=5, ge=0, le=30)
    meta_app_id: str | None = None
    meta_app_secret: SecretStr | None = None
    meta_page_id: str | None = None
    meta_instagram_account_id: str | None = None
    meta_access_token: SecretStr | None = None
    meta_api_version: str = "v22.0"
    meta_api_base_url: str = "https://graph.facebook.com"
    telegram_bot_token: SecretStr | None = None
    telegram_approval_chat_id: str | None = None

    @property
    def sqlalchemy_url(self) -> str:
        return self.database_url.get_secret_value()


def _read_yaml(path: Path) -> object:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_brand_config(path: Path) -> BrandConfig:
    return BrandConfig.model_validate(_read_yaml(path))


def load_schedule_config(path: Path) -> ScheduleConfig:
    return ScheduleConfig.model_validate(_read_yaml(path))


@lru_cache
def get_settings() -> Settings:
    return Settings()
