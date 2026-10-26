"""Real-run curves, task-bootstrap intervals and paired REx comparisons."""
import argparse
import csv
import json
from pathlib import Path
import random
import statistics


def interval(values, seed=2026, samples=2000):
    # The resampling unit is the task, after averaging its repeated seeds.
    rng = random.Random(seed)
    bootstrap = sorted(statistics.mean(rng.choices(values, k=len(values)))
                       for _ in range(samples))
    return bootstrap[int(.025 * samples)], bootstrap[int(.975 * samples)]


def aggregates(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault((row['axis'], row['budget']), []).append(row)
    result = []
    for (axis, budget), group in sorted(grouped.items()):
        # Never silently drop censored individual runs; omit the entire point.
        if any(r['censored'] for r in group):
            print(f'Omitting {axis}={budget}: call cap censored at least one run.')
            continue
        methods = sorted({r['method'] for r in group})
        keys = [{(r['task_id'], r['seed']) for r in group if r['method'] == m}
                for m in methods]
        if any(k != keys[0] for k in keys):
            raise ValueError('Methods were not evaluated on the same task/seed pairs.')
        task_values = {}
        for method in methods:
            subset = [r for r in group if r['method'] == method]
            tasks = sorted({r['task_id'] for r in subset})
            values = {t: statistics.mean(float(r['solved']) for r in subset if r['task_id'] == t)
                      for t in tasks}
            task_values[method] = values
        for method in methods:
            subset = [r for r in group if r['method'] == method]
            values = list(task_values[method].values())
            low, high = interval(values)
            solved = sum(r['solved'] for r in subset)
            spend = sum(r['actual_tokens'] for r in subset)
            item = {'axis': axis, 'budget': budget, 'method': method,
                'n_tasks': len(values), 'n_runs': len(subset),
                'success_rate': statistics.mean(values), 'ci_low': low, 'ci_high': high,
                'mean_tokens_spent': statistics.mean(r['actual_tokens'] for r in subset),
                'mean_calls_spent': statistics.mean(r['actual_calls'] for r in subset),
                'tokens_per_success_including_failures': spend / solved if solved else None,
                'visible_pass_hidden_fail_rate': statistics.mean(
                    r['visible_fraction'] == 1 and not r['solved'] for r in subset),
                'delta_vs_rex': None, 'delta_ci_low': None, 'delta_ci_high': None}
            if 'rex' in task_values:
                differences = [task_values[method][t] - task_values['rex'][t]
                               for t in task_values['rex']]
                item['delta_vs_rex'] = statistics.mean(differences)
                item['delta_ci_low'], item['delta_ci_high'] = interval(differences)
            result.append(item)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runs', required=True)
    args = ap.parse_args()
    folder = Path(args.runs)
    rows = json.loads((folder / 'evaluation.json').read_text())
    summary = aggregates(rows)
    if not summary:
        raise ValueError('No complete comparison points; increase call cap or reduce token budgets.')
    with (folder / 'summary.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for axis in ['calls', 'tokens']:
        subset = [r for r in summary if r['axis'] == axis]
        if not subset:
            continue
        fig, ax = plt.subplots(figsize=(8, 5))
        for method in sorted({r['method'] for r in subset}):
            points = sorted([r for r in subset if r['method'] == method], key=lambda r:r['budget'])
            x = [r['budget'] for r in points]
            ax.plot(x, [100 * r['success_rate'] for r in points], 'o-', label=method)
            ax.fill_between(x, [100*r['ci_low'] for r in points],
                            [100*r['ci_high'] for r in points], alpha=.08)
        ax.set(xlabel=f'Budget ({axis})', ylabel='Hidden-test success (%)', ylim=(0,100),
               title='Returned-solution accuracy at equal budgets')
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(folder / f'success_vs_{axis}.png', dpi=180)
        plt.close(fig)
    print(f'Saved summary.csv and complete comparison curves in {folder}.')


if __name__ == '__main__':
    main()
