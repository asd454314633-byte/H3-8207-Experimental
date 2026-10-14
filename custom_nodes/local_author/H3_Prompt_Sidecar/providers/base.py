"""Provider-neutral model contract. No transport/runtime fields in requests."""
from dataclasses import dataclass, field
from typing import Any, Callable
from abc import ABC, abstractmethod

@dataclass
class ModelRequest:
    messages: list[dict[str, str]] = field(default_factory=list)
    system: str | None = None
    max_tokens: int = 4000
    temperature: float = 0.3
    top_p: float = 0.9
    stop: list[str] | None = None
    structured_output: dict[str, Any] | None = None
    timeout: float = 180
    metadata: dict[str, Any] = field(default_factory=dict)
    on_text: Callable[[str], None] | None = None

@dataclass
class ModelResponse:
    text: str
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    latency_ms: int
    provider: str
    model: str
    raw_metadata: dict[str, Any] = field(default_factory=dict)

class ProviderError(RuntimeError):
    pass

class FallbackableError(ProviderError):
    """Transport-level failure that legitimately allows an AUTO chain to move
    to the next model: 429, quota exhausted, provider unavailable, model
    removed, 5xx, or timeout before any valid response.  Gate/content failures
    must NEVER raise this."""
    pass

class GenerationLoopError(ProviderError):
    def __init__(self, message, partial_text=""):
        super().__init__(message)
        self.partial_text = partial_text

class ModelProvider(ABC):
    @abstractmethod
    def generate(self, request: ModelRequest) -> ModelResponse: ...
    @abstractmethod
    def health(self) -> bool: ...
    @abstractmethod
    def capabilities(self) -> dict: ...
