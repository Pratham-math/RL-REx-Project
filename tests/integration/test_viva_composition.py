import importlib.util
from pathlib import Path

import pytest

from conftest import write_config
from rexbench.evaluate import verify_seal, seal
from rexbench.experiment import execute, make_plan
from rexbench.store import Store
from rexbench.util import fingerprint, read_json, sha, write_json, write_jsonl


spec = importlib.util.spec_from_file_location('viva_composition', Path(__file__).parents[2] / 'tools/compose_viva_pilot.py')
composition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(composition)


@pytest.fixture
def source_runs(tmp_path, task, config):
    write_json(tmp_path / 'model.json', [{'text': 'print(0)', 'input_tokens': 40, 'output_tokens': 20}])
    write_json(tmp_path / 'judge.json', {'print(0)': ['PASS', 'WRONG_ANSWER', 'WRONG_ANSWER']})
    config.model.mock_script = str(tmp_path / 'model.json')
    config.judge.mock_script = str(tmp_path / 'judge.json')
    config.experiment.methods = ['resample', 'rex', 'rex_progress_cost']
    config.budgets.max_dispatched_calls = 100
    other = task.model_copy(update={'task_id': 'other'})
    roots = []
    for name, tasks in [('original', [other, task]), ('replacement', [task])]:
        data = tmp_path / f'data_{name}'
        data.mkdir()
        write_jsonl(data / 'dev_repair.jsonl', [t.model_dump(mode='json') for t in tasks])
        write_jsonl(data / 'dev_hidden.jsonl', [{'task_id': t.task_id, 'hidden_marker': 'unchanged'} for t in tasks])
        write_json(data / 'manifest.json', {'files': {'dev_hidden.jsonl': sha((data / 'dev_hidden.jsonl').read_bytes())}})
        cfg = config.model_copy(deep=True)
        cfg.data.dev_count = len(tasks)
        cfg.data.repair_file = str(data / 'dev_repair.jsonl')
        cfg.data.manifest = str(data / 'manifest.json')
        root = tmp_path / name
        make_plan(write_config(tmp_path / f'{name}.json', cfg), root / 'plan.json')
        assert execute(root / 'plan.json')['complete']
        roots.append(root)
    seal(roots[1])
    return roots


def test_fixed_all_method_replacement_preserves_sources_and_request_identity(tmp_path, source_runs):
    before = {}
    for root in source_runs:
        store = Store(root, readonly=True)
        before[str(root)] = fingerprint(store.logical_dump())
        store.close()
    out = tmp_path / 'composed'
    result = composition.compose(*source_runs, out, 'tiny')
    assert result['trials'] == 6
    assert verify_seal(out)['coverage']['complete']
    provenance = read_json(out / 'composition.json')
    assert provenance['source_logical_hashes'] == before
    for row in provenance['trials']:
        assert row['source'] == str(source_runs[1] if row['task_id'] == 'tiny' else source_runs[0])
    composed = Store(out, readonly=True)
    for root in source_runs:
        source = Store(root, readonly=True)
        assert fingerprint(source.logical_dump()) == before[str(root)]
        for row in provenance['trials']:
            if row['source'] != str(root):
                continue
            original = source.load(row['trial_id']).model_dump()
            imported = composed.load(row['trial_id']).model_dump()
            original.pop('committed_event')
            imported.pop('committed_event')
            assert original == imported
        source.close()
    composed.close()


def test_algorithm_setting_mismatch_rejected_before_copy(tmp_path, source_runs):
    original = read_json(source_runs[0] / 'plan.json')
    replacement = read_json(source_runs[1] / 'plan.json')
    replacement['config']['policy']['eta'] = 0.9
    with pytest.raises(ValueError, match='policy'):
        composition.comparable(original, replacement)


def test_changed_hidden_suite_rejected(tmp_path, source_runs):
    replacement = read_json(source_runs[1] / 'plan.json')
    data = Path(replacement['config']['data']['manifest']).parent
    write_jsonl(data / 'dev_hidden.jsonl', [{'task_id': 'tiny', 'hidden_marker': 'changed'}])
    with pytest.raises(ValueError, match='hidden suite differs'):
        composition.compose(*source_runs, tmp_path / 'bad', 'tiny')
    assert not (tmp_path / 'bad').exists()
