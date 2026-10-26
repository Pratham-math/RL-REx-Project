import pytest

from rexbench.cli import main
from rexbench.experiment import make_plan, validate_plan
from conftest import write_config


@pytest.mark.parametrize("argv", [["--help"], ["doctor", "--help"], ["dataset", "prepare", "--help"],
                                  ["dataset", "audit", "--help"], ["parity", "--help"],
                                  ["experiment", "plan", "--help"], ["run", "--help"],
                                  ["resume", "--help"], ["status", "--help"], ["seal", "--help"],
                                  ["evaluate", "--help"], ["report", "--help"], ["trace", "--help"]])
def test_cli_help(argv):
    with pytest.raises(SystemExit) as result:
        main(argv)
    assert result.value.code == 0


def test_plan_missing_data_honest_matrix_bound(tmp_path, config):
    config.data.repair_file = str(tmp_path / "missing.jsonl")
    config.data.evaluation_count = 30
    config.experiment.methods = ["resample", "greedy", "rex", "rex_progress", "rex_cost", "rex_progress_cost"]
    config.experiment.seeds = [0, 1, 2]
    config.budgets.coverage_extension_call_ceiling = 64
    config.budgets.call_checkpoints = [1, 2, 4, 8, 16]
    config.budgets.max_dispatched_calls = 8640
    plan = make_plan(write_config(tmp_path / "config.json", config), tmp_path / "plan.json")
    assert plan["jobs"] == [] and plan["data_hash"] is None
    assert plan["status"] == "blocked_missing_repair_dataset"
    assert plan["resources"]["trials"] == 540
    assert plan["resources"]["nominal_call_upper_bound"] == 8640
    assert plan["resources"]["extension_call_upper_bound"] == 34560
    assert plan["resources"]["allowance_covers_nominal"]
    assert not plan["resources"]["allowance_covers_extensions"]
    validate_plan(plan)
    plan["config"]["policy"]["eta"] = .3
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_plan(plan)


def test_rejected_endpoint_credentials_are_not_echoed(tmp_path, capsys):
    path = tmp_path / "config.yaml"
    path.write_text("model:\n  endpoint: http://secret-user:secret-password@localhost:11434\n")
    assert main(["doctor", "--config", str(path)]) == 2
    output = capsys.readouterr().err
    assert "secret-user" not in output and "secret-password" not in output
    assert "credentials" in output


def test_duplicate_yaml_keys_rejected(tmp_path):
    from rexbench.config import load_config
    path = tmp_path / "duplicate.yaml"
    path.write_text("policy:\n  eta: 0.5\n  eta: 1.0\n")
    with pytest.raises(ValueError, match="Duplicate configuration"):
        load_config(path)
