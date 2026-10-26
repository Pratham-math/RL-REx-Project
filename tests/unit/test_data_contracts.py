import pytest
from pydantic import ValidationError

from rexbench.config import Config, Data, Model
from rexbench.data.split import partition
from rexbench.judge.compare import compare
from rexbench.types import ArmState, RepairTask


def test_input_bytes_and_conflicts():
    cfg = Data(min_repair_tests=1, min_hidden_tests=1, max_repair_tests=1, max_hidden_tests=10)
    repair, hidden, info = partition("t", "No examples", [("1  2\n", "3"), ("1\n2\n", "3"), ("1  2\n", "3\n")], "tokens_v1", cfg)
    assert len(repair + hidden) == 2
    assert {c.input for c in repair + hidden} == {"1  2\n", "1\n2\n"}
    assert info["deduplicated"] == 1
    with pytest.raises(ValueError, match="conflicting"):
        partition("t", "No examples", [("x", "1"), ("x", "2")], "tokens_v1", cfg)


def test_force_examples_and_reproducibility():
    pairs = [(str(i) + "\n", str(i)) for i in range(10, 25)]
    cfg = Data(max_repair_tests=5)
    a = partition("t", "Example input: 12", pairs, "tokens_v1", cfg)
    b = partition("t", "Example input: 12", pairs, "tokens_v1", cfg)
    assert a == b
    assert "12\n" in [c.input for c in a[0]]
    assert not {c.id for c in a[0]} & {c.id for c in a[1]}
    assert len(a[2]["forced_example_ids"]) == 1


@pytest.mark.parametrize("actual,expected,mode,ok", [
    ("1  2\n", "1\n2", "tokens_v1", True),
    ("1.0", "1", "tokens_v1", False),
    ("x\n", "x", "text_v1", False),
    ("x\n", "x", "lines_v1", True),
    ("x \n", "x\n", "lines_v1", False),
    ("x\n\n", "x\n", "lines_v1", False)])
def test_independent_comparators(actual, expected, mode, ok):
    assert compare(actual, expected, mode) == ok


def test_search_record_rejects_hidden_reference_unknown_and_hash(task):
    data = task.model_dump()
    for name in ("hidden_tests", "reference_code", "unexpected"):
        with pytest.raises(ValidationError):
            RepairTask.model_validate({**data, name: []})
    with pytest.raises(ValidationError):
        RepairTask.model_validate({**data, "statement": "tampered"})
    with pytest.raises(ValidationError):
        RepairTask.model_validate({**data, "repair_tests": []})
    with pytest.raises(ValidationError):
        RepairTask.model_validate({**data, "repair_tests": data["repair_tests"] * 2})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_invalid_numeric(value):
    with pytest.raises(ValidationError):
        ArmState(arm_id="a", alpha=value)


def test_no_hosted_spending_or_invalid_config():
    with pytest.raises(ValidationError):
        Model(endpoint="https://api.example.com")
    with pytest.raises(ValidationError):
        Model(endpoint="http://secret:password@localhost:11434")
    with pytest.raises(ValidationError):
        Config.model_validate({"budgets": {"token_mode": "strict"}})
    with pytest.raises(ValidationError):
        Config.model_validate({"model": {"backend": "mock"}})
