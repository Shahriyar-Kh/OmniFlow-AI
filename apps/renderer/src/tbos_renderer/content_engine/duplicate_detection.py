from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
from typing import Any


def normalize_text(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", value.casefold()).split())


def content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def is_close_duplicate(candidate: str, existing: str, threshold: float = 0.88) -> bool:
    left, right = normalize_text(candidate), normalize_text(existing)
    return bool(left and right and SequenceMatcher(None, left, right).ratio() >= threshold)


def has_duplicate(candidate: str, existing_values: list[str]) -> bool:
    return any(is_close_duplicate(candidate, value) for value in existing_values)
