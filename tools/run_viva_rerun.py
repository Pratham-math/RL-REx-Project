"""Frozen, all-method replacement for the task with an interrupted request."""
import importlib.util
import json
from pathlib import Path

from rexbench.config import Config
from rexbench.data.audit import audit_dataset
from rexbench.experiment import CampaignPaused, make_plan
import rexbench.experiment as experiment
from rexbench.judge.docker import DockerJudge
from rexbench.util import jsonl, now, read_json, sha, write_json, write_jsonl


def prepare():
    source = Path('data/development_pilot')
    destination = Path('data/viva_rerun_0146')
    root = Path('runs/viva_rerun_0146')
    if (root / 'plan.json').exists():
        return root
    if destination.exists():
        raise FileExistsError('Rerun preparation already exists; inspect before continuing')
    destination.mkdir(parents=True)
    task = 'test/0146'
    original = read_json(source / 'manifest.json')
    for split in ('dev', 'final'):
        for suite in ('repair', 'hidden'):
            name = f'{split}_{suite}.jsonl'
            write_jsonl(destination / name, [r for r in jsonl(source / name) if r['task_id'] == task])
    refs = [r for r in jsonl(source / original['audit_references']) if r['task_id'] == task]
    write_jsonl(destination / original['audit_references'], refs)
    manifest = dict(original)
    manifest.update({'accessed': now(), 'task_ids': {'dev': [task], 'final': []},
                     'details': {task: original['details'][task]},
                     'files': {name: sha((destination / name).read_bytes()) for name in original['files']},
                     'references_hash': sha((destination / original['audit_references']).read_bytes()),
                     'derived_from': {'manifest': str(source / 'manifest.json'),
                                      'sha256': sha((source / 'manifest.json').read_bytes())},
                     'selection': 'All methods rerun for the interrupted task, fixed before new inference/hidden evaluation'})
    write_json(destination / 'manifest.json', manifest)
    base = read_json(Path('runs/development_pilot_gpu/plan.json'))
    config = Config.model_validate(base['config'])
    config.experiment.name = 'viva_all_method_rerun_test_0146'
    config.data.dev_count = 1
    config.data.repair_file = str(destination / 'dev_repair.jsonl')
    config.data.manifest = str(destination / 'manifest.json')
    config.data.audit_only_references = str(destination / original['audit_references'])
    config.budgets.max_dispatched_calls = 3 * config.budgets.coverage_extension_call_ceiling
    config_path = Path('configs/viva_rerun_0146.json')
    write_json(config_path, config.model_dump(mode='json'))
    protocol = {
        'recorded': now(), 'scope': 'Five-task development pilot; viva evidence, not final study',
        'reason': 'One original test/0146 request lost its response during interruption',
        'replacement_task': task, 'replacement_methods': config.experiment.methods,
        'seed': 0, 'replacement_campaign': str(root), 'original_campaign': 'runs/development_pilot_gpu',
        'selection_rule': 'Use all three fresh test/0146 trials regardless of scores. Use all original trials for the other four tasks.',
        'no_cherry_picking': 'Never choose between original and rerun results using repair or hidden scores',
        'unchanged': ['task bytes', 'repair and hidden suites', 'model digest', 'runtime', 'prompts',
                      'search policy parameters', 'call/token checkpoints', 'judge image and limits'],
        'wall_time_cutoff': None, 'rerun_dispatch_ceiling': config.budgets.max_dispatched_calls,
        'cost_rule': 'Selected comparison costs reported separately from original, discarded and unknown usage; preserve all source runs',
        'limitations': ['Five development tasks', 'One seed', 'Sparse repair feedback',
                        'No progress-only or cost-only ablations in this pilot', 'No model training'],
    }
    write_json(Path('docs/viva_selection_protocol.json'), protocol)
    result = audit_dataset(destination / 'manifest.json', DockerJudge(config.judge), destination / 'audit.json')
    if not result['passed']:
        raise RuntimeError('Subset reference audit failed')
    make_plan(config_path, root / 'plan.json')
    return root


if __name__ == '__main__':
    root = prepare()
    if not (root / 'resolved_config.json').exists():
        # Resolve and validate the new frozen experiment without dispatching inference.
        original = experiment.run_trial
        def initialize_only(*_args, **_kwargs):
            raise CampaignPaused('initialized_for_explicit_no_wall_time_controller')
        try:
            experiment.run_trial = initialize_only
            experiment.execute(root / 'plan.json')
        finally:
            experiment.run_trial = original
    spec = importlib.util.spec_from_file_location('no_time_limit', Path(__file__).with_name('resume_without_time_limit.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.resume(root)
    if not result['complete']:
        raise RuntimeError(f'Rerun incomplete: {json.dumps(result)}')
    from rexbench.evaluate import seal
    with experiment.writer_lock(root):
        seal(root)
    print(json.dumps(result))
