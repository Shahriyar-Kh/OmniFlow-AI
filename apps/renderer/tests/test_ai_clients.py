from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from google.genai.errors import APIError
from pydantic import SecretStr
from tbos_renderer.config import Settings
from tbos_renderer.content_engine.client import (
    CompositeAiClient,
    GeminiClient,
    OllamaClient,
)
from tbos_renderer.content_engine.exceptions import (
    AiServiceUnavailableError,
    GeminiModelError,
    GeminiUnavailableError,
    ModelOutputError,
    OllamaModelError,
    OllamaUnavailableError,
)
from tbos_renderer.content_engine.schemas import AiStatusResponse


@pytest.fixture
def base_settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url=SecretStr("sqlite+pysqlite:///:memory:"),
        internal_api_key=SecretStr("test-key-01234567890123456789"),
        ollama_enabled=True,
        ollama_base_url="http://fake-ollama:11434",
        ollama_model="qwen3:4b",
        ollama_max_retries=1,
        gemini_api_key=SecretStr("fake-gemini-key"),
        gemini_model="gemini-2.5-flash",
        ai_primary_provider="gemini",
    )


@pytest.mark.asyncio
async def test_ollama_client_status(base_settings: Settings) -> None:
    # 1. Unconfigured
    unconfigured = Settings(
        _env_file=None,
        database_url=SecretStr("sqlite+pysqlite:///:memory:"),
        internal_api_key=SecretStr("test-key-01234567890123456789"),
        ollama_base_url=None,
        ollama_model="",
    )
    client_unconf = OllamaClient(unconfigured)
    status_unconf = await client_unconf.status()
    assert not status_unconf.configured
    assert not status_unconf.reachable

    # 2. Reachable with model
    mock_transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"models": [{"name": "qwen3:4b"}]})
    )
    client = OllamaClient(base_settings, transport=mock_transport)
    status = await client.status()
    assert status.configured
    assert status.reachable
    assert status.model_available

    # 3. HTTP Error / Unreachable
    mock_transport_err = httpx.MockTransport(
        lambda request: httpx.Response(500, text="Internal Server Error")
    )
    client_err = OllamaClient(base_settings, transport=mock_transport_err)
    status_err = await client_err.status()
    assert not status_err.reachable


@pytest.mark.asyncio
async def test_ollama_client_generate_json(base_settings: Settings) -> None:
    # Disabled check
    base_settings.ollama_enabled = False
    client = OllamaClient(base_settings)
    with pytest.raises(OllamaUnavailableError, match="disabled"):
        await client.generate_json("Prompt")

    # Success output
    base_settings.ollama_enabled = True
    valid_payload = {"response": json.dumps({"headline": "Test Title", "points": [1, 2]})}
    mock_transport = httpx.MockTransport(lambda request: httpx.Response(200, json=valid_payload))
    client = OllamaClient(base_settings, transport=mock_transport)
    result = await client.generate_json("Prompt")
    assert result["headline"] == "Test Title"

    # 404 Model Not Found
    mock_transport_404 = httpx.MockTransport(
        lambda request: httpx.Response(404, text="Model not found")
    )
    client_404 = OllamaClient(base_settings, transport=mock_transport_404)
    with pytest.raises(OllamaModelError):
        await client_404.generate_json("Prompt")

    # Invalid JSON
    mock_transport_invalid = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"response": "not a json string"})
    )
    client_invalid = OllamaClient(base_settings, transport=mock_transport_invalid)
    with pytest.raises(ModelOutputError):
        await client_invalid.generate_json("Prompt")

    # Retry on timeout then fail
    retry_count = 0

    def mock_timeout_handler(request: httpx.Request) -> httpx.Response:
        nonlocal retry_count
        retry_count += 1
        raise httpx.TimeoutException("Timeout", request=request)

    client_timeout = OllamaClient(
        base_settings, transport=httpx.MockTransport(mock_timeout_handler)
    )
    with pytest.raises(OllamaUnavailableError, match="bounded retries"):
        await client_timeout.generate_json("Prompt")
    assert retry_count == 2


@pytest.mark.asyncio
async def test_gemini_client_status(base_settings: Settings) -> None:
    # Unconfigured
    base_settings.gemini_api_key = None
    client_unconf = GeminiClient(base_settings)
    status_unconf = await client_unconf.status()
    assert not status_unconf.configured
    assert not status_unconf.reachable

    # Reachable
    base_settings.gemini_api_key = SecretStr("valid-key")
    mock_sdk = MagicMock()
    mock_sdk.models.get.return_value = MagicMock(name="gemini-2.5-flash")
    client = GeminiClient(base_settings, client=mock_sdk)
    status = await client.status()
    assert status.configured
    assert status.reachable
    assert status.model_available

    # API Error
    mock_sdk.models.get.side_effect = Exception("API connection refused")
    status_err = await client.status()
    assert not status_err.reachable


@pytest.mark.asyncio
async def test_gemini_client_generate_json(base_settings: Settings) -> None:
    # Missing key
    base_settings.gemini_api_key = None
    client_nokey = GeminiClient(base_settings)
    with pytest.raises(GeminiUnavailableError):
        await client_nokey.generate_json("Prompt")

    # Success with markdown stripping
    base_settings.gemini_api_key = SecretStr("valid-key")
    mock_sdk = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '```json\n{"status": "ok", "value": 42}\n```'
    mock_sdk.aio.models.generate_content = AsyncMock(return_value=mock_response)

    client = GeminiClient(base_settings, client=mock_sdk)
    res = await client.generate_json("Prompt")
    assert res == {"status": "ok", "value": 42}

    # API Error 404 Model Error
    mock_resp_404 = MagicMock()
    mock_resp_404.text = "Model not found"
    error_404 = APIError(404, mock_resp_404)
    mock_sdk.aio.models.generate_content.side_effect = error_404
    with pytest.raises(GeminiModelError):
        await client.generate_json("Prompt")

    # General API Error
    mock_resp_429 = MagicMock()
    mock_resp_429.text = "Quota exceeded"
    error_429 = APIError(429, mock_resp_429)
    mock_sdk.aio.models.generate_content.side_effect = error_429
    with pytest.raises(GeminiUnavailableError):
        await client.generate_json("Prompt")

    # Timeout
    mock_sdk.aio.models.generate_content.side_effect = TimeoutError("Timed out")
    with pytest.raises(GeminiUnavailableError, match="timed out"):
        await client.generate_json("Prompt")

    # Invalid JSON
    mock_resp_bad = MagicMock()
    mock_resp_bad.text = "not json"
    mock_sdk.aio.models.generate_content.side_effect = None
    mock_sdk.aio.models.generate_content.return_value = mock_resp_bad
    with pytest.raises(ModelOutputError):
        await client.generate_json("Prompt")


@pytest.mark.asyncio
async def test_composite_ai_client_failover(base_settings: Settings) -> None:
    mock_gemini = AsyncMock(spec=GeminiClient)
    mock_ollama = AsyncMock(spec=OllamaClient)

    # 1. Primary Gemini success
    mock_gemini.generate_json.return_value = {"generated_by": "gemini"}
    composite = CompositeAiClient(
        base_settings, gemini_client=mock_gemini, ollama_client=mock_ollama
    )

    out = await composite.generate_json("Test prompt")
    assert out == {"generated_by": "gemini"}
    assert composite.last_provider_used == "gemini"
    assert not composite.fallback_occurred

    # 2. Primary fails -> Failover to Ollama
    mock_gemini.generate_json.side_effect = GeminiUnavailableError("Quota exceeded 429")
    mock_ollama.generate_json.return_value = {"generated_by": "ollama"}

    out_fallback = await composite.generate_json("Test prompt")
    assert out_fallback == {"generated_by": "ollama"}
    assert composite.last_provider_used == "ollama"
    assert composite.fallback_occurred

    # 3. Both fail -> Raises AiServiceUnavailableError
    mock_ollama.generate_json.side_effect = OllamaUnavailableError("Ollama down")
    with pytest.raises(AiServiceUnavailableError, match="Both primary"):
        await composite.generate_json("Test prompt")

    # 4. Status method tests
    # 4a. Gemini primary ready
    mock_gemini.status.return_value = AiStatusResponse(
        enabled=True,
        configured=True,
        reachable=True,
        selected_model="gemini-2.5-flash",
        model_available=True,
        available_models=["gemini-2.5-flash"],
        detail="Gemini ready",
    )
    mock_ollama.status.return_value = AiStatusResponse(
        enabled=True,
        configured=True,
        reachable=False,
        selected_model="qwen3:4b",
        model_available=False,
        detail="Ollama down",
    )
    st1 = await composite.status()
    assert st1.reachable
    assert "ready" in st1.detail

    # 4b. Gemini unavailable -> Fallback active
    mock_gemini.status.return_value = AiStatusResponse(
        enabled=True,
        configured=True,
        reachable=False,
        selected_model="gemini-2.5-flash",
        model_available=False,
        detail="Gemini down",
    )
    mock_ollama.status.return_value = AiStatusResponse(
        enabled=True,
        configured=True,
        reachable=True,
        selected_model="qwen3:4b",
        model_available=True,
        detail="Ollama ready",
    )
    st2 = await composite.status()
    assert st2.reachable
    assert "Active Fallback" in st2.detail

    # 4c. Both down
    mock_ollama.status.return_value = AiStatusResponse(
        enabled=True,
        configured=True,
        reachable=False,
        selected_model="qwen3:4b",
        model_available=False,
        detail="Ollama down",
    )
    st3 = await composite.status()
    assert not st3.reachable

    # 5. Ollama primary configuration
    base_settings.ai_primary_provider = "ollama"
    comp_ollama = CompositeAiClient(
        base_settings, gemini_client=mock_gemini, ollama_client=mock_ollama
    )
    mock_ollama.generate_json.side_effect = None
    mock_ollama.generate_json.return_value = {"from": "ollama"}
    res_ol = await comp_ollama.generate_json("Test")
    assert res_ol == {"from": "ollama"}

    # Ollama fails -> failover to Gemini
    mock_ollama.generate_json.side_effect = OllamaUnavailableError("down")
    mock_gemini.generate_json.side_effect = None
    mock_gemini.generate_json.return_value = {"from": "gemini"}
    res_ol_fb = await comp_ollama.generate_json("Test")
    assert res_ol_fb == {"from": "gemini"}
