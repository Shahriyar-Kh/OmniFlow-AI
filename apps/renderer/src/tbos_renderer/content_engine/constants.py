from typing import Final

QA_ENGINE_VERSION: Final = "2.0.0"
MAX_REPAIR_ATTEMPTS: Final = 2
DEFAULT_QA_THRESHOLD: Final = 85
ROMAN_URDU_MARKERS: Final = {
    "aap",
    "apni",
    "hain",
    "hai",
    "ka",
    "ke",
    "ki",
    "ko",
    "mein",
    "se",
    "yeh",
}
PROMPT_INJECTION_MARKERS: Final = (
    "ignore previous",
    "ignore all instructions",
    "reveal system prompt",
    "show your system prompt",
    "print the api key",
    "bypass policy",
    "developer message",
)
BANNED_CLAIM_MARKERS: Final = (
    "guaranteed income",
    "guaranteed job",
    "become an expert overnight",
    "100% guaranteed",
    "instant success",
)
