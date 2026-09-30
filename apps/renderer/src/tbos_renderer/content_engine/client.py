from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

import httpx
from google import genai
from google.genai import types
from google.genai.errors import APIError

from tbos_renderer.config import Settings
from tbos_renderer.content_engine.exceptions import (
    AiServiceUnavailableError,
    GeminiModelError,
    GeminiUnavailableError,
    ModelOutputError,
    OllamaModelError,
    OllamaUnavailableError,
)
from tbos_renderer.content_engine.schemas import AiStatusResponse

LOGGER = logging.getLogger(__name__)


@runtime_checkable
class AiClient(Protocol):
    active_model_name: str
    last_provider_used: str
    fallback_occurred: bool

    async def status(self) -> AiStatusResponse: ...

    async def generate_json(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any] | None = None,
        model: str | None = None,
    ) -> dict[str, Any]: ...


class OllamaClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport
        self._semaphore = asyncio.Semaphore(settings.ollama_max_concurrency)
        self.active_model_name: str = settings.ollama_model
        self.last_provider_used: str = "ollama"
        self.fallback_occurred: bool = False

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=str(self.settings.ollama_base_url or ""),
            timeout=self.settings.ollama_timeout_seconds,
            transport=self._transport,
        )

    async def status(self) -> AiStatusResponse:
        configured = bool(self.settings.ollama_base_url and self.settings.ollama_model)
        if not configured:
            return AiStatusResponse(
                enabled=self.settings.ollama_enabled,
                configured=False,
                reachable=False,
                selected_model=self.settings.ollama_model,
                model_available=False,
                detail="Ollama is not configured.",
            )
        try:
            async with self._client() as client:
                response = await client.get("/api/tags")
                response.raise_for_status()
            body = response.json()
            models = [str(item.get("name", "")) for item in body.get("models", [])]
            return AiStatusResponse(
                enabled=self.settings.ollama_enabled,
                configured=True,
                reachable=True,
                selected_model=self.settings.ollama_model,
                model_available=self.settings.ollama_model in models,
                available_models=models,
                detail="Ollama is reachable.",
            )
        except (httpx.HTTPError, ValueError, TypeError):
            return AiStatusResponse(
                enabled=self.settings.ollama_enabled,
                configured=True,
                reachable=False,
                selected_model=self.settings.ollama_model,
                model_available=False,
                detail="Ollama is unavailable.",
            )

    async def generate_json(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any] | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        if not self.settings.ollama_enabled:
            raise OllamaUnavailableError("Ollama generation is disabled.")
        selected_model = model or self.settings.ollama_model
        self.active_model_name = selected_model
        self.last_provider_used = "ollama"
        self.fallback_occurred = False
        payload: dict[str, Any] = {
            "model": selected_model,
            "prompt": prompt,
            "stream": False,
            "format": dict(schema) if schema else "json",
            "options": {
                "temperature": self.settings.ollama_temperature,
                "num_ctx": self.settings.ollama_context_length,
            },
        }
        last_error: Exception | None = None
        async with self._semaphore:
            for attempt in range(self.settings.ollama_max_retries + 1):
                try:
                    async with self._client() as client:
                        response = await client.post("/api/generate", json=payload)
                    if response.status_code == 404:
                        raise OllamaModelError("Configured Ollama model is unavailable.")
                    response.raise_for_status()
                    outer = response.json()
                    raw = outer.get("response")
                    if isinstance(raw, dict):
                        return raw
                    if not isinstance(raw, str):
                        raise ModelOutputError("Ollama response did not contain structured output.")
                    parsed = json.loads(raw)
                    if not isinstance(parsed, dict):
                        raise ModelOutputError("Ollama JSON output must be an object.")
                    return parsed
                except OllamaModelError:
                    raise
                except (json.JSONDecodeError, ModelOutputError) as error:
                    raise ModelOutputError("Ollama returned invalid JSON.", [str(error)]) from error
                except (
                    httpx.TimeoutException,
                    httpx.TransportError,
                    httpx.HTTPStatusError,
                ) as error:
                    last_error = error
                    if attempt < self.settings.ollama_max_retries:
                        await asyncio.sleep(min(0.25 * (2**attempt), 1.0))
            raise OllamaUnavailableError(
                "Ollama request failed after bounded retries."
            ) from last_error


class GeminiClient:
    def __init__(
        self,
        settings: Settings,
        *,
        client: genai.Client | None = None,
    ) -> None:
        self.settings = settings
        self._client = client
        self._semaphore = asyncio.Semaphore(4)
        self.active_model_name: str = settings.gemini_model
        self.last_provider_used: str = "gemini"
        self.fallback_occurred: bool = False

    def _get_client(self) -> genai.Client:
        if self._client is not None:
            return self._client
        if not self.settings.gemini_api_key:
            raise GeminiUnavailableError("GEMINI_API_KEY is not configured.")
        return genai.Client(api_key=self.settings.gemini_api_key.get_secret_value())

    async def status(self) -> AiStatusResponse:
        configured = bool(self.settings.gemini_api_key and self.settings.gemini_model)
        if not configured:
            return AiStatusResponse(
                enabled=bool(self.settings.gemini_api_key),
                configured=False,
                reachable=False,
                selected_model=self.settings.gemini_model,
                model_available=False,
                detail="Gemini API key is not configured.",
            )
        try:
            client = self._get_client()
            model_info = await asyncio.to_thread(
                client.models.get, model=self.settings.gemini_model
            )
            available = model_info is not None
            return AiStatusResponse(
                enabled=True,
                configured=True,
                reachable=True,
                selected_model=self.settings.gemini_model,
                model_available=available,
                available_models=[self.settings.gemini_model],
                detail="Gemini API is reachable.",
            )
        except Exception as error:
            return AiStatusResponse(
                enabled=bool(self.settings.gemini_api_key),
                configured=True,
                reachable=False,
                selected_model=self.settings.gemini_model,
                model_available=False,
                detail=f"Gemini API check failed: {error}",
            )

    async def generate_json(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any] | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        if not self.settings.gemini_api_key:
            raise GeminiUnavailableError("Gemini API key is not configured.")
        selected_model = model or self.settings.gemini_model
        self.active_model_name = selected_model
        self.last_provider_used = "gemini"
        self.fallback_occurred = False

        client = self._get_client()
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=self.settings.ollama_temperature,
        )
        try:
            async with self._semaphore:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=selected_model,
                        contents=prompt,
                        config=config,
                    ),
                    timeout=self.settings.gemini_timeout_seconds,
                )
        except TimeoutError as error:
            raise GeminiUnavailableError("Gemini request timed out.") from error
        except APIError as error:
            if error.code == 404:
                raise GeminiModelError(
                    f"Configured Gemini model {selected_model} was not found."
                ) from error
            raise GeminiUnavailableError(f"Gemini API error: {error}") from error
        except Exception as error:
            raise GeminiUnavailableError(f"Gemini request failed: {error}") from error

        raw = response.text or ""
        cleaned = raw.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise ModelOutputError("Gemini returned invalid JSON.", [str(error)]) from error
        if not isinstance(parsed, dict):
            raise ModelOutputError("Gemini JSON output must be an object.")
        return parsed


class CompositeAiClient:
    def __init__(
        self,
        settings: Settings,
        *,
        gemini_client: GeminiClient | None = None,
        ollama_client: OllamaClient | None = None,
    ) -> None:
        self.settings = settings
        self.gemini_client = gemini_client or GeminiClient(settings)
        self.ollama_client = ollama_client or OllamaClient(settings)
        self.active_model_name: str = (
            settings.gemini_model
            if settings.ai_primary_provider == "gemini"
            else settings.ollama_model
        )
        self.last_provider_used: str = settings.ai_primary_provider
        self.fallback_occurred: bool = False

    async def status(self) -> AiStatusResponse:
        primary_is_gemini = self.settings.ai_primary_provider == "gemini"
        gemini_status = await self.gemini_client.status()
        ollama_status = await self.ollama_client.status()

        if primary_is_gemini:
            if gemini_status.reachable and gemini_status.configured:
                return AiStatusResponse(
                    enabled=gemini_status.enabled,
                    configured=gemini_status.configured,
                    reachable=gemini_status.reachable,
                    selected_model=self.settings.gemini_model,
                    model_available=gemini_status.model_available,
                    available_models=gemini_status.available_models,
                    detail=(
                        f"Primary (Gemini: {self.settings.gemini_model}) ready; "
                        f"Fallback (Ollama: {ollama_status.detail})"
                    ),
                )
            if ollama_status.reachable and ollama_status.configured:
                return AiStatusResponse(
                    enabled=ollama_status.enabled,
                    configured=ollama_status.configured,
                    reachable=ollama_status.reachable,
                    selected_model=self.settings.ollama_model,
                    model_available=ollama_status.model_available,
                    available_models=ollama_status.available_models,
                    detail=(
                        f"Gemini unavailable ({gemini_status.detail}); "
                        f"Active Fallback (Ollama: {self.settings.ollama_model})"
                    ),
                )
            return AiStatusResponse(
                enabled=gemini_status.enabled or ollama_status.enabled,
                configured=gemini_status.configured or ollama_status.configured,
                reachable=False,
                selected_model=self.settings.gemini_model,
                model_available=False,
                available_models=[],
                detail=f"Gemini: {gemini_status.detail}; Ollama: {ollama_status.detail}",
            )
        else:
            if ollama_status.reachable and ollama_status.configured:
                return ollama_status
            return gemini_status

    async def generate_json(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any] | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        if self.settings.ai_primary_provider == "gemini":
            try:
                result = await self.gemini_client.generate_json(
                    prompt, schema=schema, model=model or self.settings.gemini_model
                )
                self.active_model_name = model or self.settings.gemini_model
                self.last_provider_used = "gemini"
                self.fallback_occurred = False
                return result
            except (GeminiUnavailableError, GeminiModelError) as gemini_err:
                LOGGER.warning("gemini_generation_failed_trying_fallback", exc_info=gemini_err)
                try:
                    result = await self.ollama_client.generate_json(
                        prompt, schema=schema, model=self.settings.ollama_model
                    )
                    self.active_model_name = self.settings.ollama_model
                    self.last_provider_used = "ollama"
                    self.fallback_occurred = True
                    return result
                except (OllamaUnavailableError, OllamaModelError) as ollama_err:
                    raise AiServiceUnavailableError(
                        f"Both primary (Gemini) and fallback (Ollama) failed. "
                        f"Gemini: {gemini_err}; Ollama: {ollama_err}"
                    ) from ollama_err
        else:
            try:
                result = await self.ollama_client.generate_json(
                    prompt, schema=schema, model=model or self.settings.ollama_model
                )
                self.active_model_name = model or self.settings.ollama_model
                self.last_provider_used = "ollama"
                self.fallback_occurred = False
                return result
            except (OllamaUnavailableError, OllamaModelError) as ollama_err:
                LOGGER.warning("ollama_generation_failed_trying_fallback", exc_info=ollama_err)
                try:
                    result = await self.gemini_client.generate_json(
                        prompt, schema=schema, model=self.settings.gemini_model
                    )
                    self.active_model_name = self.settings.gemini_model
                    self.last_provider_used = "gemini"
                    self.fallback_occurred = True
                    return result
                except (GeminiUnavailableError, GeminiModelError) as gemini_err:
                    raise AiServiceUnavailableError(
                        f"Both primary (Ollama) and fallback (Gemini) failed. "
                        f"Ollama: {ollama_err}; Gemini: {gemini_err}"
                    ) from gemini_err
