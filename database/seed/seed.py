from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import insert
from tbos_renderer.config import get_settings
from tbos_renderer.content_engine.prompts import PromptLibrary
from tbos_renderer.database import create_database_engine
from tbos_renderer.models import PromptTemplate, SystemSetting

SETTINGS: list[dict[str, Any]] = [
    {
        "key": "brand",
        "value": {"name": "TechBuilt Open School", "slug": "techbuilt-open-school"},
        "description": "Canonical local brand identity.",
    },
    {
        "key": "content_pillars",
        "value": {
            "items": [
                "AI Tools and Practical AI",
                "Python and Automation",
                "Computer Science Concepts",
                "Career and Portfolio Projects",
                "Cyber Safety and Digital Literacy",
            ]
        },
        "description": "Default editorial pillars.",
    },
    {
        "key": "enabled_formats",
        "value": {"items": ["Poster", "Reel"]},
        "description": "Phase target content formats.",
    },
    {
        "key": "weekly_targets",
        "value": {"poster": 4, "reel": 3},
        "description": "Default weekly output targets.",
    },
    {
        "key": "default_language_style",
        "value": {"text": "Roman Urdu with clear, simple English technical terms."},
        "description": "Default editorial language style.",
    },
]


def seed() -> None:
    settings = get_settings()
    prompts = PromptLibrary(settings.prompt_templates_path).load_all()
    engine = create_database_engine(settings)
    try:
        with engine.begin() as connection:
            for row in SETTINGS:
                statement = insert(SystemSetting).values(**row)
                connection.execute(
                    statement.on_conflict_do_update(
                        index_elements=[SystemSetting.key],
                        set_={
                            "value": statement.excluded.value,
                            "description": statement.excluded.description,
                        },
                    )
                )
            for prompt in prompts:
                template_text = "\n\n".join(
                    [
                        prompt.system_instructions,
                        prompt.safety_instructions,
                        prompt.brand_instructions,
                        prompt.template,
                    ]
                )
                statement = insert(PromptTemplate).values(
                    name=prompt.name,
                    version=prompt.version,
                    purpose=prompt.purpose,
                    template_text=template_text,
                    language_style="Roman Urdu with simple English technical terms.",
                    is_active=prompt.active,
                    model_metadata={
                        "checksum": prompt.checksum,
                        "expected_input_fields": prompt.expected_input_fields,
                        "expected_output_schema": prompt.expected_output_schema,
                        "source": f"config/prompts/{prompt.name}_v{prompt.version}.yaml",
                    },
                )
                connection.execute(
                    statement.on_conflict_do_update(
                        constraint="uq_prompt_template_version",
                        set_={
                            "purpose": statement.excluded.purpose,
                            "template_text": statement.excluded.template_text,
                            "language_style": statement.excluded.language_style,
                            "is_active": statement.excluded.is_active,
                            "model_metadata": statement.excluded.model_metadata,
                        },
                    )
                )
    finally:
        engine.dispose()


if __name__ == "__main__":
    seed()
