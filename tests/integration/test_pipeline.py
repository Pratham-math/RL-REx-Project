import json
from pathlib import Path

import pytest

from rexbench.config import CORE
from rexbench.evaluate import evaluate, seal, verify_seal
from rexbench.experiment import execute, make_plan
from rexbench.judge.mock import MockJudge
from rexbench.replay import replay
from rexbench.report import report
from rexbench.store import Store
from rexbench.types import Case, HiddenTask, suite_hash
from rexbench.util import write_json, write_jsonl
from conftest import write_config


@pytest.fixture
def campaign(tmp_path, task, config, monkeypatch):
    monkeypatch.chdir(tmp_path)
    model = tmp_path / "model.json"
    judge = tmp_path / "judge.json"
    write_json(model, [{"text": "print(0)", "input_tokens": 40, "output_tokens": 20}])
    write_json(judge, {"print(0)": {"c0": "PASS", "default": "WRONG_ANSWER"}})
    public = tmp_path / "repair.jsonl"
    write_jsonl(public, [task.model_dump(mode="json")])
    config.model.mock_script = str(model)
    config.judge.mock_script = str(judge)
    config.data.repair_file = str(public)
    config.experiment.methods = CORE.copy()
    config.budgets.max_dispatched_calls = 24
    plan_path = tmp_path / "run" / "plan.json"
    make_plan(write_config(tmp_path / "config.json", config), plan_path)
    hidden_cases = [Case(id=f"h{i}", input=f"{i+100}\n", output="wrong") for i in range(5)]
    hidden_task = HiddenTask(task_id=task.task_id, hidden_tests=hidden_cases, comparator=task.comparator,
                             limits=task.limits, test_hash=suite_hash(hidden_cases))
    hidden_path = tmp_path / "hidden.jsonl"
    write_jsonl(hidden_path, [hidden_task.model_dump(mode="json")])
    return plan_path, hidden_path, config


def test_complete_offline_pipeline_and_inert_hidden_failure(campaign, tmp_path):
    plan_path, hidden_path, config = campaign
    result = execute(plan_path)
    assert result["complete"] and result["inference_attempts"] == 24
    root = plan_path.parent
    frozen = seal(root)
    store = Store(root, readonly=True)
    before = store.logical_dump()
    store.close()
    hidden = evaluate(root, hidden_path, MockJudge(json.loads(Path(config.judge.mock_script).read_bytes())))
    assert all(not r["solved"] for r in hidden["rows"])
    assert execute(plan_path)["complete"]  # sealed resume does nothing
    assert verify_seal(root)["seal_hash"] == frozen["seal_hash"]
    store = Store(root, readonly=True)
    assert before == store.logical_dump()
    store.close()
    output = report(root, tmp_path / "report")
    assert output["synthetic"]
    for name in ["summary.csv", "success_vs_calls.png", "success_vs_tokens.svg", "ablation.png",
                 "cost_estimator.png", "failure_analysis.csv", "replay.html", "results.md", "reproduce.md"]:
        assert (tmp_path / "report" / name).is_file()


def test_missing_job_and_hash_change_block_seal(campaign):
    plan_path, _, _ = campaign
    execute(plan_path)
    root = plan_path.parent
    store = Store(root)
    store.db.execute("UPDATE trial_states SET status='paused' WHERE id=(SELECT id FROM trial_states LIMIT 1)")
    store.close()
    with pytest.raises(ValueError, match="incomplete"):
        seal(root)


def test_tampered_seal_rejected(campaign):
    plan_path, _, _ = campaign
    execute(plan_path)
    seal(plan_path.parent)
    with (plan_path.parent / "repair.jsonl").open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="changed"):
        verify_seal(plan_path.parent)


def test_campaign_control_keeps_denominator(campaign):
    plan_path, _, config = campaign
    # Build a fresh immutable plan with the smaller allowance.
    config.budgets.max_dispatched_calls = 2
    path = plan_path.parent.parent / "limited" / "plan.json"
    make_plan(write_config(path.parent.parent / "limited_config.json", config), path)
    result = execute(path)
    assert result["expected"] == 6
    assert result["inference_attempts"] == 2
    assert not result["complete"]
    assert result["states"]["paused"] == 6


def test_replay_escapes_code_and_never_executes(tmp_path, task, job, config):
    from conftest import initialize
    from rexbench.backends.mock import MockBackend
    from rexbench.search import run_trial
    store = initialize(tmp_path, job)
    attack = "print('</pre><script>alert(1)</script>')"
    run_trial(store, task, job, config, MockBackend([{"text": attack, "input_tokens": 1, "output_tokens": 1}]), MockJudge({}), "e")
    write_json(tmp_path / "plan.json", {"config": config.model_dump(mode="json")})
    write_jsonl(tmp_path / "repair.jsonl", [task.model_dump(mode="json")])
    before = store.logical_dump()
    store.close()
    replay(tmp_path, "representative", tmp_path / "trace.html")
    content = (tmp_path / "trace.html").read_text(encoding="utf-8")
    assert "<script>alert" not in content
    assert "&lt;script&gt;" in content
    assert "default-src 'none'" in content
    store = Store(tmp_path, readonly=True)
    assert store.logical_dump() == before


def test_hidden_failure_after_visible_success_never_reopens_search(campaign):
    plan_path, hidden_path, config = campaign
    write_json(Path(config.judge.mock_script), {"print(0)": {"c0": "PASS", "c1": "PASS", "c2": "PASS", "default": "WRONG_ANSWER"}})
    first = execute(plan_path)
    assert first["complete"] and first["inference_attempts"] == 6
    seal(plan_path.parent)
    evaluated = evaluate(plan_path.parent, hidden_path, MockJudge(json.loads(Path(config.judge.mock_script).read_bytes())))
    assert all(not r["solved"] and r["visible_success_stop"] for r in evaluated["rows"])
    assert execute(plan_path)["inference_attempts"] == 6
