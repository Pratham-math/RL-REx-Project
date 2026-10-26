"""Finish benchmark analysis only; viva material is deferred at the user's request."""
import json
from pathlib import Path
import time

from rexbench.report import report
from rexbench.util import now, write_json


if __name__ == '__main__':
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    status_path=Path('reports/viva_finish_status.json')
    root=Path('runs/viva_complete_pilot')
    started=now()
    try:
        while True:
            results=list((root/'evaluations').glob('*/evaluation.json'))
            if len(results)==1:
                break
            errors=Path('reports/viva_hidden_evaluation.stderr.txt')
            if errors.exists() and errors.stat().st_size:
                raise RuntimeError(errors.read_text(encoding='utf-8'))
            count=len(list((root/'evaluations').glob('*/*.json')))
            write_json(status_path,{'stage':'waiting_for_hidden_evaluation','started':started,'updated':now(),
                                    'completed_checkpoints':count,'expected_checkpoints':150})
            time.sleep(10)
        write_json(status_path,{'stage':'generating_report','started':started,'updated':now()})
        result=report(root,Path('reports/development_pilot_final'))
        write_json(status_path,{'stage':'benchmark_report_generated','viva_material':'deferred_by_user',
                                'started':started,'updated':now(),**result})
        print(json.dumps(result))
    except Exception as exc:
        write_json(status_path,{'stage':'error','started':started,'updated':now(),'error':str(exc)})
        raise
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
