"""Explicit local-only measured-usage verification. No hosted adapters or fallback."""
from pathlib import Path
import time

import pytest

from rexbench.backends.ollama import OllamaBackend
from rexbench.config import load_config
from rexbench.types import GenerationRequest, Message
from rexbench.util import now, sha, write_json

pytestmark = pytest.mark.live


def test_real_local_repeated_prompt_usage():
    config = load_config(Path("configs/live_smoke.yaml"))
    backend = OllamaBackend(config.model)
    try:
        info = backend.info()
    except Exception as exc:
        pytest.skip(f"Configured local model unavailable: {exc}")
    backend.config.digest = info["digest"]
    records = []
    for i in range(2):
        prompt = "Return one Python code block that prints 1."
        req = GenerationRequest(experiment_id="local-usage-contract", trial_id="usage", attempt_id=f"usage:{i+1}",
                                messages=[Message(role="user", content=prompt)], prompt_hash=sha(prompt),
                                backend="ollama", model_digest=info["digest"], temperature=1., output_limit=128,
                                context_tokens=config.model.context_tokens, generation_seed=0, kind="generation")
        started, timer = now(), time.monotonic()
        raw = backend.dispatch(req)
        write_json(Path(f"reports/live_usage_raw_{i}.json"), raw)
        result = backend.normalize(req, raw, started, now(), time.monotonic() - timer)
        assert result.input_tokens is not None and result.input_tokens > 0
        assert result.output_tokens is not None and result.output_tokens > 0
        records.append(result.model_dump(mode="json"))
    assert records[0]["input_tokens"] == records[1]["input_tokens"], "Investigate prompt/cache usage semantics"
    write_json(Path("reports/live_usage_contract.json"), {"model_info": info, "records": records,
               "usage_check": "Same logical prompt count on repeated identical prompt; original fields retained",
               "seed_determinism": "not promised"})
