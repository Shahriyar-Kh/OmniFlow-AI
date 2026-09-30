from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Engine

from tbos_renderer import __version__
from tbos_renderer.api.ai import router as ai_router
from tbos_renderer.api.content import router as content_router
from tbos_renderer.api.dashboard import router as dashboard_router
from tbos_renderer.api.plans import router as plans_router
from tbos_renderer.api.publishing import router as publishing_router
from tbos_renderer.api.rendering import router as rendering_router
from tbos_renderer.api.topics import router as topics_router
from tbos_renderer.config import Settings, get_settings, load_brand_config
from tbos_renderer.content_engine.exceptions import (
    AiServiceUnavailableError,
    ContentEngineError,
    ContentNotFoundError,
    DuplicateContentError,
    GeminiModelError,
    GeminiUnavailableError,
    ModelOutputError,
    OllamaModelError,
    OllamaUnavailableError,
    PromptInjectionError,
)
from tbos_renderer.content_engine.repository import ContentRepository
from tbos_renderer.content_engine.service import ContentEngineService
from tbos_renderer.database import create_database_engine
from tbos_renderer.health import database_status, http_service_status
from tbos_renderer.logging_config import configure_logging
from tbos_renderer.middleware import CorrelationIdMiddleware
from tbos_renderer.publishing.service import PublishingService
from tbos_renderer.rendering.service import RenderingService
from tbos_renderer.schemas import (
    ErrorResponse,
    FeatureFlagsResponse,
    LiveResponse,
    PublicConfigResponse,
    ReadyResponse,
    SystemStatusResponse,
    WeeklyTargetsResponse,
)

LOGGER = logging.getLogger(__name__)
SERVICE_NAME = "tbos-renderer-api"


def _correlation_id(request: Request) -> str:
    return str(getattr(request.state, "correlation_id", "unknown"))


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    configure_logging(active_settings.app_log_level)
    active_engine = engine or create_database_engine(active_settings)
    repository = ContentRepository(active_engine)
    content_service = ContentEngineService(active_settings, repository)
    rendering_service = RenderingService(active_settings, repository)
    publishing_service = PublishingService(active_settings, repository)

    @asynccontextmanager
    async def lifespan(application: FastAPI):  # type: ignore[no-untyped-def]
        application.state.settings = active_settings
        application.state.engine = active_engine
        application.state.content_repository = repository
        application.state.content_service = content_service
        application.state.rendering_service = rendering_service
        application.state.publishing_service = publishing_service
        LOGGER.info("application_started")
        yield
        active_engine.dispose()
        LOGGER.info("application_stopped")

    docs_enabled = active_settings.app_openapi_enabled and active_settings.app_env != "production"
    application = FastAPI(
        title="TechBuilt Open School Content API",
        version=__version__,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )
    application.state.settings = active_settings
    application.state.engine = active_engine
    application.state.content_repository = repository
    application.state.content_service = content_service
    application.state.rendering_service = rendering_service
    application.state.publishing_service = publishing_service
    application.add_middleware(CorrelationIdMiddleware)

    @application.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, _error: RequestValidationError) -> JSONResponse:
        response = ErrorResponse(
            error="validation_error",
            message="The request did not pass validation.",
            correlation_id=_correlation_id(request),
        )
        return JSONResponse(status_code=422, content=response.model_dump())

    @application.exception_handler(ContentEngineError)
    async def content_engine_handler(request: Request, error: ContentEngineError) -> JSONResponse:
        status_code = 422
        code = "content_engine_error"
        if isinstance(error, ContentNotFoundError):
            status_code, code = 404, "not_found"
        elif isinstance(error, DuplicateContentError):
            status_code, code = 409, "duplicate_content"
        elif isinstance(error, PromptInjectionError):
            status_code, code = 400, "unsafe_input"
        elif isinstance(error, OllamaUnavailableError | OllamaModelError):
            status_code, code = 503, "ollama_unavailable"
        elif isinstance(error, GeminiUnavailableError | GeminiModelError):
            status_code, code = 503, "gemini_unavailable"
        elif isinstance(error, AiServiceUnavailableError):
            status_code, code = 503, "ai_unavailable"
        elif isinstance(error, ModelOutputError):
            code = "invalid_model_output"
        response = ErrorResponse(
            error=code,
            message=str(error),
            correlation_id=_correlation_id(request),
        )
        return JSONResponse(status_code=status_code, content=response.model_dump())

    @application.exception_handler(Exception)
    async def unexpected_handler(request: Request, error: Exception) -> JSONResponse:
        LOGGER.exception(
            "unhandled_request_error",
            exc_info=error,
            extra={"correlation_id": _correlation_id(request)},
        )
        response = ErrorResponse(
            error="internal_error",
            message="An internal error occurred.",
            correlation_id=_correlation_id(request),
        )
        return JSONResponse(status_code=500, content=response.model_dump())

    @application.get("/health/live", response_model=LiveResponse)
    async def live(request: Request) -> LiveResponse:
        return LiveResponse(
            status="alive",
            service=SERVICE_NAME,
            version=__version__,
            timestamp=datetime.now(UTC),
            correlation_id=_correlation_id(request),
        )

    @application.get(
        "/health/ready",
        response_model=ReadyResponse,
        responses={503: {"model": ReadyResponse}},
    )
    async def ready(request: Request) -> ReadyResponse | JSONResponse:
        database = await database_status(active_engine)
        ollama = await http_service_status(
            f"{active_settings.ollama_base_url}/api/tags"
            if active_settings.ollama_base_url
            else None,
            required=False,
            enabled=active_settings.ollama_enabled,
            service_name="Ollama",
        )
        response = ReadyResponse(
            status="ready" if database.status == "ok" else "not_ready",
            database=database,
            ollama=ollama,
            timestamp=datetime.now(UTC),
            correlation_id=_correlation_id(request),
        )
        if response.status == "not_ready":
            return JSONResponse(status_code=503, content=response.model_dump(mode="json"))
        return response

    @application.get("/api/v1/system/status", response_model=SystemStatusResponse)
    async def system_status(request: Request) -> SystemStatusResponse:
        database = await database_status(active_engine)
        n8n = await http_service_status(
            f"{active_settings.n8n_internal_url}/healthz"
            if active_settings.n8n_internal_url
            else None,
            required=False,
            service_name="n8n",
        )
        ollama = await http_service_status(
            f"{active_settings.ollama_base_url}/api/tags"
            if active_settings.ollama_base_url
            else None,
            required=False,
            enabled=active_settings.ollama_enabled,
            service_name="Ollama",
        )
        return SystemStatusResponse(
            service=SERVICE_NAME,
            version=__version__,
            environment=active_settings.app_env,
            database=database,
            n8n=n8n,
            ollama=ollama,
            timestamp=datetime.now(UTC),
            correlation_id=_correlation_id(request),
        )

    @application.get("/api/v1/config/public", response_model=PublicConfigResponse)
    async def public_config() -> PublicConfigResponse:
        brand = load_brand_config(active_settings.brand_config_path).brand
        return PublicConfigResponse(
            brand_name=brand.name,
            brand_slug=brand.slug,
            timezone=active_settings.app_timezone,
            enabled_content_types=["poster", "reel"],
            weekly_targets=WeeklyTargetsResponse.model_validate(brand.weekly_targets.model_dump()),
            default_language_style=brand.default_language_style,
            feature_flags=FeatureFlagsResponse(
                telegram=active_settings.feature_telegram_enabled,
                meta=active_settings.feature_meta_enabled,
                r2=active_settings.feature_r2_enabled,
                ollama=active_settings.ollama_enabled,
            ),
        )

    active_settings.shared_storage_path.mkdir(parents=True, exist_ok=True)
    application.mount(
        "/storage",
        StaticFiles(directory=str(active_settings.shared_storage_path), html=False),
        name="storage",
    )

    application.include_router(topics_router)
    application.include_router(plans_router)
    application.include_router(content_router)
    application.include_router(ai_router)
    application.include_router(rendering_router)
    application.include_router(publishing_router)
    application.include_router(dashboard_router)
    return application


def app_factory() -> Any:
    """Compatibility factory for ASGI runners."""
    return create_app()
