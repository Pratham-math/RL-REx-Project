"""Offline hidden evaluation of candidates already selected using visible tests."""
import argparse
import json
from pathlib import Path

from runtime import DockerEvaluator, load_jsonl, dump_json


def choose_event(events, calls=None, tokens=None):
    eligible = [e for e in events if (calls is None or e['call'] <= calls)
                and (tokens is None or e['total_tokens'] <= tokens)]
    return eligible[-1] if eligible else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runs', required=True)
    ap.add_argument('--hidden', required=True)
    ap.add_argument('--call-budgets', nargs='+', type=int, default=[1, 2, 4, 8, 16])
    ap.add_argument('--token-budgets', nargs='+', type=int, default=[2048,4096,8192,16384,32768,65536])
    args = ap.parse_args()
    folder = Path(args.runs)
    config = json.loads((folder / 'config.json').read_text())
    if config['status'] != 'complete':
        raise ValueError('Complete all searches before inspecting hidden results.')
    hidden_rows = load_jsonl(args.hidden)
    hidden = {t['id']: t['hidden_tests'] for t in hidden_rows}
    if len(hidden) != len(hidden_rows) or any(not t for t in hidden.values()):
        raise ValueError('Hidden tasks need unique IDs and nonempty tests.')
    if max(args.call_budgets) > config['budget']:
        raise ValueError('Requested call budget exceeds the completed search budget.')
    judge = DockerEvaluator(config['runner_image'], config['test_timeout'])
    if judge.image_info != config['runner_image_id']:
        raise ValueError('Runner image changed since search; restore the recorded image.')
    rows = []
    for path in sorted(folder.glob('*.json')):
        if path.name in ('config.json', 'evaluation.json'):
            continue
        run = json.loads(path.read_text())
        if 'log_file' not in run:
            continue
        events = load_jsonl(folder / run['log_file'])
        cache = {}
        for kind, budgets in [('calls', args.call_budgets), ('tokens', args.token_budgets)]:
            for budget in budgets:
                event = choose_event(events, **{kind: budget})
                # Unsolved runs that hit the call cap before a token budget are
                # right-censored, not evidence of token-budget performance.
                censored = (kind == 'tokens' and not run['visible_solved']
                            and events[-1]['total_tokens'] < budget)
                code = event['selected_code'] if event else None
                if code is not None and code not in cache:
                    cache[code] = judge(code, hidden[run['task_id']])
                ev = cache.get(code)
                rows.append({'task_id': run['task_id'], 'method': run['method'],
                    'seed': run['seed'], 'axis': kind, 'budget': budget,
                    'censored': censored,
                    'solved': bool(ev and ev.solved), 'hidden_fraction': ev.h if ev else 0.,
                    'visible_fraction': event['best_h'] if event else 0.,
                    'actual_calls': event['call'] if event else 0,
                    'actual_tokens': event['total_tokens'] if event else 0})
    dump_json(folder / 'evaluation.json', rows)
    print(f'Saved {len(rows)} offline evaluations. No result was sent back to search.')


if __name__ == '__main__':
    main()
