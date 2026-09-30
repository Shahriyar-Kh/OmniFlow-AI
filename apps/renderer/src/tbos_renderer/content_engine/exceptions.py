class ContentEngineError(Exception):
    """Base content-engine error safe to map to a typed API response."""


class OllamaUnavailableError(ContentEngineError):
    pass


class OllamaModelError(ContentEngineError):
    pass


class GeminiUnavailableError(ContentEngineError):
    pass


class GeminiModelError(ContentEngineError):
    pass


class AiServiceUnavailableError(ContentEngineError):
    pass


class ModelOutputError(ContentEngineError):
    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


class PromptInjectionError(ContentEngineError):
    pass


class DuplicateContentError(ContentEngineError):
    pass


class ContentNotFoundError(ContentEngineError):
    pass
