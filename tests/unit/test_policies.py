import numpy as np
import pytest
from hypothesis import given, strategies as st

from rexbench.config import METHODS, Policy
from rexbench.policies import advance, new_arm, observe, select
from rexbench.types import ArmState


def test_manual_oracle():
    root = ArmState(arm_id="root")
    assert (root.alpha, root.beta) == (1, 1)
    parent, child = new_arm("p", .4, 20), new_arm("q", .7, 20)
    assert (parent.alpha, parent.beta) == (9, 13)
    assert observe(parent, child, .5, False) == pytest.approx(.15)
    assert (parent.alpha, parent.beta) == pytest.approx((9.15, 13.85))
    parent = new_arm("p", .4, 20)
    observe(parent, child, 0, False)
    assert (parent.alpha, parent.beta) == (9, 14)


def test_root_regression_and_terminal():
    root, child = ArmState(arm_id="root"), new_arm("q", .7, 20)
    assert observe(root, child, 1, False) == 0
    assert root.beta == 2
    parent = new_arm("p", .9, 20)
    assert observe(parent, child, .5, False) == 0
    before = parent.model_dump()
    assert observe(parent, new_arm("win", 1, 20), .5, True) == 1
    assert parent.model_dump() == before


def test_lone_root_consumes_numpy_draw():
    a, b = np.random.default_rng(42), np.random.default_rng(42)
    select("rex", [ArmState(arm_id="root")], {"root": 1}, a, Policy(), {})
    b.beta(1, 1)
    assert a.bit_generator.state == b.bit_generator.state


def test_zero_extensions_exact_equivalence():
    left, right = np.random.default_rng(2026), np.random.default_rng(2026)
    arms = [ArmState(arm_id="root"), new_arm("a", .4, 20), new_arm("b", .7, 20)]
    cfg = Policy(eta=0, gamma=0)
    for _ in range(30):
        assert select("rex", arms, {a.arm_id: 100 + i for i, a in enumerate(arms)}, left, cfg, {}) == select(
            "rex_progress_cost", arms, {a.arm_id: 100 + i for i, a in enumerate(arms)}, right, cfg, {})
    assert left.bit_generator.state == right.bit_generator.state


def test_greedy_includes_root_and_seeded_ties():
    arms = [ArmState(arm_id="root"), new_arm("a", .4, 20)]
    assert select("greedy", arms, {"root": 1, "a": 1}, np.random.default_rng(0), Policy(), {})[0] == "root"
    arms[1].h = .5
    outcomes = [select("greedy", arms, {"root": 1, "a": 1}, np.random.default_rng(s), Policy(), {})[0] for s in range(10)]
    assert set(outcomes) == {"root", "a"}


def test_structural_orders_and_regression():
    cfg, arms, rng, state = Policy(fixed_width=2), [ArmState(arm_id="root")], np.random.default_rng(0), {}
    expected_bfs = ["root", "root", "a0", "a0", "a1", "a1"]
    for i, expected in enumerate(expected_bfs):
        selected, _ = select("bfs", arms, {a.arm_id: 1 for a in arms}, rng, cfg, state)
        assert selected == expected
        parent = next(a for a in arms if a.arm_id == selected)
        child = new_arm(f"a{i}", 0, 20)
        observe(parent, child, 0, False)
        arms.append(child)
    arms, state = [ArmState(arm_id="root")], {}
    for i, expected in enumerate(["root", "root", "a0", "a1", "a2", "a3"]):
        selected, _ = select("fixed_width", arms, {a.arm_id: 1 for a in arms}, rng, cfg, state)
        assert selected == expected
        parent = next(a for a in arms if a.arm_id == selected)
        child = new_arm(f"a{i}", max(0., .8 - i * .1), 20)
        advance("fixed_width", parent, child, state, cfg)
        arms.append(child)


def test_resample_and_toggles():
    arms = [ArmState(arm_id="root"), new_arm("a", .9, 20)]
    for _ in range(20):
        assert select("resample", arms, {"root": 2, "a": 1}, np.random.default_rng(1), Policy(), {})[0] == "root"
    for method in METHODS:
        eta, gamma = Policy().toggles(method)
        assert bool(eta) == (method in ("rex_progress", "rex_progress_cost"))
        assert bool(gamma) == (method in ("rex_cost", "rex_progress_cost"))


@given(st.floats(min_value=0, max_value=1), st.floats(min_value=0, max_value=1), st.floats(min_value=0, max_value=1))
def test_positive_beta_and_bounded_rewards(parent_h, child_h, eta):
    parent, child = new_arm("p", parent_h, 20), new_arm("q", child_h, 20)
    reward = observe(parent, child, eta, False)
    assert 0 <= reward <= 1
    assert parent.alpha > 0 and parent.beta > 0
