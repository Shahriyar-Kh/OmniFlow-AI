from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined, select_autoescape
from pydantic import BaseModel, ConfigDict, Field

from tbos_renderer.content_engine.constants import PROMPT_INJECTION_MARKERS
from tbos_renderer.content_engine.exceptions import PromptInjectionError


class PromptTemplateDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: int = Field(ge=1)
    purpose: str
    expected_input_fields: list[str]
    expected_output_schema: str
    system_instructions: str
    safety_instructions: str
    brand_instructions: str
    template: str
    example_output: dict[str, Any] | None = None
    active: bool = True
    created_at: str
    updated_at: str

    @property
    def checksum(self) -> str:
        serialized = json.dumps(self.model_dump(), sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(serialized.encode()).hexdigest()


class PromptLibrary:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.environment = Environment(
            undefined=StrictUndefined,
            autoescape=select_autoescape(default=True),
            keep_trailing_newline=True,
        )

    def load(self, name: str, version: int = 1) -> PromptTemplateDefinition:
        path = self.directory / f"{name}_v{version}.yaml"
        if not path.is_file():
            raise FileNotFoundError(f"Prompt template not found: {name} v{version}")
        with path.open(encoding="utf-8") as handle:
            return PromptTemplateDefinition.model_validate(yaml.safe_load(handle))

    def load_all(self) -> list[PromptTemplateDefinition]:
        values: list[PromptTemplateDefinition] = []
        for path in sorted(self.directory.glob("*_v*.yaml")):
            with path.open(encoding="utf-8") as handle:
                values.append(PromptTemplateDefinition.model_validate(yaml.safe_load(handle)))
        return values

    def render(self, definition: PromptTemplateDefinition, context: dict[str, Any]) -> str:
        missing = [field for field in definition.expected_input_fields if field not in context]
        if missing:
            raise ValueError(f"Missing prompt input fields: {', '.join(missing)}")
        template = self.environment.from_string(definition.template)
        return "\n\n".join(
            [
                f"SYSTEM RULES:\n{definition.system_instructions}",
                f"SAFETY RULES:\n{definition.safety_instructions}",
                f"BRAND RULES:\n{definition.brand_instructions}",
                template.render(**context),
            ]
        )


def validate_untrusted_input(*values: str | None) -> None:
    combined = " ".join(value or "" for value in values).casefold()
    marker = next((item for item in PROMPT_INJECTION_MARKERS if item in combined), None)
    if marker:
        raise PromptInjectionError("Untrusted input contains a policy-bypass instruction.")


def delimit_untrusted(value: str) -> str:
    return f"<untrusted-input>{json.dumps(value, ensure_ascii=False)}</untrusted-input>"
