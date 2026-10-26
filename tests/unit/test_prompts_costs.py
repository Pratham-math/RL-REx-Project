import pytest

from rexbench.budgets import CostEstimator, charge, checkpoint_snapshot
from rexbench.prompts import admissible, bounded, extract_code, prepare
from rexbench.types import ArmState, GenerationResult, Ledger


@pytest.mark.parametrize("text,code", [
    ("print(1)", "print(1)"), ("```python\nprint(1)\n```", "print(1)"),
    ("```\nprint(1)\n```", "print(1)"), ("", None),
    ("Here is the code:\nprint(1)", None),
    ("```python\nprint(1)\n```\n```python\nprint(2)\n```", None),
    ("```python\nprint(1)", None), ("print('\ud800')", None)])
def test_parser(text, code):
    assert extract_code(text)[0] == code


def result(input_tokens=40, output_tokens=20):
    return GenerationResult(request_id="r", text="", raw={}, finish_reason="stop", input_tokens=input_tokens,
                            output_tokens=output_tokens, usage_definition="fixture", started="a", finished="b", latency_seconds=1)


def test_costs_are_prior_only_and_usage_unknown():
    estimator = CostEstimator()
    assert estimator.estimate("x" * 400) == 612
    estimator.observe("x" * 400, result(100, 100))
    assert estimator.chars_per_token == 4
    assert estimator.output_tokens == pytest.approx(429.6)
    ledger = Ledger(reservations=1, inference_attempts=1)
    charge(ledger, result())
    assert ledger.tokens == 60 and ledger.reservations == 0
    charge(ledger, result(None, 5))
    assert ledger.tokens is None and ledger.output_tokens == 25


def test_completed_generation_crossing_no_free_first_call():
    snapshots = [{"step": 1, "calls": 1, "tokens": 60}, {"step": 2, "calls": 2, "tokens": 150}]
    assert checkpoint_snapshot(snapshots, "tokens", 59, "visible_success") == (None, False)
    assert checkpoint_snapshot(snapshots, "tokens", 100, None) == (snapshots[0], False)
    assert checkpoint_snapshot(snapshots, "tokens", 200, None) == (snapshots[-1], True)
    assert checkpoint_snapshot(snapshots, "tokens", 200, "visible_success") == (snapshots[-1], False)
    assert checkpoint_snapshot([], "calls", 1, None) == (None, True)


def test_admission_and_feedback_bound(task):
    assert not admissible("x" * 1000, 1200, 100)
    assert "TRUNCATED" in bounded("abcde", 2)
    root = ArmState(arm_id="root")
    assert prepare(task, root, "", 0, 0) == prepare(task, root, "", 0, 99)
