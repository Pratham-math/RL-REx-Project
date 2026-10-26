import urllib.error

import pytest

from rexbench.backends.base import OutcomeUnknown, RejectedBeforeInference
from rexbench.backends.ollama import OllamaBackend
from rexbench.config import Model
from rexbench.types import GenerationRequest, Message


def request():
    return GenerationRequest(experiment_id="e", trial_id="t", attempt_id="t:1", messages=[Message(role="user", content="print one")],
                             prompt_hash="h", backend="ollama", model_digest="a", temperature=1., output_limit=2048,
                             context_tokens=16384, generation_seed=7, kind="generation")


def info_http(path, payload=None):
    if path == "/api/tags":
        return {"models": [{"name": "qwen2.5-coder:7b", "digest": "a", "details": {"quantization_level": "fixture"}}]}
    if path == "/api/show":
        return {"template": "fixture-template", "model_info": {"qwen.context_length": 32768}}
    return {"version": "fixture"}


def test_info_and_drift_and_context(monkeypatch):
    adapter = OllamaBackend(Model(digest="a"))
    monkeypatch.setattr(adapter, "_http", info_http)
    assert adapter.info()["digest"] == "a"
    adapter.config.digest = "changed"
    with pytest.raises(RuntimeError, match="drift"):
        adapter.info()
    adapter.config.digest = "a"
    adapter.config.context_tokens = 65536
    with pytest.raises(RuntimeError, match="context"):
        adapter.info()


def test_explicit_options_raw_usage_and_missing_usage(monkeypatch):
    adapter = OllamaBackend(Model(digest="a"))
    captured = []
    raw = {"message": {"content": "print(1)"}, "done_reason": "length", "prompt_eval_count": 12, "eval_count": 8,
           "prompt_eval_duration": 99}
    def http(path, payload=None):
        if path == "/api/chat":
            captured.append(payload)
            return raw
        return info_http(path, payload)
    monkeypatch.setattr(adapter, "_http", http)
    req = request()
    response = adapter.dispatch(req)
    normalized = adapter.normalize(req, response, "a", "b", 1.)
    assert normalized.input_tokens == 12 and normalized.output_tokens == 8
    assert normalized.raw == raw and normalized.finish_reason == "length"
    assert captured[0]["stream"] is False
    assert captured[0]["options"] == {"temperature": 1., "seed": 7, "num_predict": 2048, "num_ctx": 16384}
    missing = adapter.normalize(req, {"message": {"content": ""}}, "a", "b", 1.)
    assert missing.input_tokens is None and missing.output_tokens is None
    assert "unverified" in adapter.info()["seed_support"]


@pytest.mark.parametrize("status,exception", [(400, RejectedBeforeInference), (404, RejectedBeforeInference),
                                               (500, OutcomeUnknown), (503, OutcomeUnknown)])
def test_transport_classification(monkeypatch, status, exception):
    adapter = OllamaBackend(Model(digest="a"))
    def http(path, payload=None):
        if path == "/api/chat":
            raise urllib.error.HTTPError("http://localhost", status, "fixture", {}, None)
        return info_http(path, payload)
    monkeypatch.setattr(adapter, "_http", http)
    with pytest.raises(exception):
        adapter.dispatch(request())


def test_timeout_is_unknown_not_free_retry(monkeypatch):
    adapter = OllamaBackend(Model(digest="a"))
    monkeypatch.setattr(adapter, "info", lambda: {})
    def timeout(*_args):
        raise TimeoutError()
    monkeypatch.setattr(adapter, "_http", timeout)
    with pytest.raises(OutcomeUnknown):
        adapter.dispatch(request())


def test_before_request_context_rejection(monkeypatch):
    adapter = OllamaBackend(Model(digest="a"))
    monkeypatch.setattr(adapter, "info", lambda: {})
    req = request()
    req.messages[0].content = "x" * 17000
    with pytest.raises(RejectedBeforeInference):
        adapter.dispatch(req)
