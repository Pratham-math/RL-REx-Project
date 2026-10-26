"""Run searches on repair tests only. Use evaluate.py afterwards for hidden tests."""
import argparse
import hashlib
import json
from pathlib import Path
import random

from rex import METHODS, search
from runtime import Ollama, DockerEvaluator, load_jsonl, dump_json


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tasks', required=True, help='Public/repair JSONL, no hidden tests')
    ap.add_argument('--out', required=True)
    ap.add_argument('--methods', nargs='+', choices=METHODS, default=list(METHODS))
    ap.add_argument('--seeds', nargs='+', type=int, default=[0, 1, 2])
    ap.add_argument('--budget', type=int, default=16)
    ap.add_argument('--model', default='qwen2.5-coder:7b')
    ap.add_argument('--url', default='http://localhost:11434')
    ap.add_argument('--temperature', type=float, default=1.0)
    ap.add_argument('--max-tokens', type=int, default=2048)
    ap.add_argument('--context', type=int, default=32768)
    ap.add_argument('--constant', type=float, default=20)
    ap.add_argument('--eta', type=float, default=.5)
    ap.add_argument('--gamma', type=float, default=.5)
    ap.add_argument('--runner-image', default='python:3.11-slim')
    ap.add_argument('--test-timeout', type=float, default=5.0)
    args = ap.parse_args()
    tasks = load_jsonl(args.tasks)
    if not tasks or len({t['id'] for t in tasks}) != len(tasks):
        raise ValueError('Tasks must be nonempty with unique IDs.')
    if any('hidden_tests' in t or 'solution' in t for t in tasks):
        raise ValueError('Search input must not contain hidden tests or reference solutions.')
    if args.budget < 1 or not 0 <= args.eta <= 1 or not 0 <= args.gamma <= 1:
        raise ValueError('Invalid budget, eta or gamma.')
    out = Path(args.out)
    if out.exists():
        raise FileExistsError('Use a new output directory; do not overwrite experiments.')
    model = Ollama(args.model, args.url, args.temperature, args.max_tokens, args.context)
    judge = DockerEvaluator(args.runner_image, args.test_timeout)
    info = model.info()
    out.mkdir(parents=True)
    dump_json(out / 'config.json', {**vars(args), 'task_count': len(tasks),
        'task_sha256': hashlib.sha256(Path(args.tasks).read_bytes()).hexdigest(),
        'model_info': info, 'runner_image_id': judge.image_info,
        'status': 'incomplete', 'search_protocol': 'visible-only, earliest-best tie break'})
    jobs = [(t, m, s) for t in tasks for m in args.methods for s in args.seeds]
    random.Random(2026).shuffle(jobs)  # Reduce time/order effects.
    print(f'{len(jobs)} runs; at most {len(jobs) * args.budget} LLM calls.', flush=True)
    for number, (task, method, seed) in enumerate(jobs, 1):
        ident = hashlib.sha256(task['id'].encode()).hexdigest()[:16]
        log_path = out / f'{ident}_{method}_{seed}.jsonl'
        with log_path.open('w') as log:
            def record(event):
                log.write(json.dumps(event) + '\n')
                log.flush()
            result = search(task['statement'], task['repair_tests'], model, judge,
                method, seed, args.budget, args.constant, args.eta, args.gamma, record)
        result.pop('events')
        dump_json(out / f'{ident}_{method}_{seed}.json', {
            'task_id': task['id'], 'method': method, 'seed': seed,
            'difficulty': task.get('difficulty', 'unknown'),
            'budget': args.budget, 'log_file': log_path.name, **result})
        print(f'{number}/{len(jobs)} {task["id"]} {method} seed={seed} '
              f'calls={result["calls"]} repair_solved={result["visible_solved"]}', flush=True)
    cfg = json.loads((out / 'config.json').read_text())
    cfg['status'] = 'complete'
    dump_json(out / 'config.json', cfg)


if __name__ == '__main__':
    main()
