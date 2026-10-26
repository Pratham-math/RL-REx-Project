"""Make a fixed stdio-only APPS subset with separate repair and hidden files."""
import argparse
import hashlib
import json
from pathlib import Path
import random

from runtime import dump_json


def partition_tests(statement, pairs, rng, visible_fraction=.5):
    # Identical inputs cannot occur on both sides. Conflicts invalidate a task.
    unique = {}
    for inp, out in pairs:
        # Conservatively treat whitespace-equivalent inputs as duplicates.
        key = ' '.join(inp.split())
        if key in unique and unique[key]['output'].split() != out.split():
            raise ValueError('Conflicting expected outputs for the same input.')
        unique.setdefault(key, {'input': inp, 'output': out})
    cases = list(unique.values())
    rng.shuffle(cases)
    normalized_statement = ' '.join(statement.split())
    # Never hold out an input visibly contained in the statement. This is
    # deliberately conservative; manually audit the selected tasks as well.
    repair = [c for c in cases if ' '.join(c['input'].split()) in normalized_statement]
    rest = [c for c in cases if c not in repair]
    count = max(3, int(len(cases) * visible_fraction))
    take = max(0, count - len(repair))
    repair.extend(rest[:take])
    hidden = rest[take:]
    if len(repair) < 3 or len(hidden) < 3:
        raise ValueError('Need at least 3 repair and 3 non-example hidden cases.')
    return repair, hidden


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apps-root', required=True)
    ap.add_argument('--out', default='data')
    ap.add_argument('--count', type=int, default=50, help='Evaluation tasks')
    ap.add_argument('--dev-count', type=int, default=10)
    ap.add_argument('--difficulty', nargs='+', default=['interview'])
    ap.add_argument('--seed', type=int, default=2026)
    ap.add_argument('--max-tests', type=int, default=20)
    args = ap.parse_args()
    root, output = Path(args.apps_root), Path(args.out)
    if output.exists():
        raise FileExistsError('Use a new dataset directory to preserve the split.')
    if args.count < 1 or args.dev_count < 0 or args.max_tests < 6:
        raise ValueError('Invalid counts; need at least 6 tests per task.')
    paths = sorted(root.rglob('question.txt'))
    random.Random(args.seed).shuffle(paths)
    selected, rejected = [], {}
    for path in paths:
        try:
            statement = path.read_text()
            io = json.loads(path.with_name('input_output.json').read_text())
            meta = json.loads(path.with_name('metadata.json').read_text())
            if meta['difficulty'] not in args.difficulty:
                continue
            if io.get('fn_name'):
                raise ValueError('function-call task')
            if len(io['inputs']) != len(io['outputs']):
                raise ValueError('mismatched test counts')
            pairs = list(zip(io['inputs'], io['outputs']))
            if not all(isinstance(x, str) and isinstance(y, str) for x, y in pairs):
                raise ValueError('non-string or alternative-output test')
            if any(len(x) > 20000 or len(y) > 20000 for x, y in pairs):
                raise ValueError('large test input/output')
            task_id = path.parent.relative_to(root).as_posix()
            task_seed = int(hashlib.sha256(f'{args.seed}:{task_id}'.encode()).hexdigest()[:16],16)
            rng = random.Random(task_seed)
            rng.shuffle(pairs)
            repair, hidden = partition_tests(statement, pairs[:args.max_tests], rng)
            selected.append({'id': task_id, 'difficulty': meta['difficulty'],
                'statement': statement, 'repair_tests': repair, 'hidden_tests': hidden})
            if len(selected) == args.count + args.dev_count:
                break
        except (ValueError, KeyError, OSError) as exc:
            key = str(exc)[:120]
            rejected[key] = rejected.get(key, 0) + 1
    if len(selected) < args.count + args.dev_count:
        raise ValueError(f'Only {len(selected)} eligible tasks. Reduce counts or broaden difficulty. '
                         f'Filtering: {rejected}')
    output.mkdir(parents=True)
    for name, subset in [('dev', selected[:args.dev_count]), ('eval', selected[args.dev_count:])]:
        public = [{k: v for k, v in t.items() if k != 'hidden_tests'} for t in subset]
        private = [{'id': t['id'], 'hidden_tests': t['hidden_tests']} for t in subset]
        for suffix, data in [('repair', public), ('hidden', private)]:
            (output / f'{name}_{suffix}.jsonl').write_text(
                ''.join(json.dumps(t) + '\n' for t in data))
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.glob('*.jsonl')}
    dump_json(output / 'manifest.json', {**vars(args), 'task_ids': [t['id'] for t in selected],
        'rejections_before_target_reached': rejected, 'sha256': hashes,
        'comparator': 'whitespace token equality; stdio only; not the official APPS harness',
        'selection': 'fixed shuffled order before any model runs; max-tests is a fixed cap'})
    print(f'Prepared {args.dev_count} development and {args.count} evaluation tasks in {output}.')


if __name__ == '__main__':
    main()
