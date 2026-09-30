from __future__ import annotations

import json
import re

from tbos_renderer.content_engine.constants import (
    BANNED_CLAIM_MARKERS,
    DEFAULT_QA_THRESHOLD,
    PROMPT_INJECTION_MARKERS,
    QA_ENGINE_VERSION,
    ROMAN_URDU_MARKERS,
)
from tbos_renderer.content_engine.facts import find_numerical_claims, needs_approved_facts
from tbos_renderer.content_engine.schemas import (
    ContentLanguage,
    ContentQualityReport,
    FactSensitivity,
    IssueSeverity,
    PosterContent,
    QualityIssue,
    ReelContent,
)


def _issue(
    code: str,
    category: str,
    severity: IssueSeverity,
    message: str,
    field: str | None = None,
    fix: str | None = None,
) -> QualityIssue:
    return QualityIssue(
        code=code,
        category=category,
        severity=severity,
        message=message,
        field=field,
        suggested_fix=fix,
    )


def evaluate_content(
    content: PosterContent | ReelContent,
    *,
    recent_topics: list[str] | None = None,
    recent_hooks: list[str] | None = None,
    threshold: int = DEFAULT_QA_THRESHOLD,
) -> ContentQualityReport:
    payload = content.model_dump(mode="json")
    combined = json.dumps(payload, ensure_ascii=False).casefold()
    blocking: list[QualityIssue] = []
    warnings: list[QualityIssue] = []
    score = 100

    for marker in BANNED_CLAIM_MARKERS:
        if marker in combined:
            blocking.append(
                _issue("BANNED_CLAIM", "safety", IssueSeverity.CRITICAL, f"Banned claim: {marker}")
            )
            score -= 40
    for marker in PROMPT_INJECTION_MARKERS:
        if marker in combined:
            blocking.append(
                _issue(
                    "PROMPT_INJECTION",
                    "safety",
                    IssueSeverity.CRITICAL,
                    "Prompt-injection language is not allowed.",
                )
            )
            score -= 40

    source_count = len(content.metadata.sources_used)
    numerical = find_numerical_claims(combined)
    fact_review = needs_approved_facts(content.metadata.fact_sensitivity, combined)
    if fact_review and source_count == 0:
        severity = (
            IssueSeverity.BLOCKING
            if content.metadata.fact_sensitivity is FactSensitivity.HIGH
            else IssueSeverity.WARNING
        )
        target = blocking if severity is IssueSeverity.BLOCKING else warnings
        target.append(
            _issue(
                "NEEDS_FACT_REVIEW",
                "facts",
                severity,
                "Specific or sensitive claims require reviewed supporting facts.",
                fix="Remove the claim or attach an approved source.",
            )
        )
        score -= 25 if severity is IssueSeverity.BLOCKING else 10

    if content.metadata.language is ContentLanguage.ROMAN_URDU:
        words = set(re.findall(r"[a-z]+", combined))
        if len(words & ROMAN_URDU_MARKERS) < 2:
            warnings.append(
                _issue(
                    "LANGUAGE_STYLE",
                    "language",
                    IssueSeverity.WARNING,
                    "Roman Urdu markers are limited; review the language style.",
                )
            )
            score -= 8

    if isinstance(content, ReelContent):
        narration_word_count = len(content.narration.split())
        expected_max = int(content.target_duration_seconds * 3.2)
        if narration_word_count > expected_max:
            warnings.append(
                _issue(
                    "NARRATION_LENGTH",
                    "readability",
                    IssueSeverity.WARNING,
                    "Narration may be too long for the target duration.",
                    "narration",
                )
            )
            score -= 8
        if recent_hooks and content.hook.casefold() in {value.casefold() for value in recent_hooks}:
            blocking.append(
                _issue("DUPLICATE_HOOK", "duplication", IssueSeverity.BLOCKING, "Hook was reused.")
            )
            score -= 20

    if recent_topics and content.metadata.topic.casefold() in {
        value.casefold() for value in recent_topics
    }:
        blocking.append(
            _issue("DUPLICATE_TOPIC", "duplication", IssueSeverity.BLOCKING, "Topic was reused.")
        )
        score -= 20

    if numerical and not fact_review:
        warnings.append(
            _issue(
                "NUMERICAL_CLAIM",
                "facts",
                IssueSeverity.WARNING,
                "Numerical text was detected and should be reviewed.",
            )
        )
        score -= 5

    score = max(0, score)
    passed = score >= threshold and not blocking
    fixes = [issue.suggested_fix for issue in [*blocking, *warnings] if issue.suggested_fix]
    return ContentQualityReport(
        score=score,
        passed=passed,
        blocking_issues=blocking,
        warnings=warnings,
        notes=["QA_PASSED never constitutes human approval."],
        human_review_required=True,
        fact_review_required=fact_review and source_count == 0,
        suggested_fixes=fixes,
        qa_engine_version=QA_ENGINE_VERSION,
    )
