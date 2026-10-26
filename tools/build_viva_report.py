"""Turn completed, sealed pilot evidence into a concise viva package."""
import base64
import html
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from rexbench.evaluate import verify_seal
from rexbench.report import csv_file
from rexbench.store import Store
from rexbench.util import fingerprint, now, read_json, write_json

LABELS = {'resample': 'Resampling', 'rex': 'REx baseline', 'rex_progress_cost': 'Progress + cost REx'}
COLORS = {'resample': '#a4acbb', 'rex': '#3d6dac', 'rex_progress_cost': '#127b70'}
METHODS = list(LABELS)


def build(root=Path('runs/viva_complete_pilot'), out=Path('reports/viva')):
    verify_seal(root)
    standard = Path('reports/viva_analysis')
    summary = read_json(standard / 'summary.json')
    evaluation = list((root / 'evaluations').glob('*/evaluation.json'))
    if len(evaluation) != 1:
        raise ValueError('Exactly one completed hidden evaluation is required')
    evaluated = read_json(evaluation[0])
    if evaluated['result_hash'] != fingerprint({k: v for k, v in evaluated.items() if k != 'result_hash'}):
        raise ValueError('Evaluation hash mismatch')
    rows = evaluated['rows']
    final = [r for r in rows if r['axis'] == 'calls' and r['budget'] == 8]
    headline = {m: next(r for r in summary if r['method'] == m and r['axis'] == 'calls' and r['budget'] == 8) for m in METHODS}
    out.mkdir(parents=True, exist_ok=True)
    figures = out / 'figures'
    figures.mkdir(exist_ok=True)
    store = Store(root, readonly=True)
    trial_rows, diagnostics, comparisons = [], {}, []
    try:
        tasks = sorted({r['task_id'] for r in final})
        all_events = {}
        for job in read_json(root / 'plan.json')['jobs']:
            state = store.load(job['id'])
            result = next(r for r in final if r['trial_id'] == job['id'])
            events = [json.loads(r['payload']) for r in store.rows(
                "SELECT payload FROM events WHERE trial_id=? AND kind='step_committed' ORDER BY number", (job['id'],))]
            all_events[(job['task_id'], job['method'])] = events
            trial_rows.append({'task': job['task_id'], 'method': job['method'], 'hidden_passed': round(result['hidden_fraction'] * 5),
                               'hidden_total': 5, 'hidden_solved': result['solved'], 'repair_fraction': result['visible_fraction'],
                               'calls': state.ledger.inference_attempts, 'actual_tokens': state.ledger.tokens,
                               'model_seconds': state.ledger.model_seconds, 'judge_seconds': state.ledger.judge_seconds,
                               'stop_reason': state.stop_reason, 'final_code_hash': result['code_hash']})
        for method in METHODS:
            events = [e for (task, m), es in all_events.items() if m == method for e in es]
            diagnostics[method] = {'generations': len(events), 'nonroot_repairs': sum(e['parent_id'] != 'root' for e in events),
                                   'root_generations': sum(e['parent_id'] == 'root' for e in events),
                                   'positive_partial_progress_updates': sum(0 < e['reward'] < 1 for e in events),
                                   'invalid_completions': sum(e['parse_status'] == 'INVALID_COMPLETION' for e in events)}
        for task in tasks:
            left, right = all_events[(task, 'rex')], all_events[(task, 'rex_progress_cost')]
            a = next(r for r in trial_rows if r['task'] == task and r['method'] == 'rex')
            b = next(r for r in trial_rows if r['task'] == task and r['method'] == 'rex_progress_cost')
            comparisons.append({'task': task, 'same_parent_sequence': [e['parent_id'] for e in left] == [e['parent_id'] for e in right],
                                'same_generated_code_sequence': [e['child']['code_hash'] for e in left] == [e['child']['code_hash'] for e in right],
                                'same_final_code': a['final_code_hash'] == b['final_code_hash'],
                                'same_actual_tokens': a['actual_tokens'] == b['actual_tokens'],
                                'same_hidden_result': a['hidden_passed'] == b['hidden_passed']})
    finally:
        store.close()
    # Full work accounting includes discarded all-method runs and the unknown request.
    source_costs = []
    for source_root in (Path('runs/development_pilot_gpu'), Path('runs/viva_rerun_0146'), Path('runs/development_pilot')):
        from rexbench.experiment import status
        value = status(source_root)
        source_costs.append({'source': str(source_root), 'requests': value['inference_attempts'],
                             'known_tokens': value['known_actual_tokens'], 'unknown_requests': value['unknown_usage_requests']})
    modified = headline['rex_progress_cost']
    baseline = headline['rex']
    resample = headline['resample']
    delta_pp = 100 * modified['delta_vs_rex']
    if modified['delta_ci_low'] <= 0 <= modified['delta_ci_high']:
        finding = (f'The implemented extension solved {modified["hidden_successes"]}/5 problems on all hidden tests '
                   f'({modified["success"]:.0%}) at up to eight calls. Its difference versus baseline REx was '
                   f'{delta_pp:+.0f} percentage points; this pilot does not establish an improvement over REx.')
    else:
        finding = (f'The extension changed hidden success by {delta_pp:+.0f} percentage points versus REx in this five-task pilot. '
                   'The sample is too small for a broad effectiveness claim.')
    same_traces = all(c['same_parent_sequence'] and c['same_generated_code_sequence'] for c in comparisons)
    method_costs = {m: {'calls': sum(r['calls'] for r in trial_rows if r['method']==m),
                        'tokens': sum(r['actual_tokens'] for r in trial_rows if r['method']==m)} for m in METHODS}
    call_reduction = 100 * (1-method_costs['rex_progress_cost']['calls']/method_costs['resample']['calls'])
    token_difference = 100 * (method_costs['rex_progress_cost']['tokens']/method_costs['resample']['tokens']-1)
    practical_finding = (
        f'The implemented repair system solved {modified["hidden_successes"]}/5 tasks using '
        f'{method_costs["rex_progress_cost"]["calls"]} calls, versus {resample["hidden_successes"]}/5 tasks '
        f'and {method_costs["resample"]["calls"]} calls for resampling ({call_reduction:.0f}% fewer calls). '
        f'It used {token_difference:+.1f}% tokens versus resampling. Baseline REx had the same measured result as the extension.'
    )
    if same_traces:
        mechanism = ('REx and the extension made identical branch choices and generated identical code sequences on all five tasks '
                     f'({diagnostics["rex"]["generations"]} generations each). Their final token costs were also identical. '
                     f'The extension received only {diagnostics["rex_progress_cost"]["positive_partial_progress_updates"]} positive partial-progress updates. '
                     'The modified scores and updates therefore did not change the selected trajectories in this setting.')
    else:
        mechanism = 'See mechanism_diagnostics.json for measured differences in branch choices, code sequences and progress rewards.'
    facts = {
        'created': now(), 'scope': 'Five-task development pilot, one seed, three methods; not final study',
        'finding': finding, 'practical_finding': practical_finding, 'mechanism': mechanism, 'headline': headline, 'trials': trial_rows,
        'policy_diagnostics': diagnostics, 'trace_comparisons': comparisons, 'source_campaign_costs': source_costs,
        'selected_requests': sum(r['calls'] for r in trial_rows), 'selected_actual_tokens': sum(r['actual_tokens'] for r in trial_rows),
        'all_pilot_requests_including_archived_cpu': sum(r['requests'] for r in source_costs),
        'all_pilot_known_tokens_including_archived_cpu': sum(r['known_tokens'] for r in source_costs),
        'all_pilot_unknown_requests': sum(r['unknown_requests'] for r in source_costs),
        'evaluation_version': evaluated['version'], 'search_seal': read_json(root / 'seal.json')['seal_hash'],
        'limitations': ['Five tasks and one seed; bootstrap intervals cannot establish broad generalization',
                        'Development-only APPS mirror subset; not an official APPS score',
                        'Only 3-6 repair tests and five hidden tests per task; finite tests do not prove correctness',
                        'Only combined extension evaluated; no progress-only or cost-only ablation',
                        'No model training or weight updates; no optimality or exact-posterior guarantee',
                        'One task was rerun for all methods under a fixed pre-evaluation replacement rule',
                        'Original interrupted request remains unknown and is counted in total-work accounting'],
    }
    write_json(out / 'results.json', facts)
    write_json(out / 'mechanism_diagnostics.json', {'policies': diagnostics, 'matched_traces': comparisons})
    csv_file(out / 'per_task_results.csv', trial_rows)
    csv_file(out / 'work_accounting.csv', source_costs)
    for name in ('summary.csv', 'auc.csv', 'diagnostics.json', 'results.md', 'reproduce.md', 'coverage.json', 'replay.html', 'replay_success.html', 'replay_loss.html'):
        if (standard / name).exists():
            shutil.copy2(standard / name, out / name)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.labelcolor': '#203449', 'text.color': '#203449', 'font.size': 11})
    names = [LABELS[m] for m in METHODS]
    success = [headline[m]['hidden_successes'] for m in METHODS]
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    bars = ax.bar(names, success, color=[COLORS[m] for m in METHODS], width=.58)
    for bar, n in zip(bars, success):
        ax.text(bar.get_x() + bar.get_width()/2, n + .12, f'{n}/5 ({20*n:.0f}%)', ha='center', weight='bold')
    ax.set(ylim=(0,5.8), yticks=range(6), ylabel='Problems passing all 5 hidden tests',
           title='Hidden-test success after up to 8 calls\n5 development tasks | 1 seed | identical model and tests')
    ax.grid(axis='y', alpha=.15)
    fig.tight_layout()
    fig.savefig(figures / 'hidden_success.png', dpi=180)
    plt.close(fig)
    matrix = np.array([[next(r['hidden_passed'] for r in trial_rows if r['task']==task and r['method']==m) for m in METHODS] for task in tasks])
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.imshow(matrix, cmap='YlGnBu', vmin=0, vmax=5, aspect='auto')
    ax.set_xticks(range(3), names)
    ax.set_yticks(range(len(tasks)), tasks)
    for i in range(len(tasks)):
        for j in range(3):
            ax.text(j, i, f'{matrix[i,j]}/5', ha='center', va='center', color='white' if matrix[i,j]>=3 else '#203449', weight='bold')
    ax.set_title('Hidden tests passed by the returned program\nAll methods paired on the same five tasks')
    fig.tight_layout()
    fig.savefig(figures / 'per_task_hidden.png', dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11,4.4))
    for axis, title, y in ((axes[0], 'Observed token cost', 'Tokens across 5 selected trials'),
                           (axes[1], 'Model calls used', 'Calls across 5 selected trials')):
        vals = [sum(r['actual_tokens'] if axis is axes[0] else r['calls'] for r in trial_rows if r['method']==m) for m in METHODS]
        bars=axis.bar(range(3), vals, color=[COLORS[m] for m in METHODS])
        axis.set_xticks(range(3), ['Resample','REx','Progress\n+ cost'])
        axis.set(title=title,ylabel=y)
        for b,v in zip(bars,vals):
            axis.text(b.get_x()+b.get_width()/2,v*1.025,f'{v:,}',ha='center',fontsize=10)
        axis.set_ylim(0,max(vals)*1.18)
    fig.suptitle('Comparison cost: selected trials only; discarded work recorded separately', fontsize=11)
    fig.tight_layout()
    fig.savefig(figures / 'cost_comparison.png',dpi=180)
    plt.close(fig)
    for name in ('success_vs_calls.png','success_vs_tokens.png','cost_estimator.png'):
        shutil.copy2(standard / name, figures / name)
    # Distinguishable line styles make coincident baseline/extension curves visible.
    for axis in ('calls','tokens'):
        fig,ax=plt.subplots(figsize=(8.5,4.6))
        for method in METHODS:
            group=sorted([r for r in summary if r['method']==method and r['axis']==axis],key=lambda r:r['budget'])
            ax.plot([r['budget'] for r in group],[r['success'] for r in group],label=LABELS[method],
                    color=COLORS[method],linewidth=3.5 if method=='rex' else 1.8,
                    linestyle='--' if method=='rex_progress_cost' else '-',marker='x' if method=='rex_progress_cost' else 'o')
            ax.fill_between([r['budget'] for r in group],[r['ci_low'] for r in group],[r['ci_high'] for r in group],color=COLORS[method],alpha=.07)
        ax.set(xlabel='Completed model calls' if axis=='calls' else 'Actual tokens: completed-generation prefixes',
               ylabel='Returned-program hidden success',ylim=(-.02,1.02),
               title='Hidden success across inference budgets\n5 development tasks | 1 seed | paired task bootstrap intervals')
        ax.legend(fontsize=9)
        ax.grid(alpha=.15)
        fig.tight_layout()
        fig.savefig(figures/f'success_vs_{axis}.png',dpi=180)
        plt.close(fig)
    # A curve of repair progress explains what feedback the search actually received.
    fig,ax=plt.subplots(figsize=(8.5,4.6))
    for m in METHODS:
        vals=[]
        for b in range(1,9):
            rs=[r for r in rows if r['method']==m and r['axis']=='calls' and r['budget']==b]
            vals.append(np.mean([r['visible_fraction'] for r in rs]))
        ax.plot(range(1,9),vals,marker='o',label=LABELS[m],color=COLORS[m],linestyle='--' if m=='rex_progress_cost' else '-')
    ax.set(xlabel='Completed model calls',ylabel='Mean best repair-test fraction',ylim=(0,1.03),
           title='Repair feedback during search\nThis is not hidden-test accuracy')
    ax.legend(loc='lower right',fontsize=9)
    ax.grid(alpha=.15)
    fig.tight_layout()
    fig.savefig(figures/'repair_progress.png',dpi=180)
    plt.close(fig)
    table_lines=['| Method | Hidden success at 8 calls | Calls used | Actual tokens |', '| --- | --- | --- | --- |']
    for m in METHODS:
        group=[r for r in trial_rows if r['method']==m]
        table_lines.append(f'| {LABELS[m]} | {headline[m]["hidden_successes"]}/5 ({headline[m]["success"]:.0%}) | {sum(r["calls"] for r in group)} | {sum(r["actual_tokens"] for r in group):,} |')
    table='\n'.join(table_lines)
    script=(f'"My project studies how to spend an LLM code-repair budget. I reproduced the REx search scheduler and implemented a combined progress- and cost-aware extension. '
            'The LLM itself stays frozen. Each candidate program is an arm; test pass fraction initializes its Beta distribution. '
            'My changes give fractional credit for a nonterminal improvement and divide the sampled priority by estimated token cost to the power 0.5. '
            'I compared resampling, baseline REx and the extension using Qwen2.5-Coder 7B on five development problems, one seed and up to eight nominal calls. '
            f'Hidden success was {resample["hidden_successes"]}/5 for resampling, {baseline["hidden_successes"]}/5 for REx and {modified["hidden_successes"]}/5 for the extension. '
            f'{finding} '
            'The trace analysis explains why: in this setting the extension followed the same branches as REx. '
            'My defensible contribution is the implemented search modification, the reproducible evaluation harness, and an honest empirical diagnosis. '
            'Next I would run separate component ablations with more tasks and seeds before claiming a general improvement."')
    qa=[
        ('What did you change from REx?', 'I kept its Beta-prior and Thompson-sampling structure, added fractional positive progress credit for incomplete repairs, and normalized selection scores by estimated tokens. Implementation: policies.observe/select; estimator: budgets.CostEstimator.'),
        ('Did you train an LLM or invent REx?', 'No. Qwen2.5-Coder weights are frozen. REx and Thompson sampling are prior work. My implemented extension changes inference-time search decisions; research novelty beyond this project has not been established.'),
        ('What exactly is the progress reward?', 'For a non-root, nonterminal repair: r = 0.5 * max(0, h_child - h_parent). Update alpha += r and beta += 1-r. Root partial generations get zero progress credit. On full repair success, save the solution and stop before updating its parent, following the upstream terminal rule.'),
        ('What exactly is cost awareness?', 'Sample theta from the same Beta distribution and choose the arm maximizing theta / max(1, estimated_tokens)^0.5. Start with prompt_characters/4 + 512 output tokens, then update estimates with current-trial observations. Measured costs use actual backend counts, not estimates.'),
        ('Why is this related to reinforcement learning?', 'It is an online bandit search policy with rewards and exploration/exploitation, as in the source REx formulation. It is not gradient training, RLHF or a full learned MDP policy. The progress update is a heuristic pseudo-count rule without an exact Bernoulli-posterior or optimality guarantee.'),
        ('Did your modification improve the result?', finding + ' ' + mechanism),
        ('Why might the trajectories be unchanged?', 'Only two positive partial-progress updates were observed in the modified policy, and all branch choices still matched REx. Strong C=20 priors, sparse feedback and the short eight-call budget are plausible explanations, not separately tested causal findings.'),
        ('How did you prevent test leakage?', 'Search sees only frozen repair tests and one sampled failing repair case. Hidden tests are loaded only by the post-search evaluator. The selected return is fixed by repair score before hidden judging; hidden success never selects a branch or solution.'),
        ('Why only five problems and one seed?', 'This is a small development pilot under local compute and viva time constraints. Each solved task changes success by 20 percentage points. It is not the planned 30-task, six-method, three-seed final study.'),
        ('How did you handle the interrupted run?', 'I preserved its unknown request and all original evidence. Before replacement inference and hidden evaluation, I froze a rule to rerun that entire problem for all three methods. A sealed analysis view imports those three fresh trials and the other twelve original trials with source IDs and hashes. I did not choose whichever rerun scored better.'),
        ('Can you attribute effects to progress versus cost?', 'No. This pilot tests the combined extension. Separate eta-only and gamma-only ablations exist as implementation options but were not executed here.'),
        ('How reliable is the comparison?', 'The setup and measured rows are traceable, but there are only five development tasks, one seed and five hidden tests per task. Report bootstrap intervals as descriptive; a zero-width paired interval for identical outcomes does not prove population equivalence. Finite suites, public-task contamination, sparse feedback and seed/runtime behavior limit generalization.'),
        ('What would you do next?', 'Run progress-only and cost-only ablations, collect richer development feedback, use more seeds and tasks, select parameters on development data, then freeze a separate final protocol and evaluate held-out tasks without further tuning.'),
    ]
    notes=(f'# Viva: progress- and cost-aware code repair\n\n{practical_finding}\n\n{finding}\n\n'
           '## Results to show\n\n'+table+'\n\nAll rows are five paired development tasks and seed 0. Hidden success means passing all five hidden tests for the repair-selected program.\n\n'
           '## What I implemented differently\n\n'
           '- Baseline: REx chooses a candidate by a Beta/Thompson draw initialized from repair pass fraction.\n'
           '- Progress: incomplete repairs receive fractional positive credit when they improve over their parent.\n'
           '- Cost: divide each draw by estimated tokens raised to gamma=0.5.\n'
           '- Engineering: frozen datasets/settings, isolated Docker judging, durable request/response accounting, checkpoint evaluation and trace replay.\n\n'
           '## What the evidence actually shows\n\n'+mechanism+'\n\n'
           '## 90-second speaking script\n\n'+script+'\n\n'
           '## Likely viva questions\n\n'+'\n\n'.join(f'### {q}\n\n{a}' for q,a in qa)+'\n\n'
           '## Cost and provenance\n\n'
           f'Selected comparison: {facts["selected_requests"]} calls and {facts["selected_actual_tokens"]:,} actual tokens, with no unknown usage. '
           f'All pilot work including discarded GPU trials and archived CPU work: {facts["all_pilot_requests_including_archived_cpu"]} requests, '
           f'{facts["all_pilot_known_tokens_including_archived_cpu"]:,} known tokens plus one request with unknown usage. '
           'Setup, smoke, reference audit and hidden judging are separate work. Do not call the known-token sum an exact total.\n\n'
           'Sources: Tang et al., Code Repair with LLMs gives an Exploration-Exploitation Tradeoff, NeurIPS 2024, arXiv:2405.17503v3; '
           'pinned authors code in vendor/REx; local policy code in src/rexbench/policies/__init__.py; selection protocol in docs/viva_selection_protocol.json.\n')
    (out/'VIVA_NOTES.md').write_text(notes,encoding='utf-8')
    (out/'SPEAKING_SCRIPT.txt').write_text(script+'\n',encoding='utf-8')
    (out/'WHAT_TO_CLAIM.md').write_text(
        '# Claims supported by this pilot\n\n'+practical_finding+'\n\n'+finding+'\n\n'+mechanism+'\n\n'
        'Say: "I implemented and tested a progress- and cost-aware extension of REx on a small development pilot."\n\n'
        'Do not claim a new LLM, model training, state-of-the-art APPS accuracy, an official APPS score, optimality, or a general improvement over REx. '
        'Do not present the original REx algorithm as your invention or the three-method comparison as a component ablation.\n',encoding='utf-8')
    def img(name):
        return 'data:image/png;base64,'+base64.b64encode((figures/name).read_bytes()).decode()
    def esc(s):
        return html.escape(str(s))
    table_html='<table><thead><tr><th>Method</th><th>Hidden success</th><th>Calls</th><th>Tokens</th></tr></thead><tbody>'
    for m in METHODS:
        g=[r for r in trial_rows if r['method']==m]
        table_html+=f'<tr><td>{LABELS[m]}</td><td>{headline[m]["hidden_successes"]}/5 ({headline[m]["success"]:.0%})</td><td>{sum(r["calls"] for r in g)}</td><td>{sum(r["actual_tokens"] for r in g):,}</td></tr>'
    table_html+='</tbody></table>'
    sections=[
        ('Progress- and cost-aware code repair', f'<p class="eyebrow">MEASURED DEVELOPMENT PILOT / 26 OCT 2026</p><p class="lead">Can a repair search policy use partial progress and token cost more effectively?</p><div class="cards"><div><b>5</b><span>problems</span></div><div><b>3</b><span>methods</span></div><div><b>1</b><span>seed</span></div><div><b>8</b><span>nominal calls</span></div></div><p>{esc(finding)}</p><p class="small">Qwen2.5-Coder 7B, Q4_K_M; RTX 4060 Laptop; frozen weights. This is a pilot, not the final study.</p>'),
        ('What changed?', '<div class="columns"><div><h3>REx baseline</h3><p>Each candidate is an arm. Initialize Beta(1+20h, 1+20(1-h)), where h is repair pass fraction. Sample a priority and refine the chosen arm.</p></div><div><h3>Implemented extension</h3><p><b>Progress:</b> r = 0.5 max(0, h_child - h_parent) for nonterminal, non-root repairs.</p><p><b>Cost:</b> priority = Beta draw / estimated_tokens<sup>0.5</sup>.</p></div></div><div class="callout">No LLM training. The change is to inference-time search. Progress shaping is heuristic, with no optimality guarantee.</div>'),
        ('How the comparison was controlled', '<ol><li>Same model, prompts, parser, task bytes, test suites and judge limits.</li><li>Compare independent resampling, baseline REx and combined extension.</li><li>Use repair feedback to search and select the returned program.</li><li>Seal all 15 selected trials before hidden evaluation.</li><li>Evaluate 150 call/token checkpoints using five hidden tests each.</li></ol><p class="small">One interrupted task was rerun for all methods under a fixed pre-evaluation rule. Original records and costs are preserved.</p>'),
        ('Measured hidden-test results', table_html+f'<img src="{img("hidden_success.png")}" alt="Hidden success by method"><p class="small">A problem is solved only when every hidden test passes. Each problem is 20 percentage points; n=5 limits inference.</p>'),
        ('Which tasks were solved?', f'<img src="{img("per_task_hidden.png")}" alt="Hidden tests passed by task"><p>{esc(finding)}</p>'),
        ('Behavior and cost', f'<p>{esc(mechanism)}</p><img src="{img("cost_comparison.png")}" alt="Measured selected-trial costs"><p class="small">These costs describe selected trials. Discarded and interrupted work remains in work_accounting.csv.</p>'),
        ('Search progress', f'<img src="{img("success_vs_calls.png")}" alt="Hidden success over model calls"><p class="small">Curves evaluate the repair-selected return at each completed-call checkpoint. Hidden results never guided search.</p>'),
        ('What I can defend in the viva', '<ul><li>I reproduced the REx scheduler and built an auditable local evaluation harness.</li><li>I implemented progress credit plus estimated-token priority normalization.</li><li>I measured the result and inspected why behavior did or did not change.</li></ul><div class="callout">'+esc(finding)+'</div><p>Next: separate component ablations, more tasks/seeds, richer development feedback, and a frozen held-out final evaluation.</p><p class="small">Baseline source: Tang et al., NeurIPS 2024. <a href="https://arxiv.org/abs/2405.17503">arXiv:2405.17503</a>. Local evidence: results.json, composition.json, summary.csv and replay.html.</p>'),
    ]
    content=''.join(f'<section id="s{i+1}"><div class="number">{i+1:02d} / {len(sections):02d}</div><h1>{title}</h1>{body}</section>' for i,(title,body) in enumerate(sections))
    qa_html='<section><h1>Questions and answers</h1>'+''.join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q,a in qa)+'</section>'
    page='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>REx pilot - viva results</title><style>
    *{box-sizing:border-box}body{margin:0;background:#edf1f4;color:#173046;font:18px/1.55 system-ui,Arial}nav{position:sticky;top:0;z-index:3;background:#122c3e;color:white;padding:12px 5vw;display:flex;gap:20px;align-items:center}nav a{color:white;text-decoration:none;font-size:14px}nav b{margin-right:auto}section{position:relative;max-width:1120px;margin:30px auto;background:white;border-radius:14px;padding:48px 62px;box-shadow:0 6px 30px #1730460a;break-after:page;scroll-margin-top:80px}h1{font-size:35px;line-height:1.15;margin:4px 0 28px;max-width:90%}h3{font-size:22px}.number{position:absolute;right:30px;top:22px;font-size:12px;color:#667b88}.eyebrow{font-size:12px;letter-spacing:.13em;color:#127b70;font-weight:bold}.lead{font-size:28px;max-width:800px}.small{font-size:13px;color:#53697b}img{display:block;width:100%;max-height:500px;object-fit:contain;margin:24px auto}table{width:100%;border-collapse:collapse;font-size:17px}th{text-align:left;background:#e9f3f1}td,th{padding:12px;border-bottom:1px solid #dce5eb}.columns{display:grid;grid-template-columns:1fr 1fr;gap:42px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;margin:30px 0}.cards div{border:1px solid #cbdeda;border-radius:8px;padding:20px}.cards b{display:block;font-size:38px;color:#127b70}.cards span{font-size:14px}.callout{padding:20px 24px;background:#eaf5f1;border-left:5px solid #127b70;margin:24px 0}li{margin:15px 0}details{border-bottom:1px solid #dce5eb;padding:16px 0}summary{font-weight:650;cursor:pointer}a{color:#1e659b}@media(max-width:800px){section{margin:14px;padding:32px 22px}h1{font-size:28px}.columns{grid-template-columns:1fr}.cards{grid-template-columns:1fr 1fr}nav{gap:12px}}@media print{body{background:white;font-size:12pt}nav{display:none}section{margin:0;box-shadow:none;border-radius:0;padding:20px 10px;max-width:none}h1{font-size:25pt}img{max-height:130mm}.number{top:0}details{break-inside:avoid}}
    </style></head><body><nav><b>REx / pilot results</b><a href="#s1">Overview</a><a href="#s4">Results</a><a href="#s8">Conclusion</a><a href="VIVA_NOTES.md">Notes</a><a href="replay.html">Trace</a></nav>'''+content+qa_html+'</body></html>'
    (out/'OPEN_FOR_VIVA.html').write_text(page,encoding='utf-8')
    (out/'START_HERE.md').write_text('# Open these for the viva\n\n1. `OPEN_FOR_VIVA.html`: presentation-ready results, method, graphs and Q&A.\n2. `VIVA_NOTES.md`: full speaking notes and likely examiner questions.\n3. `SPEAKING_SCRIPT.txt`: concise rehearsal script.\n4. `figures/`: PNG graphs for slides.\n5. `results.json`, `per_task_results.csv`, `summary.csv`: exact measured data.\n6. `work_accounting.csv`: source run costs including discarded and interrupted work.\n\n'+finding+'\n\n'+mechanism+'\n',encoding='utf-8')
    return {'report':str(out),'finding':finding,'mechanism':mechanism,'selected_calls':facts['selected_requests']}


if __name__=='__main__':
    print(json.dumps(build()))
