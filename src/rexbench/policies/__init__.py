"""Pure selectors. I/O, prompts and persistence belong to the controller."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..config import Policy
from ..types import ArmState


def new_arm(arm_id: str, h: float, C: float, **kwargs) -> ArmState:
    return ArmState(arm_id=arm_id, h=h, alpha=1 + C * h, beta=1 + C * (1 - h), **kwargs)


def observe(parent: ArmState, child: ArmState, eta: float, terminal: bool) -> float:
    # Upstream exits before posterior mutation on terminal success. Child evidence is still saved.
    reward = 1. if terminal else eta * max(0., child.h - parent.h) if parent.arm_id != "root" else 0.
    if not terminal:
        parent.alpha += reward
        parent.beta += 1 - reward
        parent.pulls += 1
    return reward


def select(method: str, arms: list[ArmState], estimates: dict[str, float], rng: np.random.Generator,
           cfg: Policy, policy_state: dict[str, Any]) -> tuple[str, dict]:
    eligible = [a for a in arms if a.arm_id in estimates]
    if not eligible:
        raise ValueError("No admissible action")
    scores: dict[str, float] = {}
    draws: dict[str, float] = {}
    if method == "resample":
        chosen = "root"
    elif method == "greedy":
        scores = {a.arm_id: cfg.greedy_root_score if a.arm_id == "root" else a.h for a in eligible}
        best = max(scores.values())
        ties = [a.arm_id for a in eligible if scores[a.arm_id] == best]
        chosen = str(rng.choice(ties))  # Controlled study: seeded random ties; upstream uses earliest.
    elif method == "bfs":
        chosen = next((a.arm_id for a in eligible if a.pulls < cfg.bfs_branching), "")
    elif method == "fixed_width":
        endpoints = policy_state.get("endpoints", [])
        if len(endpoints) < cfg.fixed_width:
            chosen = "root"
        else:
            cursor = policy_state.get("cursor", 0)
            chosen = endpoints[cursor % cfg.fixed_width]
    else:
        _, gamma = cfg.toggles(method)
        for a in eligible:  # Consume even the lone root draw; order matches NumPy upstream.
            draws[a.arm_id] = float(rng.beta(a.alpha, a.beta))
            scores[a.arm_id] = draws[a.arm_id] / max(1., estimates[a.arm_id]) ** gamma
        chosen = max(scores, key=lambda x: scores[x])
    if chosen not in estimates:
        # Structural controls cannot silently switch to a different tree/chain.
        raise ValueError("Required structural action exceeds context")
    return chosen, {"draws": draws, "priorities": scores, "estimates": estimates.copy(), "chosen": chosen,
                    "parameters": {a.arm_id: [a.alpha, a.beta, a.pulls] for a in eligible}}


def advance(method: str, parent: ArmState, child: ArmState, state: dict, cfg: Policy):
    if method == "fixed_width":
        endpoints = list(state.get("endpoints", []))
        if len(endpoints) < cfg.fixed_width:
            endpoints.append(child.arm_id)
        else:
            cursor = state.get("cursor", 0)
            endpoints[cursor % cfg.fixed_width] = child.arm_id  # Includes regressions.
            state["cursor"] = cursor + 1
        state["endpoints"] = endpoints
