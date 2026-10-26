from ..types import GenerationRequest, GenerationResult
from ..util import fingerprint


class MockBackend:
    """Synthetic fixture backend. Indexed by attempt, never shared as empirical model work."""

    def __init__(self, script: list[dict]):
        if not script:
            raise ValueError("Mock script must not be empty")
        self.script = script
        self.calls = 0

    def info(self):
        return {"backend": "mock", "digest": fingerprint(self.script), "synthetic": True,
                "seed_support": "scripted", "usage_semantics": "synthetic logical tokens"}

    def dispatch(self, request: GenerationRequest) -> dict:
        self.calls += 1
        step = int(request.attempt_id.rsplit(":", 1)[1])
        return self.script[(step - 1) % len(self.script)].copy()

    def normalize(self, request, raw, started, finished, latency):
        return GenerationResult(request_id=request.attempt_id, text=raw.get("text", ""), raw=raw,
                                finish_reason=raw.get("finish_reason", "stop"),
                                input_tokens=raw.get("input_tokens"), output_tokens=raw.get("output_tokens"),
                                usage_definition="synthetic logical tokens", started=started,
                                finished=finished, latency_seconds=latency)
