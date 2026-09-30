from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def workflows_dir() -> Path:
    # Workspace root is 3 levels up from tests directory
    root = Path(__file__).resolve().parents[3]
    return root / "n8n" / "workflows"


def test_n8n_workflow_files_exist(workflows_dir: Path) -> None:
    assert workflows_dir.exists(), f"Workflows directory {workflows_dir} must exist."
    workflow_files = list(workflows_dir.glob("*.json"))
    assert len(workflow_files) >= 3, (
        f"Expected at least 3 workflow files, found {len(workflow_files)}"
    )

    expected_files = {
        "01_weekly_planner.json",
        "02_telegram_approval_dispatcher.json",
        "03_telegram_approval_webhook.json",
    }
    actual_files = {f.name for f in workflow_files}
    assert expected_files.issubset(actual_files), (
        f"Missing workflows: {expected_files - actual_files}"
    )


def test_n8n_workflows_valid_json_schema(workflows_dir: Path) -> None:
    for json_file in workflows_dir.glob("*.json"):
        content = json_file.read_text(encoding="utf-8")
        data = json.loads(content)

        # Top-level required keys
        assert "name" in data, f"{json_file.name} missing 'name'"
        assert "nodes" in data, f"{json_file.name} missing 'nodes'"
        assert "connections" in data, f"{json_file.name} missing 'connections'"
        assert isinstance(data["nodes"], list), f"{json_file.name} 'nodes' must be a list"
        assert isinstance(data["connections"], dict), (
            f"{json_file.name} 'connections' must be a dict"
        )

        # Validate nodes
        node_names = set()
        for node in data["nodes"]:
            assert "name" in node, f"Node missing 'name' in {json_file.name}"
            assert "type" in node, f"Node missing 'type' in {json_file.name}"
            assert "position" in node, f"Node missing 'position' in {json_file.name}"
            assert "parameters" in node, f"Node missing 'parameters' in {json_file.name}"
            node_names.add(node["name"])

        # Validate connections: all source and destination nodes must exist
        for source_node, conn_types in data["connections"].items():
            assert source_node in node_names, (
                f"Connection source '{source_node}' not found in nodes of {json_file.name}"
            )
            for _conn_type, outputs in conn_types.items():
                for output_branch in outputs:
                    for target in output_branch:
                        target_node = target.get("node")
                        assert target_node in node_names, (
                            f"Connection target '{target_node}' from '{source_node}' "
                            f"not found in {json_file.name}"
                        )


def test_n8n_workflows_security_no_hardcoded_secrets(workflows_dir: Path) -> None:
    forbidden_tokens = [
        "bot123456",
        "ghp_",
        "AIzaSy",
        "CHANGE_ME",
        "password123",
    ]
    for json_file in workflows_dir.glob("*.json"):
        text = json_file.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in text, (
                f"Forbidden hardcoded token '{token}' found in {json_file.name}"
            )

        # Verify environment variable interpolation is used for sensitive parameters
        if "telegram" in json_file.name.lower():
            assert "$env.TELEGRAM_BOT_TOKEN" in text, (
                f"{json_file.name} must reference $env.TELEGRAM_BOT_TOKEN"
            )
        if "renderer-api" in text:
            assert "$env.INTERNAL_API_KEY" in text, (
                f"{json_file.name} must reference $env.INTERNAL_API_KEY for renderer-api"
            )


def test_telegram_callback_parsing_logic() -> None:
    content_id = str(uuid4())
    version_id = str(uuid4())

    mock_telegram_callback_payload = {
        "callback_query": {
            "id": "query_123456789",
            "from": {
                "id": 987654321,
                "is_bot": False,
                "first_name": "Editorial",
                "username": "tbos_editor",
            },
            "message": {
                "message_id": 42,
                "chat": {"id": -1001234567890, "title": "TBOS Approvals"},
                "caption": "Sample Telegram review caption",
            },
            "data": f"approve:{content_id}:{version_id}",
        }
    }

    # Simulate JavaScript node parser in workflow 03
    callback_query = mock_telegram_callback_payload["callback_query"]
    data = callback_query["data"]
    parts = data.split(":")
    action = parts[0]
    parsed_content_id = parts[1]
    parsed_version_id = parts[2]
    from_user = callback_query["from"]
    reviewer_ref = f"telegram:{from_user['id']} (@{from_user['username']})"

    assert action == "approve"
    assert parsed_content_id == content_id
    assert parsed_version_id == version_id
    assert reviewer_ref == "telegram:987654321 (@tbos_editor)"
