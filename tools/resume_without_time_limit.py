"""Resume a frozen campaign with an explicitly authorized wall-time amendment.

The original plan, experiment identity, model, data and search implementation
remain pinned. Only this continuation controller's elapsed-time check is absent.
Per-request timeouts, program limits and dispatch limits remain in force.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import time

from rexbench.data.apps import load_repair
from rexbench.experiment import (
    CampaignPaused, _audit_gate, adapters, status, validate_plan, writer_lock,
)
from rexbench.search import run_trial
from rexbench.store import Store
from rexbench.util import fingerprint, now, read_json, sha, write_json


def resume(root: Path, max_dispatched_calls: int | None = None):
    plan = read_json(root / 'plan.json')
    if (root / 'seal.json').exists() or status(root)['complete']:
        return status(root)
    config = validate_plan(plan)
    if not plan['jobs'] or plan['status'] != 'ready_for_resolution':
        raise ValueError('Plan lacks frozen repair tasks')
    pins = read_json(root / 'resolved_config.json')
    identity = fingerprint(pins)
    with writer_lock(root):
        backend, judge = adapters(config)
        if hasattr(judge, 'cleanup_owned'):
            judge.owner = fingerprint([identity, str(root.resolve())])
            judge.cleanup_owned()
        info = backend.info()
        resolved = config.model_copy(deep=True)
        resolved.model.digest = info['digest']
        resolved.judge.image_digest = judge.image_digest
        expected = {
            'plan_hash': plan['plan_hash'], 'config': resolved.model_dump(mode='json'),
            'model_info': info, 'image_digest': judge.image_digest, 'audit': _audit_gate(resolved),
            'source_pins': plan['source_pins'], 'environment': plan['environment'],
        }
        if pins != expected:
            raise ValueError('Resolved model/image/config/environment drift; resume refused')
        if config.model.backend == 'ollama':
            backend.config = resolved.model
        for repair in (Path(plan['repair_file']), root / 'repair.jsonl'):
            if sha(repair.read_bytes()) != plan['data_hash']:
                raise ValueError('Frozen repair data drift')
        tasks = {t.task_id: t for t in load_repair(root / 'repair.jsonl')}
        if set(tasks) != {j['task_id'] for j in plan['jobs']}:
            raise ValueError('Planned matrix does not match frozen tasks')
        store = Store(root)
        saved_cap = store.db.execute(
            "SELECT value FROM metadata WHERE key='max_dispatched_calls_override'"
        ).fetchone()
        effective_cap = int(saved_cap[0]) if saved_cap else resolved.budgets.max_dispatched_calls
        if max_dispatched_calls is not None:
            if max_dispatched_calls < effective_cap:
                store.close()
                raise ValueError('Dispatch amendment must not decrease the existing allowance')
            effective_cap = max_dispatched_calls
        active = store.db.execute("SELECT value FROM metadata WHERE key='active_seconds'").fetchone()
        previous_seconds = float(active[0]) if active else 0.0
        started = time.monotonic()
        # No campaign deadline. Adapter defaults retain ordinary request/program timeouts.
        cancelled = False

        def cancel(_sig, _frame):
            nonlocal cancelled
            cancelled = True
            raise KeyboardInterrupt

        old_handler = signal.signal(signal.SIGTERM, cancel)

        def check():
            count = store.db.execute(
                "SELECT COUNT(*) FROM requests WHERE state NOT IN ('prepared','rejected')"
            ).fetchone()[0]
            if cancelled or count >= effective_cap:
                raise CampaignPaused('Campaign inference allowance reached')

        try:
            amendment = {
                'recorded': now(), 'authorization': 'User: no hard 1 hour cutoff',
                'plan_hash': plan['plan_hash'], 'original_wall_hours': config.budgets.campaign_wall_hours,
                'effective_wall_hours': None, 'max_dispatched_calls': effective_cap,
                'controller': str(Path(__file__).resolve()), 'controller_sha256': sha(Path(__file__).read_bytes()),
                'pid': os.getpid(), 'original_plan_and_search_pins_unchanged': True,
            }
            with store.transaction():
                if not store.db.execute('SELECT 1 FROM experiments WHERE id=?', (identity,)).fetchone():
                    raise ValueError('Existing experiment identity does not match pins')
                store.event(None, 'wall_time_limit_removed_by_user', amendment)
                store.db.execute("INSERT OR REPLACE INTO metadata VALUES('wall_time_limit_override','none')")
                if max_dispatched_calls is not None:
                    dispatch_amendment = {
                        'recorded': now(), 'authorization': 'User: Extend the request allowance to finish',
                        'original_gpu_allowance': resolved.budgets.max_dispatched_calls,
                        'previous_gpu_allowance': int(saved_cap[0]) if saved_cap else resolved.budgets.max_dispatched_calls,
                        'effective_gpu_allowance': effective_cap, 'plan_hash': plan['plan_hash'],
                        'per_trial_limits_unchanged': True,
                    }
                    store.event(None, 'dispatch_allowance_extended_by_user', dispatch_amendment)
                    store.db.execute("INSERT OR REPLACE INTO metadata VALUES('max_dispatched_calls_override',?)",
                                     (str(effective_cap),))
                store.db.execute('UPDATE trial_states SET lease_owner=NULL,lease_until=NULL')
            write_json(root / 'wall_time_amendment.json', amendment)
            if max_dispatched_calls is not None:
                write_json(root / 'dispatch_allowance_amendment.json', dispatch_amendment)
            for job in plan['jobs']:
                checkpoint = store.load(job['id'])
                if checkpoint and checkpoint.stop_reason:
                    continue
                store.db.execute('UPDATE trial_states SET lease_owner=?,lease_until=? WHERE id=?',
                                 (f'pid:{os.getpid()}', time.time() + 3600, job['id']))
                try:
                    run_trial(store, tasks[job['task_id']], job, resolved, backend, judge, identity, check)
                except (CampaignPaused, KeyboardInterrupt):
                    raise
                except Exception as exc:
                    with store.transaction():
                        store.event(job['id'], 'controller_error',
                                    {'type': type(exc).__name__, 'message': str(exc)[:1000]})
                        store.db.execute("UPDATE trial_states SET status='error',stop_reason=? WHERE id=?",
                                         (type(exc).__name__, job['id']))
                finally:
                    store.db.execute('UPDATE trial_states SET lease_owner=NULL,lease_until=NULL WHERE id=?',
                                     (job['id'],))
        except (CampaignPaused, KeyboardInterrupt) as exc:
            with store.transaction():
                store.db.execute("UPDATE trial_states SET status='paused',stop_reason=? "
                                 "WHERE status IN ('planned','running')", (str(exc) or 'cancelled',))
        finally:
            signal.signal(signal.SIGTERM, old_handler)
            store.db.execute("INSERT OR REPLACE INTO metadata VALUES('active_seconds',?)",
                             (str(previous_seconds + time.monotonic() - started),))
            store.close()
    return status(root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--no-wall-time-limit', action='store_true', required=True)
    parser.add_argument('--max-dispatched-calls', type=int,
                        help='Explicitly authorized total GPU dispatch allowance, persisted for later resumes')
    args = parser.parse_args()
    print(json.dumps(resume(args.experiment, args.max_dispatched_calls)))
