import pytest

from conftest import fixture_backend, fixture_judge, initialize, write_config
from rexbench.experiment import make_plan
from rexbench.reconcile import reconcile
from rexbench.search import run_trial
from rexbench.util import now, write_json, write_jsonl


def test_proven_same_response_reconciles_without_a_model_retry(tmp_path, task, config):
    public = tmp_path / "repair.jsonl"
    write_jsonl(public, [task.model_dump(mode="json")])
    config.data.repair_file = str(public)
    root = tmp_path / "run"
    plan = make_plan(write_config(tmp_path / "config.json", config), root / "plan.json")
    job = plan["jobs"][0]
    store, backend = initialize(root, job), fixture_backend()
    class Crash(BaseException):
        pass
    def crash(point):
        if point == "after_dispatch":
            raise Crash()
    with pytest.raises(Crash):
        run_trial(store, task, job, config, backend, fixture_judge(), "fixture", fault=crash)
    run_trial(store, task, job, config, backend, fixture_judge(), "fixture")
    assert backend.calls == 1 and store.load(job["id"]).ledger.unknown_usage == 1
    row = store.pending(job["id"])
    request = store.object(row["request_blob"])
    evidence = {"request_id": request["attempt_id"], "prompt_hash": request["prompt_hash"],
                "model_digest": request["model_digest"], "provider_request_id": "synthetic-provider-fixture-1",
                "origin": "transport_capture", "evidence_description": "Synthetic exact-request transport fixture",
                "response": backend.script[0], "text": "print(0)", "input_tokens": 40, "output_tokens": 20,
                "finish_reason": "stop", "usage_definition": "synthetic logical token counts", "started": row["started"],
                "finished": now(), "latency_seconds": .01}
    path = tmp_path / "recovered.json"
    write_json(path, {**evidence, "prompt_hash": "wrong"})
    store.close()
    with pytest.raises(ValueError, match="fingerprint"):
        reconcile(root, path)
    write_json(path, evidence)
    assert reconcile(root, path)["model_calls"] == 0
    assert backend.calls == 1
    with pytest.raises(ValueError, match="uncertain"):
        reconcile(root, path)
    from rexbench.store import Store
    store = Store(root)
    resumed = fixture_backend()
    result = run_trial(store, task, job, config, resumed, fixture_judge(), "fixture")
    assert backend.calls + resumed.calls == 4
    assert result.ledger.tokens == 240 and result.ledger.unknown_usage == 0
    assert result.ledger.policy_steps == 4
    assert len(store.rows("SELECT * FROM generations")) == 4
    store.close()
