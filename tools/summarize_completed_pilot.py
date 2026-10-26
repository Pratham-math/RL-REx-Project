"""Scientific pilot findings, costs and plots; no viva/presentation material."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from rexbench.evaluate import verify_seal
from rexbench.experiment import status
from rexbench.report import csv_file
from rexbench.store import Store
from rexbench.util import fingerprint, now, read_json, write_json


def summarize():
    root=Path('runs/viva_complete_pilot')
    out=Path('reports/development_pilot_final')
    frozen=verify_seal(root)
    evaluated=read_json(next((root/'evaluations').glob('*/evaluation.json')))
    if evaluated['result_hash'] != fingerprint({k:v for k,v in evaluated.items() if k!='result_hash'}):
        raise ValueError('Evaluation checksum mismatch')
    rows=evaluated['rows']
    assert len(rows)==150 and all(not r['censored'] for r in rows)
    assert len(evaluated['outcomes'])==150
    assert sum(len(r['evaluation']['outcomes']) for r in evaluated['outcomes'])==750
    assert all(o['status']!='INFRA_ERROR' for r in evaluated['outcomes'] for o in r['evaluation']['outcomes'])
    methods=['resample','rex','rex_progress_cost']
    labels={'resample':'Resampling','rex':'REx baseline','rex_progress_cost':'Progress + cost REx'}
    palette={'resample':'#8e9aaa','rex':'#416ea8','rex_progress_cost':'#127b70'}
    final=[r for r in rows if r['axis']=='calls' and r['budget']==8]
    summary=read_json(out/'summary.json')
    source_costs=[]
    for source in ('runs/development_pilot_gpu','runs/viva_rerun_0146','runs/development_pilot'):
        data=status(Path(source))
        source_costs.append({'source':source,'requests':data['inference_attempts'],'known_actual_tokens':data['known_actual_tokens'],
                             'unknown_usage_requests':data['unknown_usage_requests']})
    store=Store(root,readonly=True)
    per_task=[]
    event_map={}
    for job in read_json(root/'plan.json')['jobs']:
        state=store.load(job['id'])
        result=next(r for r in final if r['trial_id']==job['id'])
        events=[json.loads(r['payload']) for r in store.rows("SELECT payload FROM events WHERE trial_id=? AND kind='step_committed' ORDER BY number",(job['id'],))]
        event_map[(job['task_id'],job['method'])]=events
        per_task.append({'task':job['task_id'],'method':job['method'],'hidden_tests_passed':round(5*result['hidden_fraction']),
                         'hidden_tests_total':5,'hidden_solved':result['solved'],'repair_fraction':result['visible_fraction'],
                         'calls':state.ledger.inference_attempts,'actual_tokens':state.ledger.tokens,
                         'model_seconds':state.ledger.model_seconds,'judge_seconds':state.ledger.judge_seconds,
                         'code_hash':result['code_hash']})
    store.close()
    tasks=sorted({r['task'] for r in per_task})
    comparisons=[]
    for task in tasks:
        a,b=event_map[(task,'rex')],event_map[(task,'rex_progress_cost')]
        comparisons.append({'task':task,'same_parent_sequence':[e['parent_id'] for e in a]==[e['parent_id'] for e in b],
                            'same_generated_code_sequence':[e['child']['code_hash'] for e in a]==[e['child']['code_hash'] for e in b],
                            'generations_each':len(a),'positive_progress_updates':sum(0<e['reward']<1 for e in b)})
    method_rows=[]
    for m in methods:
        group=[r for r in per_task if r['method']==m]
        calls=sum(r['calls'] for r in group)
        tokens=sum(r['actual_tokens'] for r in group)
        solved=sum(r['hidden_solved'] for r in group)
        method_rows.append({'method':m,'hidden_solved':solved,'tasks':5,'hidden_success_rate':solved/5,
                            'repair_full_pass_tasks':sum(r['repair_fraction']==1 for r in group),
                            'calls':calls,'actual_tokens':tokens,'tokens_per_hidden_success':tokens/solved if solved else None,
                            'call_auc':next(r['normalized_call_auc'] for r in read_json(out/'auc.json') if r['method']==m)})
    result={'recorded':now(),'scope':'Measured development pilot; five tasks, one seed, three methods',
            'selected_trials':15,'selected_requests':sum(r['calls'] for r in per_task),
            'selected_actual_tokens':sum(r['actual_tokens'] for r in per_task),'selected_unknown_usage':0,
            'hidden_checkpoints':150,'hidden_test_executions':750,'methods':method_rows,
            'trace_comparisons':comparisons,'source_campaign_costs':source_costs,
            'all_pilot_requests':sum(r['requests'] for r in source_costs),
            'all_pilot_known_tokens':sum(r['known_actual_tokens'] for r in source_costs),
            'all_pilot_unknown_usage_requests':sum(r['unknown_usage_requests'] for r in source_costs),
            'search_seal':frozen['seal_hash'],'evaluation_version':evaluated['version'],
            'composition':'runs/viva_complete_pilot/composition.json',
            'limitations':['Five development tasks and one seed; not the planned final study',
                           'Five hidden tests per task; passing them does not prove full task correctness',
                           'Two REx returns pass hidden suites while still failing some repair tests',
                           'No progress-only/cost-only ablations; no improvement over baseline REx observed',
                           'All-method affected-task rerun selected by a rule fixed before replacement inference/hidden evaluation',
                           'Original unknown usage remains in full-work accounting; selected costs are not total project costs']}
    write_json(out/'findings.json',result)
    csv_file(out/'method_results.csv',method_rows)
    csv_file(out/'per_task_results.csv',per_task)
    csv_file(out/'work_accounting.csv',source_costs)
    write_json(out/'mechanism_diagnostics.json',comparisons)
    plt.rcParams.update({'font.family':'DejaVu Sans','axes.spines.top':False,'axes.spines.right':False,'font.size':11})
    fig,ax=plt.subplots(figsize=(9,5))
    bars=ax.bar([labels[m] for m in methods],[r['hidden_solved'] for r in method_rows],color=[palette[m] for m in methods],width=.58)
    for bar,row in zip(bars,method_rows):
        ax.text(bar.get_x()+bar.get_width()/2,row['hidden_solved']+.12,f'{row["hidden_solved"]}/5 ({row["hidden_success_rate"]:.0%})',ha='center',weight='bold')
    ax.set(ylim=(0,5.5),yticks=range(6),ylabel='Tasks passing all five hidden tests',
           title='Hidden-test success at up to eight model calls\nFive paired development tasks | one seed')
    ax.grid(axis='y',alpha=.15)
    fig.tight_layout()
    fig.savefig(out/'hidden_success_comparison.png',dpi=180)
    plt.close(fig)
    matrix=np.array([[next(r['hidden_tests_passed'] for r in per_task if r['task']==task and r['method']==m) for m in methods] for task in tasks])
    fig,ax=plt.subplots(figsize=(9,5))
    ax.imshow(matrix,cmap='YlGnBu',vmin=0,vmax=5,aspect='auto')
    ax.set_xticks(range(3),[labels[m] for m in methods])
    ax.set_yticks(range(5),tasks)
    for i in range(5):
        for j in range(3):
            ax.text(j,i,f'{matrix[i,j]}/5',ha='center',va='center',color='white' if matrix[i,j]>=3 else '#173046',weight='bold')
    ax.set_title('Hidden tests passed by the repair-selected program')
    fig.tight_layout()
    fig.savefig(out/'per_task_hidden.png',dpi=180)
    plt.close(fig)
    # Re-render the existing comparison with a precise title; this is not a component ablation.
    fig,ax=plt.subplots(figsize=(8,5))
    ax.bar([labels[m] for m in methods[1:]],[r['hidden_success_rate'] for r in method_rows[1:]],color=[palette[m] for m in methods[1:]])
    ax.set(ylim=(0,1.05),ylabel='Returned-program hidden success',title='Baseline REx versus combined extension\nFive development tasks | one seed | eight nominal calls')
    fig.tight_layout()
    for suffix in ('png','svg'):
        fig.savefig(out/f'ablation.{suffix}',dpi=180,metadata={'Date':None} if suffix=='svg' else None)
    fig.savefig(out/'baseline_vs_extension.png',dpi=180)
    plt.close(fig)
    # Matching curves remain visually distinguishable with a thick baseline and dashed extension.
    for axis in ('calls','tokens'):
        fig,ax=plt.subplots(figsize=(9,5))
        for m in methods:
            values=sorted([r for r in summary if r['axis']==axis and r['method']==m],key=lambda r:r['budget'])
            ax.plot([r['budget'] for r in values],[r['success'] for r in values],label=labels[m],color=palette[m],
                    linewidth=3.5 if m=='rex' else 1.8,linestyle='--' if m=='rex_progress_cost' else '-',
                    marker='x' if m=='rex_progress_cost' else 'o')
            ax.fill_between([r['budget'] for r in values],[r['ci_low'] for r in values],[r['ci_high'] for r in values],color=palette[m],alpha=.07)
        ax.set(xlabel='Completed model calls' if axis=='calls' else 'Actual tokens: completed-generation prefixes',
               ylabel='Returned-program hidden success',ylim=(-.02,1.02),
               title='Hidden success versus inference budget\nFive paired development tasks | one seed | descriptive task-bootstrap intervals')
        ax.legend(fontsize=9)
        ax.grid(alpha=.15)
        fig.tight_layout()
        for suffix in ('png','svg'):
            fig.savefig(out/f'success_vs_{axis}.{suffix}',dpi=180,metadata={'Date':None} if suffix=='svg' else None)
        plt.close(fig)
    report='''# Completed development pilot

The combined progress/cost implementation and baseline REx each passed every hidden test on 4/5 development tasks (80%). Independent resampling did so on 1/5 tasks (20%). Both REx variants used 34 model calls versus resampling's 40 (15% fewer calls). Each REx variant consumed 27,247 tokens versus resampling's 25,819 (+5.5%); fewer calls did not mean fewer total tokens.

This supports a positive measured comparison for repair-based search against resampling in this small setting. It does not show an additional gain from the proposed combined extension over baseline REx: the two policies had identical selected branches, generated code sequences and actual token costs on all five tasks. The modified policy received two positive partial-progress updates without changing those selections.

## Measurement

Five development tasks x three methods x one seed = 15 complete selected trials. The model was frozen Qwen2.5-Coder 7B Q4_K_M on RTX 4060 Laptop via Ollama Vulkan. Settings: C=20, eta=0.5, gamma=0.5; eight nominal calls, integer checkpoints 1..8 and completed-prefix token checkpoints 1024/2048. The model, prompts, task bytes, parser and judge settings were shared. There was no model training.

Search saw only repair feedback. The returned program was fixed by repair score before hidden judging. The sealed analysis view has no missing or censored checkpoints and no unknown selected usage. All 150 hidden checkpoint evaluations (750 individual tests) completed without infrastructure errors.

## Provenance and accounting

One original response was lost during interruption. A rule fixed before replacement inference and hidden evaluation reran the affected problem for all three methods, irrespective of outcomes. The analysis uses those three fresh trials and twelve unaffected originals. Source experiment IDs, raw responses and hashes are preserved in `runs/viva_complete_pilot/composition.json`; originals were not overwritten.

Selected comparison: 108 requests and 80,313 actual tokens. Both GPU source campaigns, including discarded work: 131 requests, 101,706 known tokens and one unknown-usage request. The separately preserved CPU campaign adds 18 requests and 16,103 tokens. All pilot work therefore totals 149 requests and 117,809 known tokens plus the unresolved request's usage. Setup, smoke, reference audits and hidden judging are separate. These known-token sums are not an exact total project cost.

## Interpretation limits

This is a five-task, one-seed development pilot, not the planned final study or an official APPS score. There are only five hidden tests per task. Two returned REx programs pass all hidden cases while still failing some repair cases, so 80% hidden-suite success is not proof of full program correctness. Report both suites in `per_task_results.csv`.

Paired task-bootstrap intervals are descriptive with n=5. The zero-width extension-minus-REx interval arises from identical observed outcomes and does not establish population equivalence. Progress-only and cost-only ablations were not run. Strong priors, sparse feedback and the short call budget are plausible explanations for unchanged choices, not isolated causal findings.

## Files

- `method_results.csv`: success, requests, tokens and normalized call AUC.
- `per_task_results.csv`: hidden and repair fractions for every selected trial.
- `summary.csv`: full call/token checkpoints and bootstrap intervals.
- `findings.json`: machine-readable verified results and accounting.
- `hidden_success_comparison.png`, `per_task_hidden.png`, `success_vs_calls.png`, `success_vs_tokens.png`: scientific graphs.
- `mechanism_diagnostics.json`: direct trace comparison between baseline and extension.
- `work_accounting.csv`: full source campaign spend, including discarded and unknown work.
- `replay.html`, `replay_success.html`, `replay_loss.html`: inert recorded traces.

Regenerate standard analysis with `rexbench report --experiment runs/viva_complete_pilot --out reports/development_pilot_final`, then run `.venv/Scripts/python.exe tools/summarize_completed_pilot.py` to restore these supplemental findings and graph labels. Neither step invokes the model or reruns hidden judging.
'''
    (out/'FINDINGS.md').write_text(report,encoding='utf-8')
    print(json.dumps({'out':str(out),'methods':method_rows,'selected_calls':result['selected_requests']}))


if __name__=='__main__':
    summarize()
