"""Build a sealed analysis view from fixed, traceable trial sources; no inference.

The view retains original request experiment IDs and all response bytes. It is
explicitly a composition, not a new search campaign or recovery of lost usage.
"""
from contextlib import ExitStack
import json
from pathlib import Path

from rexbench.evaluate import coverage, seal, verify_seal
from rexbench.experiment import validate_plan, writer_lock
from rexbench.store import Store
from rexbench.types import GenerationRequest
from rexbench.util import atomic_bytes, fingerprint, jsonl, now, read_json, sha, write_json


def comparable(original, replacement):
    for key in ('model', 'policy', 'judge', 'execution', 'report'):
        if original['config'][key] != replacement['config'][key]:
            raise ValueError(f'Algorithm/runtime setting mismatch: {key}')
    for key in ('track', 'methods', 'seeds', 'primary_metric', 'primary_comparison'):
        if original['config']['experiment'][key] != replacement['config']['experiment'][key]:
            raise ValueError(f'Experiment setting mismatch: {key}')
    allowed = {'max_dispatched_calls', 'campaign_wall_hours'}
    for key, value in original['config']['budgets'].items():
        if key not in allowed and replacement['config']['budgets'][key] != value:
            raise ValueError(f'Budget checkpoint mismatch: {key}')
    for key in ('source_pins', 'environment', 'prompt_hash', 'parser_version'):
        if original[key] != replacement[key]:
            raise ValueError(f'Pinned implementation mismatch: {key}')


def compose(original_root: Path, replacement_root: Path, out: Path, task: str):
    if out.exists():
        raise FileExistsError('Analysis view already exists; never overwrite sealed evidence')
    original = read_json(original_root / 'plan.json')
    replacement = read_json(replacement_root / 'plan.json')
    validate_plan(original)
    validate_plan(replacement)
    comparable(original, replacement)
    original_pins = read_json(original_root / 'resolved_config.json')
    verify_seal(replacement_root)
    expected = [j for j in original['jobs'] if j['task_id'] == task]
    if replacement['jobs'] != expected:
        raise ValueError('Replacement must contain every method/seed for exactly the affected task')
    originals = {r['task_id']: r for r in jsonl(original_root / 'repair.jsonl')}
    replacements = {r['task_id']: r for r in jsonl(replacement_root / 'repair.jsonl')}
    if replacements != {task: originals[task]}:
        raise ValueError('Replacement repair task is not byte-equivalent after canonical decoding')
    # Bind identical hidden/reference suites before evaluation, without inspecting model outcomes.
    manifests = [read_json(Path(p['config']['data']['manifest'])) for p in (original, replacement)]
    data_roots = [Path(p['config']['data']['manifest']).parent for p in (original, replacement)]
    hidden = [{r['task_id']: r for r in jsonl(d / 'dev_hidden.jsonl')} for d in data_roots]
    if hidden[1] != {task: hidden[0][task]}:
        raise ValueError('Replacement hidden suite differs')
    for manifest, data_root, plan in zip(manifests, data_roots, (original, replacement)):
        if sha((data_root / 'dev_hidden.jsonl').read_bytes()) != manifest['files']['dev_hidden.jsonl']:
            raise ValueError('Hidden data hash mismatch')
        audit = read_json((original_root if plan is original else replacement_root) / 'resolved_config.json')['audit']
        if plan['config']['experiment']['track'] != 'synthetic' or audit:
            if not audit or sha(Path(plan['config']['data']['manifest']).read_bytes()) != audit['manifest_hash']:
                raise ValueError('Audited manifest drift')
    with ExitStack() as stack:
        for source_root in (original_root, replacement_root):
            stack.enter_context(writer_lock(source_root))
        sources = {str(r): Store(r, readonly=True) for r in (original_root, replacement_root)}
        for store in sources.values():
            stack.callback(store.close)
        before = {name: fingerprint(store.logical_dump()) for name, store in sources.items()}
        out.mkdir(parents=True)
        # These are the original measurement contract, not a fictitious new search plan.
        for name in ('plan.json', 'resolved_config.json', 'repair.jsonl'):
            atomic_bytes(out / name, (original_root / name).read_bytes())
        destination = Store(out)
        stack.callback(destination.close)
        provenance = {
            'schema_version': 1, 'created': now(), 'kind': 'sealed_analysis_composition_not_search_campaign',
            'selection_rule': 'All methods/seeds for affected task use replacement; all other tasks use original',
            'affected_task': task, 'hidden_outcomes_used_for_selection': False,
            'source_logical_hashes': before, 'trials': [],
            'cost_rule': 'Selected trial ledgers are comparison costs; full source costs include discarded work and one unknown request',
            'events': 'Original event payloads/timestamps preserved; event numbers and checkpoint committed_event links remapped',
        }
        with destination.transaction():
            for source in sources.values():
                for row in source.rows('SELECT * FROM experiments'):
                    destination.db.execute('INSERT OR IGNORE INTO experiments VALUES(?,?)', (row['id'], row['manifest']))
            for job in original['jobs']:
                source_root = replacement_root if job['task_id'] == task else original_root
                source = sources[str(source_root)]
                pins = read_json(source_root / 'resolved_config.json')
                source_trial = source.db.execute('SELECT * FROM trial_states WHERE id=?', (job['id'],)).fetchone()
                state = source.load(job['id'])
                if not source_trial or source_trial['status'] != 'completed' or state is None:
                    raise ValueError(f'Selected trial incomplete: {job}')
                requests = source.rows('SELECT * FROM requests WHERE trial_id=? ORDER BY iteration', (job['id'],))
                if len(requests) != state.iteration or len(requests) != state.ledger.inference_attempts:
                    raise ValueError('Trial request/checkpoint ledger mismatch')
                if state.ledger.unknown_usage or state.ledger.reservations:
                    raise ValueError('Selected trial contains unknown or reserved usage')
                destination.db.execute('INSERT INTO planned_trials VALUES(?,?,?,?)',
                                       (job['id'], job['task_id'], job['method'], job['seed']))
                destination.db.execute("INSERT INTO trial_states(id,status) VALUES(?,'planned')", (job['id'],))
                for request in requests:
                    if request['state'] != 'committed' or not request['response_blob'] or not request['evaluation_blob']:
                        raise ValueError('Selected request is not fully committed')
                    envelope = GenerationRequest.model_validate(source.object(request['request_blob']))
                    if envelope.experiment_id != fingerprint(pins) or envelope.trial_id != job['id']:
                        raise ValueError('Original request identity is invalid')
                    if envelope.model_digest != original_pins['config']['model']['digest']:
                        raise ValueError('Request model digest differs')
                for table, query in (
                    ('requests', 'SELECT * FROM requests WHERE trial_id=?'),
                    ('generations', 'SELECT g.* FROM generations g JOIN requests r ON g.request_id=r.id WHERE r.trial_id=?'),
                    ('edges', 'SELECT g.* FROM edges g JOIN requests r ON g.request_id=r.id WHERE r.trial_id=?'),
                    ('test_outcomes', 'SELECT g.* FROM test_outcomes g JOIN requests r ON g.request_id=r.id WHERE r.trial_id=?'),
                    ('arms', 'SELECT * FROM arms WHERE trial_id=?'),
                    ('snapshots', 'SELECT * FROM snapshots WHERE trial_id=?'),
                ):
                    for row in source.rows(query, (job['id'],)):
                        destination.db.execute(f'INSERT INTO {table} VALUES({",".join("?" for _ in row)})', tuple(row.values()))
                event_numbers = {}
                for event in source.rows('SELECT * FROM events WHERE trial_id=? ORDER BY number', (job['id'],)):
                    cursor = destination.db.execute('INSERT INTO events(trial_id,kind,payload,created) VALUES(?,?,?,?)',
                                                   (job['id'], event['kind'], event['payload'], event['created']))
                    event_numbers[event['number']] = cursor.lastrowid
                state.committed_event = event_numbers[state.committed_event]
                # Only the database-local event pointer changes; algorithm state and ledgers are preserved.
                checkpoint = destination.put(state.model_dump(mode='json'))
                destination.db.execute("UPDATE trial_states SET status='completed',stop_reason=?,checkpoint=? WHERE id=?",
                                       (state.stop_reason, checkpoint, job['id']))
                provenance['trials'].append({'trial_id': job['id'], 'task_id': job['task_id'], 'method': job['method'],
                                             'source': str(source_root), 'source_experiment_id': fingerprint(pins),
                                             'source_checkpoint': source_trial['checkpoint'], 'view_checkpoint': checkpoint,
                                             'source_plan_hash': pins['plan_hash'], 'requests': len(requests)})
            for source in sources.values():
                for path in source.artifacts.glob('*/*'):
                    if not path.is_file():
                        continue
                    data = path.read_bytes()
                    if sha(data) != path.parent.name + path.name:
                        raise ValueError('Source artifact hash mismatch')
                    destination.put(data)
            active_seconds = sum(float(source.db.execute(
                "SELECT value FROM metadata WHERE key='active_seconds'"
            ).fetchone()[0]) for source in sources.values())
            destination.db.execute("INSERT INTO metadata VALUES('active_seconds',?)", (str(active_seconds),))
            destination.db.execute("INSERT INTO metadata VALUES('analysis_only','true')")
            destination.db.execute("INSERT INTO metadata VALUES('active_seconds_definition','Sum of both source campaign accounting values; includes discarded work and conservative downtime')")
            blob = destination.put(provenance)
            destination.event(None, 'analysis_composition_provenance', {'blob': blob})
        write_json(out / 'composition.json', provenance)
        atomic_bytes(out / 'ANALYSIS_ONLY.md', b'This is a sealed analysis view of two preserved source campaigns. Never run model inference here. See composition.json.\n')
        for name, source in sources.items():
            if fingerprint(source.logical_dump()) != before[name]:
                raise ValueError('Source campaign changed during composition')
        checked = coverage(out, destination)
        if not checked['complete']:
            raise ValueError(f'Composed matrix incomplete: {json.dumps(checked)}')
        sealed = seal(out)
        return {'analysis_view': str(out), 'seal_hash': sealed['seal_hash'], 'trials': len(provenance['trials'])}


if __name__ == '__main__':
    print(json.dumps(compose(Path('runs/development_pilot_gpu'), Path('runs/viva_rerun_0146'),
                             Path('runs/viva_complete_pilot'), 'test/0146')))
