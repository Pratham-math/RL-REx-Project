"""Execute the pinned author's scheduler in deterministic, model-free domains."""
from __future__ import annotations

import ast
import importlib.util
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np

from .config import Policy
from .policies import new_arm, observe, select
from .types import ArmState
from .util import sha, write_json


def parity(upstream: Path, out: Path):
    commit = subprocess.run(["git", "-C", str(upstream), "rev-parse", "HEAD"], check=True,
                            capture_output=True, text=True, timeout=10).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(upstream), "status", "--porcelain"], check=True,
                           capture_output=True, text=True, timeout=10).stdout.strip()
    if dirty:
        raise ValueError("Upstream working tree must match the recorded commit")
    source = upstream / "acr/scheduler/rex.py"
    spec = importlib.util.spec_from_file_location("rexbench_upstream_scheduler", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_rng = np.random.default_rng
    results = []
    for seed in [0, 1, 2026]:
        for duplicate_wrapper in [False, True]:
            values = [.4, .7, .2, .7, .0, .9, 1.]
            upstream_draws, selected = [], []

            class RecordingRNG:
                def __init__(self):
                    self.rng = original_rng(seed)

                def beta(self, alpha, beta):
                    value = float(self.rng.beta(alpha, beta))
                    upstream_draws.append([alpha, beta, value])
                    return value

            class Domain:
                def set_seed(self, value):
                    assert value == seed

                def reset(self, problem):
                    self.step_count, self.arm_count = 0, 1
                    return [(0, "empty", None)]

                def step(self, index):
                    selected.append(index)
                    value = values[self.step_count]
                    self.step_count += 1
                    # Explicit fake domain can suppress a duplicate arm, as APPS wrapper does.
                    skip = duplicate_wrapper and self.step_count == 4
                    actions = [] if skip else [(self.arm_count, f"candidate-{self.step_count}", value)]
                    if not skip:
                        self.arm_count += 1
                    return int(value == 1), value == 1, actions

                def get_metrics(self):
                    return {"step": self.step_count}

            with patch.object(module.np.random, "default_rng", lambda _seed: RecordingRNG()):
                module.rex(Domain(), 0, seed, smoothing=1, constant=20, max_steps=len(values))
            rng, arms, local_draws, local_selected = original_rng(seed), [ArmState(arm_id="root")], [], []
            for step, value in enumerate(values):
                estimates = {a.arm_id: 1. for a in arms}
                arm_id, decision = select("rex", arms, estimates, rng, Policy(), {})
                for arm in arms:
                    local_draws.append([arm.alpha, arm.beta, decision["draws"][arm.arm_id]])
                parent_index = next(i for i, a in enumerate(arms) if a.arm_id == arm_id)
                local_selected.append(parent_index)
                child = new_arm(f"child-{step}", value, 20)
                observe(arms[parent_index], child, 0, value == 1)
                if value == 1:
                    break
                if not (duplicate_wrapper and step == 3):
                    arms.append(child)
            assert selected == local_selected
            assert upstream_draws == local_draws
            results.append({"seed": seed, "duplicate_suppression": duplicate_wrapper, "matched": True,
                            "actions": selected, "draw_parameters_and_values": local_draws,
                            "terminal_parent_unchanged": True})
    # Inspect only trusted upstream code: isolate wrapper class/method without loading its old SDKs.
    app_source = upstream / "acr/domains/apps/main.py"
    tree = ast.parse(app_source.read_text(encoding="utf-8"))
    refine = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RefineAPPS")
    namespace: dict[str, Any] = {}
    exec(compile(ast.Module(body=[refine], type_ignores=[]), str(app_source), "exec"), namespace)
    klass = namespace["RefineAPPS"]
    one = klass("fake_task", {"solution": "same code", "success_rate": .4}, None)
    two = klass("fake_task", {"solution": "same code", "success_rate": .7}, None)
    assert one == two
    evidence = {"schema_version": 1, "upstream_commit": commit, "license": "MIT", "license_hash": sha((upstream / "LICENSE").read_bytes()),
                "scheduler_hash": sha(source.read_bytes()), "apps_wrapper_hash": sha(app_source.read_bytes()),
                "track": "algorithm_conformance", "fixtures": results, "passed": True,
                "duplicate_wrapper_check": "Upstream RefineAPPS equality merges exact solution for same task using hash(str(data)+source)",
                "departures": ["Controlled study acquires one arm per generation, including duplicate code",
                               "Invalid completions retain a failed-generation arm; upstream APPS may add no arm",
                               "Successful child recorded by harness; upstream scheduler exits before adding it",
                               "Controlled greedy uses seeded random ties; upstream greedy uses earliest max"],
                "claim": "Scheduler trace parity on fake domains; not full APPS/model/prompt reproduction"}
    write_json(out, evidence)
    return evidence
