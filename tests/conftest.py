import json
from pathlib import Path

import pytest

from rexbench.backends.mock import MockBackend
from rexbench.config import Config
from rexbench.judge.mock import MockJudge
from rexbench.store import Store
from rexbench.types import Case, RepairTask, suite_hash
from rexbench.util import sha


@pytest.fixture
def task():
    cases = [Case(id=f"c{i}", input=f"{i}\n", output=f"{i}\n") for i in range(3)]
    return RepairTask(task_id="tiny", source="fixture", revision="1", difficulty="synthetic",
                      statement="Echo an integer.", repair_tests=cases, comparator="tokens_v1",
                      statement_hash=sha("Echo an integer."), test_hash=suite_hash(cases))


@pytest.fixture
def config():
    return Config.model_validate({"experiment": {"track": "synthetic", "methods": ["rex"], "seeds": [0]},
                                  "data": {"require_audit": False, "evaluation_count": 1, "dev_count": 1}, "model": {"backend": "mock"},
                                  "judge": {"backend": "mock"},
                                  "budgets": {"call_checkpoints": [1, 2, 4], "token_checkpoints": [],
                                              "coverage_extension_call_ceiling": 4, "max_dispatched_calls": 20}})


@pytest.fixture
def job():
    return {"id": "trial", "task_id": "tiny", "method": "rex", "seed": 0}


def initialize(root: Path, job: dict):
    store = Store(root)
    with store.transaction():
        store.db.execute("INSERT INTO planned_trials VALUES(?,?,?,?)", (job["id"], job["task_id"], job["method"], job["seed"]))
        store.db.execute("INSERT INTO trial_states(id,status) VALUES(?,'planned')", (job["id"],))
    return store


def fixture_backend():
    return MockBackend([{"text": f"print({i})", "input_tokens": 40, "output_tokens": 20} for i in range(4)])


def fixture_judge():
    return MockJudge({"print(0)": ["PASS", "WRONG_ANSWER", "WRONG_ANSWER"],
                      "print(1)": ["PASS", "PASS", "WRONG_ANSWER"]})


def write_config(path: Path, config: Config):
    path.write_text(json.dumps(config.model_dump(mode="json")), encoding="utf-8")
    return path
