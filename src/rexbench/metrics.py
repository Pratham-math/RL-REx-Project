from __future__ import annotations

import numpy as np


def validate_rows(rows: list[dict], jobs: list[dict], call_max: int, token_grid: list[int]):
    expected = {(j["task_id"], j["method"], j["seed"], axis, b) for j in jobs
                for axis, budgets in [("calls", range(1, call_max + 1)), ("tokens", token_grid)] for b in budgets}
    actual = [(r["task_id"], r["method"], r["seed"], r["axis"], r["budget"]) for r in rows]
    if len(actual) != len(set(actual)):
        raise ValueError("Duplicate evaluation rows")
    if expected != set(actual):
        raise ValueError("Missing or unexpected task/method/seed/budget rows")
    if any(r["censored"] for r in rows):
        raise ValueError("Censored checkpoint: final comparison incomplete")
    if any(r["campaign_trial_tokens"] is None for r in rows):
        raise ValueError("Unknown actual usage blocks cost report")


def aggregate(rows: list[dict], methods: list[str], samples: int = 10000, seed: int = 2026):
    tasks = sorted({r["task_id"] for r in rows})
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(tasks), size=(samples, len(tasks)))
    output = []
    for axis, budget in sorted({(r["axis"], r["budget"]) for r in rows}):
        subset = [r for r in rows if r["axis"] == axis and r["budget"] == budget]
        values, bundles = {}, {}
        for method in methods:
            task_rows = [[r for r in subset if r["task_id"] == t and r["method"] == method] for t in tasks]
            if any(not r for r in task_rows):
                raise ValueError("Incomplete paired task support")
            values[method] = np.array([np.mean([r["solved"] for r in group]) for group in task_rows])
            bundles[method] = task_rows
        for method in methods:
            value = values[method]
            boot = value[draws].mean(axis=1)
            delta = value - values.get("rex", value)
            delta_boot = delta[draws].mean(axis=1)
            task_rows = bundles[method]
            cost = np.array([sum(r["prefix_tokens"] for r in group) for group in task_rows], dtype=float)
            successes = np.array([sum(r["solved"] for r in group) for group in task_rows], dtype=float)
            numerator, denominator = cost[draws].sum(axis=1), successes[draws].sum(axis=1)
            ratio = numerator[denominator > 0] / denominator[denominator > 0]
            all_rows = [r for group in task_rows for r in group]
            visible = [r for r in all_rows if r["visible_fraction"] == 1]
            false = sum(not r["solved"] for r in visible) / len(visible) if visible else None
            output.append({"axis": axis, "budget": budget, "method": method, "n_tasks": len(tasks),
                           "n_trials": len(all_rows), "success": float(value.mean()),
                           "ci_low": float(np.quantile(boot, .025)), "ci_high": float(np.quantile(boot, .975)),
                           "delta_vs_rex": float(delta.mean()) if "rex" in values else None,
                           "delta_ci_low": float(np.quantile(delta_boot, .025)) if "rex" in values else None,
                           "delta_ci_high": float(np.quantile(delta_boot, .975)) if "rex" in values else None,
                           "prefix_actual_tokens": int(cost.sum()), "hidden_successes": int(successes.sum()),
                           "tokens_per_hidden_success": float(cost.sum() / successes.sum()) if successes.sum() else None,
                           "cost_ratio_ci_low": float(np.quantile(ratio, .025)) if len(ratio) else None,
                           "cost_ratio_ci_high": float(np.quantile(ratio, .975)) if len(ratio) else None,
                           "zero_denominator_bootstrap_draws": int(sum(denominator == 0)),
                           "false_visible_success": false,
                           "campaign_tokens_per_hidden_success": sum(r["campaign_trial_tokens"] for r in all_rows) / float(successes.sum()) if successes.sum() else None,
                           "campaign_actual_tokens": sum(r["campaign_trial_tokens"] for r in all_rows)})
    return output


def call_auc(rows: list[dict], method: str, call_max: int) -> float:
    values = [r["solved"] for r in rows if r["method"] == method and r["axis"] == "calls"]
    if not values or len(values) % call_max:
        raise ValueError("Incomplete integer call grid")
    return float(np.mean(values))


def auc_statistics(rows: list[dict], methods: list[str], call_max: int, samples: int, seed: int):
    tasks = sorted({r["task_id"] for r in rows})
    draws = np.random.default_rng(seed).integers(0, len(tasks), size=(samples, len(tasks)))
    values = {}
    for method in methods:
        task_values = []
        for task in tasks:
            group = [r for r in rows if r["task_id"] == task and r["method"] == method and r["axis"] == "calls"]
            by_seed = {s: [r for r in group if r["seed"] == s] for s in {r["seed"] for r in group}}
            if not by_seed or any({r["budget"] for r in g} != set(range(1, call_max + 1)) or len(g) != call_max for g in by_seed.values()):
                raise ValueError("Incomplete AUC trial grid")
            task_values.append(np.mean([np.mean([r["solved"] for r in g]) for g in by_seed.values()]))
        values[method] = np.array(task_values)
    output = []
    for method in methods:
        boot = values[method][draws].mean(axis=1)
        delta = values[method] - values.get("rex", values[method])
        paired = delta[draws].mean(axis=1)
        output.append({"method": method, "normalized_call_auc": float(values[method].mean()),
                       "ci_low": float(np.quantile(boot, .025)), "ci_high": float(np.quantile(boot, .975)),
                       "delta_vs_rex": float(delta.mean()) if "rex" in values else None,
                       "delta_ci_low": float(np.quantile(paired, .025)) if "rex" in values else None,
                       "delta_ci_high": float(np.quantile(paired, .975)) if "rex" in values else None,
                       "n_tasks": len(tasks), "call_grid": f"1..{call_max}"})
    return output
