"""Import independently recovered evidence for the SAME uncertain request, never regenerate it."""
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from .experiment import validate_plan, writer_lock
from .store import Store
from .types import GenerationRequest, GenerationResult, Record
from .util import read_json, sha


class RecoveredResponse(Record):
    request_id: str
    prompt_hash: str
    model_digest: str
    provider_request_id: str = Field(min_length=1)
    origin: Literal["local_server_log", "transport_capture"]
    evidence_description: str = Field(min_length=10)
    response: dict
    text: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    finish_reason: str
    usage_definition: str = Field(min_length=10)
    started: str
    finished: str
    latency_seconds: float = Field(ge=0)


def reconcile(root: Path, evidence_path: Path):
    if (root / "seal.json").exists():
        raise ValueError("Cannot reconcile a sealed experiment")
    evidence = RecoveredResponse.model_validate(read_json(evidence_path))
    validate_plan(read_json(root / "plan.json"))
    started, finished = datetime.fromisoformat(evidence.started), datetime.fromisoformat(evidence.finished)
    if started.tzinfo is None or finished.tzinfo is None or finished < started:
        raise ValueError("Recovery timestamps must be ordered and timezone-aware")
    with writer_lock(root):
        store = Store(root)
        try:
            row = store.db.execute("SELECT * FROM requests WHERE id=?", (evidence.request_id,)).fetchone()
            if row is None or row["state"] not in ("dispatched", "unknown") or row["response_blob"]:
                raise ValueError("Only an uncertain request without a persisted response may be reconciled")
            request = GenerationRequest.model_validate(store.object(row["request_blob"]))
            if request.prompt_hash != evidence.prompt_hash or request.model_digest != evidence.model_digest:
                raise ValueError("Recovered prompt/model fingerprint does not match the original request")
            if row["started"] != evidence.started:
                raise ValueError("Recovered request start does not match the dispatch ledger")
            previous = store.rows("SELECT payload FROM events WHERE kind='request_reconciled'")
            import json
            if any(json.loads(item["payload"])["provider_request_id"] == evidence.provider_request_id for item in previous):
                raise ValueError("Provider request ID was already consumed")
            # Preserve the provider's original fields. This normalized envelope is read only for this request.
            raw = evidence.response.copy()
            raw["_rex_recovered"] = evidence.model_dump(mode="json")
            raw["text"] = evidence.text
            raw["input_tokens"] = evidence.input_tokens
            raw["output_tokens"] = evidence.output_tokens
            # Ollama normalizer reads its native fields; explicit recovered text/counts must agree.
            if request.backend == "ollama":
                if raw.get("message", {}).get("content") != evidence.text or raw.get("prompt_eval_count") != evidence.input_tokens or raw.get("eval_count") != evidence.output_tokens:
                    raise ValueError("Recovered evidence disagrees with native Ollama usage/content")
            GenerationResult(request_id=request.attempt_id, text=evidence.text, raw=raw,
                             finish_reason=evidence.finish_reason, input_tokens=evidence.input_tokens,
                             output_tokens=evidence.output_tokens, usage_definition=evidence.usage_definition,
                             started=evidence.started, finished=evidence.finished, latency_seconds=evidence.latency_seconds)
            state = store.load(row["trial_id"])
            if state is None:
                raise ValueError("Missing pre-request checkpoint")
            if row["state"] == "unknown" and state.ledger.unknown_usage:
                state.ledger.unknown_usage -= 1
            with store.transaction():
                blob = store.put(raw)
                store.db.execute("UPDATE requests SET state='responded',response_blob=?,finished=?,latency=?,error=NULL WHERE id=?",
                                 (blob, evidence.finished, evidence.latency_seconds, evidence.request_id))
                store.event(row["trial_id"], "request_reconciled", {"request_id": evidence.request_id,
                            "provider_request_id": evidence.provider_request_id, "evidence_hash": sha(evidence_path.read_bytes()),
                            "evidence_blob": store.put(evidence.model_dump(mode="json")), "origin": evidence.origin})
                store.checkpoint(state, "paused")
            return {"request_id": evidence.request_id, "state": "responded", "model_calls": 0,
                    "next": "resume; the recovered response will be judged and committed exactly once"}
        finally:
            store.close()
