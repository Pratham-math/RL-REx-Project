"""Stop inspected Windows Python controllers only when no request is in flight."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import time

from rexbench.experiment import writer_lock
from rexbench.store import Store
from rexbench.util import now, write_json


def handoff(root, controller_pid, launcher_pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    native = ctypes.WinDLL('ntdll')
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    native.NtSuspendProcess.argtypes = [wintypes.HANDLE]
    native.NtResumeProcess.argtypes = [wintypes.HANDLE]
    handles = []
    suspended = False
    terminated = False
    database = None
    try:
        for pid in (controller_pid, launcher_pid):
            handle = kernel.OpenProcess(0x1000 | 0x0800 | 0x0001 | 0x100000, False, pid)
            if not handle:
                raise OSError(ctypes.get_last_error(), 'Cannot open inspected controller')
            handles.append(handle)
            image = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(image))
            if not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)):
                raise OSError(ctypes.get_last_error(), 'Cannot verify controller image')
            if Path(image.value).name.lower() != 'python.exe':
                raise ValueError('Inspected controller is not Python')
        created, exited, system, user = (wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(handles[0], ctypes.byref(created), ctypes.byref(exited),
                                      ctypes.byref(system), ctypes.byref(user)):
            raise OSError(ctypes.get_last_error(), 'Cannot read controller start time')
        seconds = ((created.dwHighDateTime << 32) + created.dwLowDateTime) / 1e7 - 11644473600
        started = datetime.fromtimestamp(seconds, timezone.utc)
        database = sqlite3.connect(f"file:{(root / 'state.sqlite').resolve().as_posix()}?mode=ro", uri=True)

        def inflight():
            return database.execute("SELECT COUNT(*) FROM requests WHERE state='dispatched'").fetchone()[0]

        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            if inflight():
                time.sleep(.01)
                continue
            if native.NtSuspendProcess(handles[0]) != 0:
                raise RuntimeError('Could not suspend controller for boundary verification')
            suspended = True
            # Recheck while the controller cannot dispatch a new request.
            if inflight():
                native.NtResumeProcess(handles[0])
                suspended = False
                continue
            for handle in handles:
                if not kernel.TerminateProcess(handle, 130):
                    raise OSError(ctypes.get_last_error(), 'Cannot terminate controller at safe boundary')
            terminated = True
            for handle in handles:
                if kernel.WaitForSingleObject(handle, 5000) != 0:
                    raise RuntimeError('Controller termination did not finish')
            break
        else:
            raise TimeoutError('No safe boundary observed; controller left running')
        database.close()
        database = None
        with writer_lock(root):
            store = Store(root)
            try:
                old = store.db.execute("SELECT value FROM metadata WHERE key='active_seconds'").fetchone()
                elapsed = (datetime.now(timezone.utc) - started).total_seconds() + 2
                total = (float(old[0]) if old else 0) + elapsed
                record = {'recorded': now(), 'reason': 'User removed hard one-hour cutoff',
                          'controller_pid': controller_pid, 'launcher_pid': launcher_pid,
                          'controller_created': started.isoformat(), 'no_new_unknown_requests': True,
                          'verified_no_dispatched_requests_while_suspended': True,
                          'active_seconds_upper_bound': total}
                with store.transaction():
                    store.event(None, 'controller_saved_response_handoff', record)
                    store.db.execute("INSERT OR REPLACE INTO metadata VALUES('active_seconds',?)", (str(total),))
                write_json(root / 'controller_time_amendment_handoff.json', record)
                return record
            finally:
                store.close()
    finally:
        if database:
            database.close()
        if suspended and not terminated:
            native.NtResumeProcess(handles[0])
        for handle in handles:
            kernel.CloseHandle(handle)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--controller-pid', type=int, required=True)
    parser.add_argument('--launcher-pid', type=int, required=True)
    args = parser.parse_args()
    print(handoff(args.experiment, args.controller_pid, args.launcher_pid))
