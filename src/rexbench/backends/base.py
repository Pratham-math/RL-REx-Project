from typing import Protocol

from ..types import GenerationRequest, GenerationResult


class OutcomeUnknown(RuntimeError):
    """Dispatch may have consumed inference. Must never be retried as free work."""


class RejectedBeforeInference(RuntimeError):
    """Verified explicit rejection; no inference was accepted."""


class Backend(Protocol):
    def info(self) -> dict: ...
    def dispatch(self, request: GenerationRequest) -> dict: ...
    def normalize(self, request: GenerationRequest, raw: dict, started: str,
                  finished: str, latency: float) -> GenerationResult: ...
