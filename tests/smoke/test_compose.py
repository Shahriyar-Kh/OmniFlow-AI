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
