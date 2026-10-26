import importlib.util
from pathlib import Path

import pytest

from conftest import write_config
from rexbench.experiment import execute, make_plan
from rexbench.store import Store
from rexbench.util import write_json, write_jsonl


spec = importlib.util.spec_from_file_location(
    'wall_time_continuation', Path(__file__).parents[2] / 'tools/resume_without_time_limit.py'
)
continuation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(continuation)


def prepare(tmp_path, task, config):
    write_json(tmp_path / 'model.json', [{'text': 'print(0)', 'input_tokens': 40, 'output_tokens': 20}])
    write_json(tmp_path / 'judge.json', {'print(0)': ['PASS', 'WRONG_ANSWER', 'WRONG_ANSWER']})
    write_jsonl(tmp_path / 'repair.jsonl', [task.model_dump(mode='json')])
    config.model.mock_script = str(tmp_path / 'model.json')
    config.judge.mock_script = str(tmp_path / 'judge.json')
    config.data.repair_file = str(tmp_path / 'repair.jsonl')
    path = tmp_path / 'run' / 'plan.json'
    make_plan(write_config(tmp_path / 'config.json', config), path)
    return path


@pytest.mark.parametrize('dispatch_cap', [2, 20])
def test_continues_expired_clock_with_unchanged_pins_and_dispatch_limit(tmp_path, task, config, dispatch_cap):
    config.budgets.campaign_wall_hours = 1e-12
    config.budgets.max_dispatched_calls = dispatch_cap
    path = prepare(tmp_path, task, config)
    paused = execute(path)
    assert paused['inference_attempts'] == 0
    assert paused['states'] == {'paused': 1}
    original = {p.name: p.read_bytes() for p in (path, path.parent / 'resolved_config.json')}
    result = continuation.resume(path.parent)
    assert result['inference_attempts'] == min(4, dispatch_cap)
    assert result['complete'] == (dispatch_cap >= 4)
    assert {p.name: p.read_bytes() for p in (path, path.parent / 'resolved_config.json')} == original
    store = Store(path.parent, readonly=True)
    assert len(store.rows("SELECT * FROM events WHERE kind='wall_time_limit_removed_by_user'")) == 1
    store.close()


def test_unknown_request_is_preserved_without_retry(tmp_path, task, config, monkeypatch):
    import rexbench.experiment as experiment

    class Crash(BaseException):
        pass

    original_run_trial = experiment.run_trial

    def crash_after_dispatch(*args, **kwargs):
        def fault(boundary):
            if boundary == 'after_dispatch':
                raise Crash
        return original_run_trial(*args, **kwargs, fault=fault)

    path = prepare(tmp_path, task, config)
    monkeypatch.setattr(experiment, 'run_trial', crash_after_dispatch)
    with pytest.raises(Crash):
        execute(path)
    result = continuation.resume(path.parent)
    assert result['inference_attempts'] == 1
    assert result['unknown_usage_requests'] == 1
    assert result['trials'][0]['stop_reason'] == 'REQUEST_OUTCOME_UNKNOWN'
    assert not result['complete']


def test_authorized_dispatch_extension_finishes_existing_trial_without_changing_plan(tmp_path, task, config):
    config.budgets.max_dispatched_calls = 2
    path = prepare(tmp_path, task, config)
    assert execute(path)['inference_attempts'] == 2
    original_plan = path.read_bytes()
    result = continuation.resume(path.parent, max_dispatched_calls=4)
    assert result['complete']
    assert result['inference_attempts'] == 4
    assert path.read_bytes() == original_plan
    store = Store(path.parent, readonly=True)
    assert store.db.execute(
        "SELECT value FROM metadata WHERE key='max_dispatched_calls_override'"
    ).fetchone()[0] == '4'
    assert len(store.rows("SELECT * FROM events WHERE kind='dispatch_allowance_extended_by_user'")) == 1
    store.close()
