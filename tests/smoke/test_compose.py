from pathlib import Path

import yaml


def test_compose_has_local_only_ports_and_no_postgres_port() -> None:
    compose_path = Path(__file__).resolve().parents[2] / "compose.yaml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = compose["services"]
    assert "ports" not in services["postgres"]
    assert services["n8n"]["ports"] == ["127.0.0.1:${N8N_PORT:-5678}:5678"]
    assert services["renderer-api"]["ports"] == ["127.0.0.1:${APP_PORT:-8080}:8080"]
    assert services["postgres"]["networks"] == ["tbos_private"]


def test_images_are_explicitly_versioned() -> None:
    compose_path = Path(__file__).resolve().parents[2] / "compose.yaml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    assert compose["services"]["postgres"]["image"] == "postgres:17.11-alpine3.24"
    assert compose["services"]["n8n"]["image"] == "n8nio/n8n:2.39.8"
    dockerfile = (compose_path.parent / "apps/renderer/Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.13.15-slim-bookworm" in dockerfile


def test_production_compose_overlay_configuration() -> None:
    prod_compose_path = Path(__file__).resolve().parents[2] / "docker-compose.prod.yml"
    assert prod_compose_path.is_file()
    prod_compose = yaml.safe_load(prod_compose_path.read_text(encoding="utf-8"))
    services = prod_compose["services"]
    assert services["renderer-api"]["environment"]["APP_ENV"] == "production"
    assert services["renderer-api"]["environment"]["APP_OPENAPI_ENABLED"] == "false"
    assert services["n8n"]["environment"]["N8N_SECURE_COOKIE"] == "true"
    assert services["cloudflared"]["image"] == "cloudflare/cloudflared:2024.12.0"
    assert "tbos_edge" in services["cloudflared"]["networks"]

