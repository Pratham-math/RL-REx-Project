import pytest

from rexbench.metrics import aggregate, auc_statistics, call_auc, validate_rows


def toy():
    jobs = [{"task_id": str(t), "method": m, "seed": s} for t in range(3) for m in ["rex", "rex_progress_cost"] for s in [0, 1]]
    rows = [{**j, "axis": "calls", "budget": b, "solved": j["method"] != "rex" and b == 2,
             "censored": False, "prefix_tokens": 100, "campaign_trial_tokens": 200,
             "visible_fraction": .5} for j in jobs for b in [1, 2]]
    return jobs, rows


def test_independent_toy_metrics():
    jobs, rows = toy()
    validate_rows(rows, jobs, 2, [])
    summary = aggregate(rows, ["rex", "rex_progress_cost"], 500, 0)
    combined = next(r for r in summary if r["method"] == "rex_progress_cost" and r["budget"] == 2)
    assert combined["success"] == 1 and combined["delta_vs_rex"] == 1
    assert combined["delta_ci_low"] == 1 and combined["delta_ci_high"] == 1
    assert combined["n_tasks"] == 3 and combined["n_trials"] == 6
    assert combined["tokens_per_hidden_success"] == 100
    failed = next(r for r in summary if r["method"] == "rex")
    assert failed["tokens_per_hidden_success"] is None
    assert failed["zero_denominator_bootstrap_draws"] == 500
    assert call_auc(rows, "rex_progress_cost", 2) == .5
    auc = auc_statistics(rows, ["rex", "rex_progress_cost"], 2, 500, 0)
    assert auc[1]["normalized_call_auc"] == .5
    assert auc[1]["delta_ci_low"] == auc[1]["delta_ci_high"] == .5


def test_missing_method_duplicate_censor_usage_gates():
    jobs, rows = toy()
    with pytest.raises(ValueError, match="Missing"):
        validate_rows([r for r in rows if r["method"] == "rex"], jobs, 2, [])
    with pytest.raises(ValueError, match="Duplicate"):
        validate_rows(rows + rows[:1], jobs, 2, [])
    rows[0]["censored"] = True
    with pytest.raises(ValueError, match="Censored"):
        validate_rows(rows, jobs, 2, [])
    rows[0]["censored"] = False
    rows[0]["campaign_trial_tokens"] = None
    with pytest.raises(ValueError, match="Unknown"):
        validate_rows(rows, jobs, 2, [])


def test_task_bootstrap_keeps_seeds_clustered():
    jobs, rows = toy()
    for row in rows:
        row["solved"] = int(row["task_id"]) == 0
    summary = aggregate(rows, ["rex", "rex_progress_cost"], 1000, 3)
    assert all(r["delta_ci_low"] == r["delta_ci_high"] == 0 for r in summary)
    assert all(r["success"] == pytest.approx(1/3) for r in summary)


def test_real_single_method_run_is_not_mislabeled_synthetic():
    from rexbench.report import describe_finding
    assert "synthetic" not in describe_finding(False, None, 2).lower()
    assert "no comparative model performance" in describe_finding(True, None, 2)
