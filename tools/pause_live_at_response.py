"""One-time Windows handoff: retain an in-flight CPU response before a GPU campaign.

This preserves the old campaign rather than changing its pinned environment. It
does not issue model requests. Known responses can finish judging before pause.
"""
from __future__ import annotations

import argparse
import ctypes
import signal
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from rexbench.config import Config
from rexbench.experiment import CampaignPaused, adapters, writer_lock
from rexbench.search import run_trial
from rexbench.store import Store
from rexbench.data.apps import load_repair
from rexbench.util import fingerprint, now, read_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--pid', type=int, action='append', required=True)
    args = parser.parse_args()
    root = args.experiment.resolve()
    plan = read_json(root / 'plan.json')
    resolved = read_json(root / 'resolved_config.json')
    config = Config.model_validate(resolved['config'])
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
    handles = []
    for pid in args.pid:
        handle = kernel.OpenProcess(0x1000 | 0x0001, 0, pid)
        if not handle:
            raise OSError(ctypes.get_last_error(), 'Cannot open the selected controller')
        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.c_uint32(len(buffer))
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)) or Path(buffer.value).name.lower() != 'python.exe':
            kernel.CloseHandle(handle)
            raise ValueError('Selected process is not the inspected Python controller')
        handles.append(handle)
    database = sqlite3.connect(f'file:{(root / "state.sqlite").as_posix()}?mode=ro', uri=True)
    database.row_factory = sqlite3.Row
    latest = database.execute('SELECT * FROM requests ORDER BY rowid DESC LIMIT 1').fetchone()
    target = latest['id']
    deadline = time.monotonic() + 240
    try:
        while True:
            row = database.execute('SELECT * FROM requests WHERE id=?', (target,)).fetchone()
            if row['response_blob']:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('No response persisted; CPU controller left running')
            time.sleep(.05)
        for handle in handles:  # Child first, then its venv launcher.
            kernel.TerminateProcess(handle, 130)
    finally:
        database.close()
        for handle in handles:
            kernel.CloseHandle(handle)
    time.sleep(1)
    with writer_lock(root):
        store = Store(root)
        try:
            first = store.db.execute('SELECT MIN(started) FROM requests WHERE started IS NOT NULL').fetchone()[0]
            elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(first)).total_seconds() + 30
            backend, judge = adapters(config)
            identity = fingerprint(resolved)
            if hasattr(judge, 'cleanup_owned'):
                judge.owner = fingerprint([identity, str(root)])
                judge.cleanup_owned()
            tasks = {t.task_id: t for t in load_repair(root / 'repair.jsonl')}
            def no_dispatch():
                raise CampaignPaused('hardware_switch_to_gpu')
            for job in plan['jobs']:
                pending = store.pending(job['id'])
                if pending and pending['response_blob']:
                    try:
                        run_trial(store, tasks[job['task_id']], job, config, backend, judge, identity, no_dispatch)
                    except CampaignPaused:
                        pass
            with store.transaction():
                store.db.execute("UPDATE trial_states SET status='paused',stop_reason='hardware_switch_to_gpu',lease_owner=NULL,lease_until=NULL WHERE status IN ('running','planned')")
                store.db.execute("INSERT OR REPLACE INTO metadata VALUES('active_seconds',?)", (str(elapsed),))
                store.event(None, 'hardware_switch_pause', {'response_preserved': target, 'elapsed_upper_bound_seconds': elapsed})
            counts = store.rows('SELECT state,COUNT(*) AS count FROM requests GROUP BY state')
            attempts = store.db.execute("SELECT COUNT(*) FROM requests WHERE state NOT IN ('prepared','rejected')").fetchone()[0]
            report = {'paused': now(), 'reason': 'User requested GPU acceleration', 'response_preserved': target,
                      'request_states': counts, 'cpu_attempts': attempts, 'cpu_active_seconds_upper_bound': elapsed,
                      'remaining_pilot_seconds': max(0, 3600-elapsed), 'remaining_pilot_dispatches': max(0, 120-attempts),
                      'new_inference_dispatched_by_this_tool': 0,
                      'method': 'Terminate inspected controllers after a committed raw response, then drain saved judging under a dispatch-blocking callback. Thirty-second timing margin included.'}
            write_json(Path('reports/setup/cpu_to_gpu_pause.json'), report)
            print(report)
        finally:
            store.close()


if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal.default_int_handler)
    main()
