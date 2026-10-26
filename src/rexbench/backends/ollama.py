from __future__ import annotations

import json
import base64
import time
import urllib.error
import urllib.request

from ..config import Model
from ..prompts import admissible
from ..types import GenerationResult
from ..util import fingerprint
from .base import OutcomeUnknown, RejectedBeforeInference


class OllamaBackend:
    def __init__(self, config: Model):
        self.config = config

    def _http(self, path: str, payload: dict | None = None):
        request = urllib.request.Request(self.config.endpoint.rstrip("/") + path,
                                         data=None if payload is None else json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
        timeout = min(self.config.request_timeout_seconds, getattr(self, "deadline", float("inf")) - time.monotonic())
        if timeout <= 0:
            raise TimeoutError("Campaign deadline reached")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            # Bounded model response, including any auxiliary fields.
            body = response.read(16 * 1024 * 1024 + 1)
            if len(body) > 16 * 1024 * 1024:
                raise OutcomeUnknown("Model response exceeded 16 MiB transport cap")
            try:
                parsed = json.loads(body)
            except (ValueError, UnicodeError):
                if path != "/api/chat":
                    raise
                return {"_raw_http_body_base64": base64.b64encode(body).decode(),
                        "error": "INVALID_BACKEND_JSON"}
            if path == "/api/chat":
                if not isinstance(parsed, dict):
                    parsed = {"error": "INVALID_BACKEND_RESPONSE_TYPE"}
                parsed["_raw_http_body_base64"] = base64.b64encode(body).decode()
            return parsed

    def info(self):
        tags = self._http("/api/tags")
        models = [m for m in tags["models"] if m["name"] == self.config.name]
        if len(models) != 1:
            raise RuntimeError("Configured local model is missing or ambiguous; no fallback")
        item = models[0]
        if self.config.digest and item["digest"] != self.config.digest:
            raise RuntimeError("Model digest drift")
        details = self._http("/api/show", {"model": self.config.name})
        version = self._http("/api/version")
        context_caps = [v for k, v in details.get("model_info", {}).items() if k.endswith(".context_length")]
        if context_caps and self.config.context_tokens > min(context_caps):
            raise RuntimeError("Configured context exceeds model context")
        return {"backend": "ollama", "digest": item["digest"], "listing": item,
                "show": details, "version": version, "context_tokens": self.config.context_tokens,
                "seed_support": "requested; bitwise determinism unverified",
                "usage_semantics": "prompt_eval_count + eval_count; repeated-prompt verification pending",
                "token_counter": "UTF-8 bytes + 256 envelope admission; unverified bound; strict cap unsupported",
                "template_hash": fingerprint(details.get("template"))}

    def dispatch(self, request):
        # Check immutable pins before each dispatch; GETs are not inference requests.
        self.info()
        prompt = "\n".join(m.content for m in request.messages)
        if not admissible(prompt, request.context_tokens, request.output_limit):
            raise RejectedBeforeInference("Context admission rejected before inference")
        try:
            return self._http("/api/chat", {
                "model": self.config.name, "stream": False,
                "messages": [{"role": m.role, "content": m.content} for m in request.messages],
                "options": {"temperature": request.temperature, "num_predict": request.output_limit,
                            "num_ctx": request.context_tokens, "seed": request.generation_seed}})
        except urllib.error.HTTPError as exc:
            # Only explicit validation/model-not-found errors are certified rejections.
            if exc.code in (400, 404, 413, 422):
                raise RejectedBeforeInference(f"Explicit HTTP rejection {exc.code}") from exc
            raise OutcomeUnknown(f"HTTP {exc.code}; inference outcome uncertain") from exc
        except (OSError, ValueError) as exc:
            raise OutcomeUnknown(f"Transport/response failure: {type(exc).__name__}") from exc

    def normalize(self, request, raw, started, finished, latency):
        error = raw.get("error")
        if raw.get("done_reason") in ("context_length", "context_overflow", "prompt_too_long"):
            error = "CONTEXT_OVERFLOW"
        # Explicit API overflow is a persisted failed request, never silently truncated input.
        if error:
            error = str(error)[:1000]
        return GenerationResult(request_id=request.attempt_id,
                                text=raw.get("message", {}).get("content", ""), raw=raw,
                                finish_reason=raw.get("done_reason", "unknown"),
                                input_tokens=raw.get("prompt_eval_count"), output_tokens=raw.get("eval_count"),
                                usage_definition="Ollama prompt_eval_count logical input; eval_count output; raw retained",
                                started=started, finished=finished, latency_seconds=latency, backend_error=error)
