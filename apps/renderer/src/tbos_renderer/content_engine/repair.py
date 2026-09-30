from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from pydantic import ValidationError

from tbos_renderer.content_engine.client import AiClient
from tbos_renderer.content_engine.constants import MAX_REPAIR_ATTEMPTS
from tbos_renderer.content_engine.exceptions import ModelOutputError

T = TypeVar("T")
Validator = Callable[[dict[str, Any]], T]


async def generate_with_repair[T](
    client: AiClient,
    prompt: str,
    *,
    schema: Mapping[str, Any],
    validator: Validator[T],
    repair_prompt: Callable[[dict[str, Any], list[str]], str],
    max_repairs: int = MAX_REPAIR_ATTEMPTS,
) -> tuple[T, int]:
    current_prompt = prompt
    previous: dict[str, Any] = {}
    failures: list[str] = []
    for attempt in range(max_repairs + 1):
        try:
            previous = await client.generate_json(current_prompt, schema=schema)
            return validator(previous), attempt
        except (ValidationError, ValueError, ModelOutputError) as error:
            if isinstance(error, ValidationError):
                failures = [
                    f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                    for item in error.errors(include_url=False)
                ]
            elif isinstance(error, ModelOutputError):
                failures = error.errors or [str(error)]
            else:
                failures = [str(error)]
            if attempt >= max_repairs:
                break
            current_prompt = repair_prompt(previous, failures)
    safe_failures = [message[:500] for message in failures]
    raise ModelOutputError("Model output remained invalid after bounded repair.", safe_failures)


def build_repair_prompt(previous: dict[str, Any], errors: list[str]) -> str:
    return (
        "Repair only the invalid fields in the JSON object. Preserve valid educational content. "
        "Never remove or weaken safety constraints. Return only strict JSON.\n"
        f"VALIDATION ERRORS:\n{json.dumps(errors, ensure_ascii=False)}\n"
        f"FAILED JSON:\n{json.dumps(previous, ensure_ascii=False)}"
    )
