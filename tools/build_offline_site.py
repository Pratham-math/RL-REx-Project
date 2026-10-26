"""Build a self-contained, file:// compatible research website from saved evidence."""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path
import re
import shutil
import sqlite3
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'website'
REPORT = ROOT / 'reports/development_pilot_final'
METHODS = ['resample', 'rex', 'rex_progress_cost']
LABELS = {'resample': 'Resampling', 'rex': 'REx', 'rex_progress_cost': 'Progress + cost'}


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def esc(value):
    return html.escape(str(value), quote=True)


def read_csv(path):
    with Path(path).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def test_record(path):
    suites=list(ET.parse(path).getroot().iter('testsuite'))
    counts={key:sum(int(s.attrib.get(key,0)) for s in suites) for key in ('tests','failures','errors','skipped')}
    counts['passed']=counts['tests']-counts['failures']-counts['errors']-counts['skipped']
    counts['timestamp']=suites[0].attrib.get('timestamp','')
    counts['seconds']=sum(float(s.attrib.get('time',0)) for s in suites)
    counts['cases']=[{'group':t.attrib.get('classname',''),'name':t.attrib.get('name',''),
                     'status':'failed' if t.find('failure') is not None or t.find('error') is not None else 'skipped' if t.find('skipped') is not None else 'passed'}
                    for s in suites for t in s.findall('testcase')]
    return counts


def icon(name):
    paths={'arrow':'<path d="M5 12h14m-6-6 6 6-6 6"/>',
           'file':'<path d="M14 3H6v18h12V7zM14 3v5h5M9 12h6M9 16h6"/>',
           'check':'<path d="m5 12 4 4L19 6"/>',
           'menu':'<path d="M4 6h16M4 12h16M4 18h16"/>',
           'download':'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>'}
    return f'<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">{paths[name]}</svg>'


NAV=[('index.html','Overview','01'),('methods.html','Methods','02'),('results.html','Results','03'),
     ('testing.html','Testing','04'),('progress.html','Progress','05'),('files.html','Files & evidence','06')]


def page(filename,title,subtitle,body,section=''):
    marker_number=0
    def unique_markers(match):
        nonlocal marker_number
        marker_number+=1
        marker=f'arrow-{marker_number}'
        return match.group(0).replace('id="arrow"',f'id="{marker}"').replace('url(#arrow)',f'url(#{marker})')
    body=re.sub(r'<svg class="flowchart".*?</svg>',unique_markers,body,flags=re.S)
    navigation=''.join(f'<a href="{href}" class="nav-link {"active" if href==filename else ""}"'+
                       (' aria-current="page"' if href==filename else '')+
                       f'><span>{num}</span>{label}</a>' for href,label,num in NAV)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Code-repair project: methods, measured pilot results, testing and implementation progress.">
<meta name="color-scheme" content="light"><title>{esc(title)} · Code repair</title>
<link rel="icon" href="assets/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="assets/style.css">
<script src="assets/data.js" defer></script><script src="assets/site.js" defer></script></head>
<body data-page="{filename}"><a class="skip-link" href="#main">Skip to content</a>
<header class="mobile-header"><a href="index.html">Code repair <span>/ project notes</span></a><button type="button" id="menu-button" aria-expanded="false" aria-controls="sidebar" aria-label="Open navigation">{icon('menu')}</button></header>
<aside class="sidebar" id="sidebar"><a class="brand" href="index.html"><span class="brand-mark" aria-hidden="true">r<span>↗</span></span><span>Code repair<small>Project notes</small></span></a>
<nav aria-label="Main navigation">{navigation}</nav><div class="sidebar-bottom"><span class="status-dot"></span> Development pilot complete<small>Updated 26 October 2026<br>Local, offline copy</small></div></aside>
<main id="main"><div class="topline"><span>CODE REPAIR / {esc(section or title).upper()}</span><span class="topline-right">Five problems. Three methods.</span></div>
{f'<div class="page-heading"><h1>{esc(title)}</h1><p>{subtitle}</p></div>' if filename!='index.html' else ''}{body}
<footer><span>Code repair with bandit search</span><span>Development pilot · 26 October 2026</span></footer></main>
<dialog id="image-dialog" aria-label="Enlarged figure"><button class="dialog-close" type="button" aria-label="Close figure">Close ×</button><img alt=""><p></p></dialog>
</body></html>'''


def evidence_link(filename,label,download=False):
    return f'<a class="text-link" href="evidence/{filename}"'+(' download' if download else '')+f'>{esc(label)} {icon("download" if download else "arrow")}</a>'


def figure(filename,caption,alt=None):
    return f'<figure><button type="button" class="figure-button" data-zoom aria-label="Enlarge {esc(alt or caption)}"><img src="assets/figures/{filename}" alt="{esc(alt or caption)}" loading="lazy"></button><figcaption>{caption}<span>Click to enlarge</span></figcaption></figure>'


def section_title(number,title,extra=''):
    return f'<div class="section-title"><span>{number}</span><h2>{title}</h2>{extra}</div>'


def stat_row(items):
    return '<div class="stat-row">'+''.join(f'<div><strong>{value}</strong><span>{label}</span></div>' for value,label in items)+'</div>'


def svg_node(x,y,w,h,lines,accent=False):
    lines=lines if isinstance(lines,list) else [lines]
    start=y+h/2-(len(lines)-1)*9+5
    return f'<g><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" class="{"node-accent" if accent else "node"}"/>'+''.join(f'<text x="{x+w/2}" y="{start+18*i}" text-anchor="middle">{esc(line)}</text>' for i,line in enumerate(lines))+'</g>'


def svg_diamond(cx,cy,w,h,lines):
    return f'<path d="M{cx-w/2} {cy} L{cx} {cy-h/2} L{cx+w/2} {cy} L{cx} {cy+h/2} Z" class="decision"/>'+''.join(f'<text x="{cx}" y="{cy-(len(lines)-1)*9+5+i*18}" text-anchor="middle">{esc(line)}</text>' for i,line in enumerate(lines))


def svg_arrow(d,label=None,x=0,y=0):
    return f'<path d="{d}" class="flow-arrow" marker-end="url(#arrow)"/>'+ (f'<text x="{x}" y="{y}" class="edge-label">{esc(label)}</text>' if label else '')


def svg_start(title,w,h):
    return f'<svg class="flowchart" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}"><title>{esc(title)}</title><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#526f69"/></marker></defs>'


def pipeline():
    stages=[('Frozen tasks','Repair / hidden split'),('Search','Generate, test, repair'),('Seal','Fix the returned code'),('Hidden evaluation','No feedback to search'),('Analysis','Paired tasks and costs')]
    svg=svg_start('Evaluation pipeline: frozen tasks to search, sealing, hidden evaluation and analysis',1080,160)
    for i,(title,detail) in enumerate(stages):
        x=10+i*215
        svg+=svg_node(x,35,190,80,[title,detail],i==2)
        if i<4:
            svg+=svg_arrow(f'M{x+190} 75H{x+212}')
    return '<div class="diagram-shell compact">'+svg+'</svg></div>'


def search_flow(method):
    modified=method=='rex_progress_cost'
    if method=='resample':
        s=svg_start('Resampling flow: generate fresh programs, test them, keep the best until success or budget coverage',920,510)
        s+=svg_node(265,20,300,58,['Problem statement + root prompt'])
        s+=svg_node(265,120,300,58,['Generate a fresh program'])
        s+=svg_node(265,220,300,58,['Parse and run repair tests'])
        s+=svg_diamond(415,355,230,100,['All repair tests','pass?'])
        s+=svg_node(665,325,220,60,['Return program'],True)
        s+=svg_node(20,325,230,60,['Keep best repair score'])
        s+=svg_arrow('M415 78V118')+svg_arrow('M415 178V218')+svg_arrow('M415 278V303')
        s+=svg_arrow('M530 355H663','Yes',575,343)+svg_arrow('M300 355H252','No',264,342)
        s+=svg_arrow('M135 325V149H263','Next fresh attempt',30,205)
        s+='<text x="25" y="440" class="diagram-note">Stop at target budget coverage; return the best eligible completed program.</text><text x="25" y="466" class="diagram-note">This method never selects an earlier program for repair. Invalid outputs still consume budget.</text></svg>'
        return '<div class="diagram-shell">'+s+'</div>'
    s=svg_start(('Progress- and cost-aware REx' if modified else 'Baseline REx')+' search loop',1000,780)
    s+=svg_node(305,20,380,58,['Candidate bank: root + saved programs'])
    s+=svg_node(305,115,380,65,['Sample from each arm’s Beta distribution', 'Divide by estimated cost^0.5' if modified else 'Choose the largest sample'],modified)
    s+=svg_diamond(495,255,200,94,['Root chosen?'])
    s+=svg_node(85,340,300,62,['Generate a fresh program'])
    s+=svg_node(610,340,300,62,['Repair the selected program','using one failed repair case'])
    s+=svg_node(305,455,380,58,['Parse code + execute repair tests'])
    s+=svg_diamond(495,585,250,105,['Full repair pass?'])
    s+=svg_node(745,553,220,64,['Save program and stop'],True)
    s+=svg_node(295,680,400,68,['Add the new arm; keep the best eligible code', 'Fractional progress update to parent' if modified else 'Incomplete repair: increase parent beta'],modified)
    s+=svg_arrow('M495 78V113')+svg_arrow('M495 180V206')
    s+=svg_arrow('M395 255H235V338','Yes',250,243)+svg_arrow('M595 255H760V338','No',665,243)
    s+=svg_arrow('M235 402V484H303')+svg_arrow('M760 402V484H687')
    s+=svg_arrow('M495 513V530')+svg_arrow('M620 585H743','Yes',670,572)
    s+=svg_arrow('M495 637V678','No',510,660)
    s+=svg_arrow('M295 714H45V147H303','Continue while coverage/budget permits',65,660)
    s+='<text x="730" y="708" class="diagram-note">Budget reached?</text><text x="730" y="732" class="diagram-note">Return best repair score.</text></svg>'
    return '<div class="diagram-shell">'+s+'</div>'


def build():
    (SITE/'assets/figures').mkdir(parents=True,exist_ok=True)
    (SITE/'evidence').mkdir(exist_ok=True)
    facts=load(REPORT/'findings.json')
    per_task=read_csv(REPORT/'per_task_results.csv')
    summary=load(REPORT/'summary.json')
    evaluation_path=next((ROOT/'runs/viva_complete_pilot/evaluations').glob('*/evaluation.json'))
    evaluation=load(evaluation_path)
    offline=test_record(ROOT/'reports/verification/site_current_offline.xml')
    docker=test_record(ROOT/'reports/verification/site_current_docker.xml')
    live=test_record(ROOT/'reports/verification/live_model_installed.xml')
    assert offline['failures']==offline['errors']==offline['skipped']==0
    assert docker['failures']==docker['errors']==docker['skipped']==0
    assert facts['selected_trials']==15 and facts['hidden_test_executions']==750
    data={'facts':facts,'summary':summary,'perTask':per_task,'evaluationRows':evaluation['rows'],
          'verification':{'offline':offline,'docker':docker,'live':live}}
    (SITE/'assets/data.js').write_text('window.RESEARCH_DATA = '+json.dumps(data,ensure_ascii=True)+';\n',encoding='utf-8')
    (SITE/'assets/favicon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#203b34"/><text x="20" y="47" font-family="Georgia" font-size="50" fill="#faf7ef">r</text></svg>',encoding='utf-8')
    figures=['hidden_success_comparison.png','per_task_hidden.png','success_vs_calls.png','success_vs_tokens.png',
             'baseline_vs_extension.png','cost_estimator.png']
    for name in figures:
        shutil.copy2(REPORT/name,SITE/'assets/figures'/name)
    records={name:REPORT/name for name in ['findings.json','method_results.csv','per_task_results.csv','summary.csv','summary.json','auc.csv',
              'coverage.json','diagnostics.json','mechanism_diagnostics.json','work_accounting.csv','FINDINGS.md','replay.html','replay_success.html','replay_loss.html']}
    records.update({'offline-tests.xml':ROOT/'reports/verification/site_current_offline.xml',
                    'docker-tests.xml':ROOT/'reports/verification/site_current_docker.xml',
                    'live-model-test.xml':ROOT/'reports/verification/live_model_installed.xml',
                    'benchmark-checks.json':ROOT/'reports/verification/completed_pilot_checks.json',
                    'scheduler-parity.json':ROOT/'reports/parity.json',
                    'reference-audit-summary.json':ROOT/'reports/development_audit_summary.json',
                    'resume-noop.json':ROOT/'reports/verification/live_resume_noop.json',
                    'selection-protocol.json':ROOT/'docs/viva_selection_protocol.json',
                    'composition.json':ROOT/'runs/viva_complete_pilot/composition.json',
                    'seal.json':ROOT/'runs/viva_complete_pilot/seal.json',
                    'model-and-runner.json':ROOT/'runs/viva_complete_pilot/resolved_config.json',
                    'policy.py':ROOT/'src/rexbench/policies/__init__.py',
                    'cost_estimator.py':ROOT/'src/rexbench/budgets.py'})
    for name,source in records.items():
        shutil.copy2(source,SITE/'evidence'/name)
    with zipfile.ZipFile(SITE/'evidence/sealed-benchmark.zip','w',zipfile.ZIP_DEFLATED) as archive:
        source=ROOT/'runs/viva_complete_pilot'
        for path in sorted(source.rglob('*')):
            if path.is_file() and path.name not in {'.writer.lock','state.sqlite-wal','state.sqlite-shm','state.sqlite'}:
                archive.write(path,Path('analysis')/path.relative_to(source))
        # SQLite backup includes any checkpointed WAL state and leaves the source unchanged.
        temp=SITE/'evidence/.measurement.sqlite'
        connection=sqlite3.connect(f'file:{(source/"state.sqlite").as_posix()}?mode=ro',uri=True)
        target=sqlite3.connect(temp)
        connection.backup(target)
        target.close()
        connection.close()
        archive.write(temp,'analysis/state.sqlite')
        temp.unlink()

    overview=f'''
<section class="overview-hero"><div><p class="eyebrow">THE PROJECT</p><h1>Code repair with<br>a search budget.</h1><p class="lead">We built a local code-repair system and compared three ways of using the same language model.</p><p class="hero-detail">The work focuses on a simple choice: generate another program, or try to improve one we already have.</p><a href="methods.html" class="button">How it works {icon('arrow')}</a></div>
<div class="result-note"><div class="note-heading"><span>Latest pilot result</span><span>8-call budget</span></div><h2>Hidden-test success</h2><p>Programs that passed every hidden test.</p><div class="mini-bar"><div><span>Resampling</span><b>20%</b></div><i style="--bar:20%;--color:#929a9b"></i></div><div class="mini-bar"><div><span>REx</span><b>80%</b></div><i style="--bar:80%;--color:#5d7d9b"></i></div><div class="mini-bar"><div><span>Progress + cost</span><b>80%</b></div><i style="--bar:80%;--color:#2e6854"></i></div><small>5 development problems · 1 seed<br>The extension matched baseline REx in this pilot.</small><a class="text-link" href="results.html">See the full comparison {icon('arrow')}</a></div></section>
{stat_row([('5','programming problems'),('3','search methods'),('15','completed trials'),('108','model requests')])}
<section>{section_title('01','What we changed')}<div class="two-col intro-columns"><div><h3>Progress feedback</h3><p>An incomplete repair can still improve a program. We added a small reward for a positive change in its repair-test score.</p></div><div><h3>Estimated token cost</h3><p>We adjusted the selection priority using the estimated cost of the next request. Actual spending is measured separately from the model’s token counts.</p></div></div><p class="section-note">These changes affect candidate selection. The language model’s weights stay fixed.</p></section>
<section>{section_title('02','From problem to result')} {pipeline()}<p class="section-note">Repair tests guide the search. Hidden tests are used only after the returned programs have been fixed and sealed.</p></section>
<section>{section_title('03','The work, in detail')}<div class="reading-list"><a href="methods.html"><span class="list-number">02</span><div><h3>Methods</h3><p>REx, the two modifications, and the complete search loop.</p></div>{icon('arrow')}</a><a href="results.html"><span class="list-number">03</span><div><h3>Results</h3><p>Success rates, per-problem scores, request counts and tokens.</p></div>{icon('arrow')}</a><a href="testing.html"><span class="list-number">04</span><div><h3>Testing</h3><p>Test reports, isolated execution and benchmark checks.</p></div>{icon('arrow')}</a><a href="progress.html"><span class="list-number">05</span><div><h3>Progress</h3><p>What has been completed and what remains to be measured.</p></div>{icon('arrow')}</a></div></section>
<aside class="plain-note"><strong>About this result</strong><p>This is a small development pilot, not a full APPS benchmark. It shows a clear difference against resampling, while the proposed extension and baseline REx produced the same result. The results page includes the limits of this comparison.</p></aside>'''

    method_tabs=''.join(f'<button type="button" role="tab" id="tab-{m}" aria-controls="panel-{m}" aria-selected="{"true" if m=="rex" else "false"}" tabindex="{0 if m=="rex" else -1}" data-method="{m}">{LABELS[m]}</button>' for m in METHODS)
    method_panels=''
    descriptions={'resample':'Always generate from the root prompt. Test each completed program and retain the best repair score. There is no branch refinement.',
                  'rex':'Maintain a bank of programs. Sample from a Beta distribution for each eligible arm, then generate from the root or repair a selected program.',
                  'rex_progress_cost':'Use the same candidate bank and model. Add positive partial-progress credit to the update and normalize selection by estimated token cost.'}
    for method in METHODS:
        method_panels+=f'<div role="tabpanel" id="panel-{method}" aria-labelledby="tab-{method}"'+(' hidden' if method!='rex' else '')+f'><p class="diagram-intro">{descriptions[method]}</p>{search_flow(method)}</div>'
    methods=f'''
<section class="opening-note"><p>A program is an <strong>arm</strong>. Repair-test pass fraction is its score, <strong>h</strong>. The root is the option to generate a fresh program. REx decides which arm to try next.</p><dl class="setup-inline"><div><dt>Model</dt><dd>Qwen2.5-Coder 7B</dd></div><div><dt>Prior strength C</dt><dd>20</dd></div><div><dt>Progress weight η</dt><dd>0.5</dd></div><div><dt>Cost exponent γ</dt><dd>0.5</dd></div></dl></section>
<section>{section_title('01','The three search methods')}<div class="tabs" role="tablist" aria-label="Search method">{method_tabs}</div>{method_panels}</section>
<section>{section_title('02','The two changes')}<div class="change-block"><span class="change-number">A</span><div><h3>Give credit to an improvement</h3><p>Baseline REx gives an incomplete repair no success credit. The extension gives fractional credit when a non-root repair improves its parent without yet passing every repair test.</p><div class="formula">r = η × max(0, h<sub>child</sub> − h<sub>parent</sub>)<br><span>α ← α + r &nbsp;&nbsp; β ← β + (1 − r)</span></div><p class="small">Root partial generations receive zero progress credit. Full repair success is saved and stops before updating the parent, following the upstream terminal rule.</p></div></div>
<div class="change-block"><span class="change-number">B</span><div><h3>Account for the next request’s cost</h3><p>Baseline REx selects the largest Beta sample. The extension divides that sample by estimated tokens raised to γ.</p><div class="formula">priority = θ / max(1, estimated tokens)<sup>γ</sup><br><span>θ ~ Beta(α, β) &nbsp;&nbsp; α = 1 + C·h &nbsp;&nbsp; β = 1 + C·(1 − h)</span></div><p class="small">The estimate starts at prompt characters / 4 + 512 output tokens, then adapts using past requests within that trial. Actual reported costs use backend token counts.</p></div></div></section>
<section>{section_title('03','A small worked example','<span class="section-tag">Illustration, not benchmark data</span>')}<div class="example-grid"><div><h3>Partial-progress update</h3><label for="parent-score">Parent repair score <output id="parent-output">0.30</output></label><input id="parent-score" type="range" min="0" max="0.9" step="0.1" value="0.3"><label for="child-score">Child repair score <output id="child-output">0.70</output></label><input id="child-score" type="range" min="0" max="0.9" step="0.1" value="0.7"><div class="example-answer"><span>Progress reward, η = 0.5</span><strong id="progress-reward">0.20</strong></div><p class="small">Both scores stay below 1 here so the example uses the nonterminal update. A lower or equal child score earns zero progress credit.</p></div><div><h3>A different selection priority</h3><table class="simple-table"><thead><tr><th>Arm</th><th>Beta sample</th><th>Estimated tokens</th></tr></thead><tbody><tr><td>A</td><td>0.60</td><td>1,000</td></tr><tr><td>B</td><td>0.70</td><td>4,000</td></tr></tbody></table><p>Baseline REx chooses <b>B</b>, since 0.70 is larger.</p><p>With γ = 0.5, the priorities become <b>0.0190</b> for A and <b>0.0111</b> for B. The extension chooses <b>A</b>.</p><p class="small">The samples and costs above are chosen to explain the formula. This is not a measured token saving.</p></div></div></section>
<section>{section_title('04','Shared rules')}<div class="prose"><ul><li>All methods use the same model, prompts, parser, repair tests and Docker limits.</li><li>Repair feedback includes one independently selected failing test from the current candidate.</li><li>The returned solution is the completed eligible program with the highest repair score. Earlier creation breaks ties.</li><li>Malformed and duplicate generations still consume calls and tokens.</li><li>Full repair success stops search. Otherwise the pilot targets eight calls and token coverage; the per-trial extension ceiling is sixteen calls.</li><li>Hidden results never select, rank or repair a program during search.</li></ul></div><details><summary>Implementation and original source</summary><p>The REx scheduler is reproduced from the pinned upstream implementation. The controlled APPS wrapper has documented differences, including one arm per generation and explicit charging of invalid outputs. Progress shaping is a heuristic pseudo-count update, without an exact-posterior or optimality guarantee.</p><div class="inline-links">{evidence_link('policy.py','Selection and update code',True)}{evidence_link('cost_estimator.py','Cost estimator',True)}<a class="text-link" href="https://arxiv.org/abs/2405.17503" target="_blank" rel="noreferrer">Original REx paper ↗</a></div></details></section>'''

    final_table=''.join(f'<tr><th scope="row">{LABELS[r["method"]]}</th><td><b>{r["hidden_solved"]}/5</b> <span class="muted">({r["hidden_success_rate"]:.0%})</span></td><td>{r["calls"]}</td><td>{r["actual_tokens"]:,}</td><td>{r["tokens_per_hidden_success"]:,.0f}</td></tr>' for r in facts['methods'])
    task_rows=''
    counts={'test/0107':6,'test/0136':5,'test/0146':3,'test/0163':4,'test/0173':3}
    for r in sorted(per_task,key=lambda r:(r['task'],METHODS.index(r['method']))):
        passed=round(float(r['repair_fraction'])*counts[r['task']])
        task_rows+=f'<tr data-trial-method="{r["method"]}"><th scope="row"><code>{r["task"]}</code></th><td>{LABELS[r["method"]]}</td><td>{passed}/{counts[r["task"]]}</td><td><span class="score {"full" if r["hidden_solved"]=="True" else "partial"}">{r["hidden_tests_passed"]}/5</span></td><td>{r["calls"]}</td><td>{int(r["actual_tokens"]):,}</td></tr>'
    results=f'''
<section class="result-summary"><p class="eyebrow">AT UP TO EIGHT MODEL CALLS</p><h2>Four problems solved with repair search.<br>One with repeated sampling.</h2><p>Both REx variants passed every hidden test on 4 of 5 problems. The proposed extension matched baseline REx.</p></section>
<section><div class="table-wrap"><table><caption>Final pilot comparison. Same five tasks and seed 0.</caption><thead><tr><th>Method</th><th>Hidden success</th><th>Calls</th><th>Actual tokens</th><th>Tokens / hidden success</th></tr></thead><tbody>{final_table}</tbody></table></div><div class="result-footnotes"><p><strong>15% fewer calls</strong> for both REx variants versus resampling.</p><p><strong>5.5% more total tokens.</strong> Fewer calls did not mean fewer tokens.</p></div></section>
<section>{section_title('01','Explore the recorded checkpoints')}<div class="chart-controls"><label for="budget-axis">Budget type<select id="budget-axis"><option value="calls">Model calls</option><option value="tokens">Actual token threshold</option></select></label><label for="budget-value">Checkpoint<select id="budget-value">{''.join(f'<option value="{i}" {"selected" if i==8 else ""}>{i} calls</option>' for i in range(1,9))}</select></label><p id="checkpoint-description">Final checkpoint: eight calls. Each solved problem contributes 20 percentage points.</p></div><div id="checkpoint-chart" class="checkpoint-chart" role="img" aria-label="Recorded success at the selected checkpoint"></div><div class="table-wrap"><table class="checkpoint-table"><thead><tr><th>Method</th><th>Hidden success</th><th>Prefix calls</th><th>Prefix tokens</th></tr></thead><tbody id="checkpoint-table"></tbody></table></div><p class="section-note">Every value comes from the saved evaluation. Token checkpoints use only completed generations at or below the threshold; a crossing request is still charged to campaign spend.</p></section>
<section>{section_title('02','Per-problem results','<label class="filter-label" for="method-filter">Method <select id="method-filter"><option value="all">All methods</option>'+''.join(f'<option value="{m}">{LABELS[m]}</option>' for m in METHODS)+'</select></label>')}<div class="table-wrap"><table id="task-table"><caption>Repair tests guided the return; hidden tests were evaluated afterward.</caption><thead><tr><th>Problem</th><th>Method</th><th>Repair tests</th><th>Hidden tests</th><th>Calls</th><th>Tokens</th></tr></thead><tbody>{task_rows}</tbody></table></div><p class="small">Two REx returns pass all five hidden tests while still failing some repair cases. Passing the small hidden suite does not prove correctness on every possible input.</p></section>
<section>{section_title('03','Curves and diagnostics')}<div class="figure-grid">{figure('success_vs_calls.png','Success across the eight integer call checkpoints.')}{figure('success_vs_tokens.png','Success at the two completed-generation token thresholds.')}</div>{figure('per_task_hidden.png','Hidden tests passed by each repair-selected return.')}</section>
<section>{section_title('04','What the traces show')}<div class="two-col"><div><h3>The extension matched REx</h3><p>Across all five tasks, the two policies selected the same parents and generated identical code sequences: 34 generations each. Actual token totals also match.</p><p>The modified policy received two positive partial-progress updates. Those updates and the cost normalization did not change the selected trajectories here.</p></div><div class="scope-note"><h3>How far this result goes</h3><ul><li>Five development problems and one seed.</li><li>Three to six repair tests, five hidden tests per problem.</li><li>No separate progress-only or cost-only runs.</li><li>The larger held-out study has not been run.</li></ul></div></div><p class="small">Task-bootstrap intervals are descriptive at this sample size. An identical observed outcome and a zero-width paired interval do not establish population equivalence.</p></section>
<section>{section_title('05','Comparison cost and total work')}<div class="table-wrap"><table><thead><tr><th>Scope</th><th>Requests</th><th>Known tokens</th><th>Unknown usage</th></tr></thead><tbody><tr><th>Selected 15-trial comparison</th><td>108</td><td>80,313</td><td>0</td></tr><tr><th>All GPU pilot work, including discarded trials</th><td>131</td><td>101,706</td><td>1 request</td></tr><tr><th>Archived CPU pilot</th><td>18</td><td>16,103</td><td>0</td></tr><tr><th>All pilot work</th><td>149</td><td>117,809</td><td>1 request</td></tr></tbody></table></div><p class="small">The full-work known-token sum is not an exact total while the interrupted request remains unresolved. Setup, smoke tests, reference audits and hidden judging are separate work.</p><div class="inline-links">{evidence_link('method_results.csv','Download method results',True)}{evidence_link('per_task_results.csv','Download per-task results',True)}{evidence_link('work_accounting.csv','Full cost accounting',True)}</div></section>'''

    verification_rows=[('Offline suite',str(offline['passed'])+' passed','Unit and integration checks; excludes real Docker and live-model marks.','offline-tests.xml'),
                       ('Real Docker suite',str(docker['passed'])+' passed','Executed generated fixture programs in real isolated Linux containers.','docker-tests.xml'),
                       ('Live-model smoke','1 passed','Recorded local-model test from the installed model check. Not rerun for this webpage.','live-model-test.xml'),
                       ('Scheduler conformance','6 matched','Fake-domain trace comparisons against pinned upstream REx; not a model-quality benchmark.','scheduler-parity.json'),
                       ('Reference audit','92 executions','Vetted reference solutions tested across the five frozen repair/hidden suites.','reference-audit-summary.json'),
                       ('Pilot hidden evaluation','750 executions','150 checkpoints × five hidden tests; zero infrastructure errors.','benchmark-checks.json')]
    checks=''.join(f'<tr><th scope="row">{name}</th><td><span class="test-result">{status}</span></td><td>{detail}</td><td><a href="evidence/{record}" class="file-link">Record {icon("arrow")}</a></td></tr>' for name,status,detail,record in verification_rows)
    testing=f'''
{stat_row([(str(offline['passed']),'offline tests passed'),(str(docker['passed']),'real Docker tests passed'),('150','hidden checkpoints'),('0','evaluation infrastructure errors')])}
<section>{section_title('01','Recorded verification')}<p>The offline and Docker suites were rerun while preparing this site. The live-model smoke and reference audit are earlier recorded checks. These counts describe different kinds of testing; they are not added into a single benchmark score.</p><div class="table-wrap"><table class="verification-table"><thead><tr><th>Check</th><th>Result</th><th>What it establishes</th><th>Evidence</th></tr></thead><tbody>{checks}</tbody></table></div><p class="small">Latest offline run: {esc(offline['timestamp'][:19].replace('T',' '))}, {offline['seconds']:.1f}s. Latest Docker run: {esc(docker['timestamp'][:19].replace('T',' '))}, {docker['seconds']:.1f}s. No skipped tests in either run.</p></section>
<section>{section_title('02','How programs were tested')}<div class="two-col"><div><h3>Fresh container for every test</h3><ul><li>Linux runner image pinned by digest.</li><li>No network, non-root users and read-only source mount.</li><li>256 MiB memory limit, one CPU and process/output limits.</li><li>Compilation and execution are separate phases.</li><li>Expected output stays on the host.</li></ul></div><div><h3>Failure cases covered</h3><ul><li>Correct output and wrong answers.</li><li>Syntax errors and runtime exceptions.</li><li>CPU time, memory and output limits.</li><li>Process cleanup and fresh test state.</li><li>Cancellation and owner-scoped orphan cleanup.</li></ul></div></div><details><summary>Execution limits and model setup</summary><div class="table-wrap"><table class="simple-table"><tbody><tr><th>Model</th><td>Qwen2.5-Coder 7B, Q4_K_M</td></tr><tr><th>Runtime</th><td>Ollama 0.40.11, Vulkan, RTX 4060 Laptop</td></tr><tr><th>Context / output limit</th><td>16,384 / 2,048 tokens</td></tr><tr><th>Sampling temperature / seed</th><td>1.0 / 0</td></tr><tr><th>Program limits</th><td>2 CPU seconds, 5 seconds wall time per phase, 256 MiB</td></tr><tr><th>Scheduling</th><td>One worker; one model request at a time</td></tr></tbody></table></div>{evidence_link('model-and-runner.json','Exact resolved settings')}</details></section>
<section>{section_title('03','From saved response to hidden score')}{pipeline()}<div class="two-col"><div><h3>Durable request accounting</h3><p>Request intent is stored before dispatch. Raw responses are saved before parsing and judging. A missing response is marked unknown instead of being silently retried.</p><p>Completed resume was checked separately: two calls before and after, with no additional inference.</p>{evidence_link('resume-noop.json','Completed-resume check')}</div><div><h3>Sealed evaluation</h3><p>A seal binds the selected plan, resolved setup, task records, artifact hashes and logical database state. The evaluator checks the seal before and after hidden judging.</p><p>The 15-trial view has complete call/token coverage, no selected unknown usage and no censored checkpoints.</p>{evidence_link('coverage.json','Coverage record')}</div></div></section>
<section>{section_title('04','Inspect the test cases')}<div class="chart-controls"><label for="test-suite">Suite<select id="test-suite"><option value="docker">Real Docker tests</option><option value="offline">Offline tests</option></select></label><label class="search-field" for="test-search">Find a test<input id="test-search" type="search" placeholder="e.g. recovery, memory, policy"></label><p id="test-count" aria-live="polite"></p></div><div class="table-wrap test-table-wrap"><table><thead><tr><th>Test</th><th>Result</th></tr></thead><tbody id="test-cases"></tbody></table></div></section>
<section class="plain-note"><strong>What a passing test means here</strong><p>Fixture tests verify harness behavior. Reference checks verify the chosen suites against vetted solutions. The model benchmark measures returned-program success on five hidden cases per problem. Each is useful evidence for a different part of the work.</p></section>'''

    milestones=[('01','Source and contracts','Complete','Preserved the starter, pinned upstream REx, and defined task, request and result contracts.'),
                ('02','Dataset and reference audit','Complete','Selected five development tasks, separated repair and hidden cases, and completed the real reference audit.'),
                ('03','Runner and backend','Complete','Built the Docker judge, installed the local model, checked usage counts, and moved inference to the GPU.'),
                ('04','Search policies','Complete','Implemented resampling and REx, then added positive progress credit and token-cost normalization.'),
                ('05','Recovery and accounting','Complete','Recorded intent, responses and commits; added unknown-outcome handling and evidence-based reconciliation.'),
                ('06','Development pilot','Complete','Finished the all-method replacement task and assembled the fixed 15-trial analysis view.'),
                ('07','Hidden evaluation and analysis','Complete','Sealed the view, evaluated 750 hidden test executions, and generated paired summaries and traces.'),
                ('08','Larger held-out study','Not run','Planned: 30 tasks, six methods and three seeds. Data selection, frozen protocol and compute planning remain.')]
    timeline=''.join(f'<article class="milestone"><div class="milestone-number">{n}</div><div><div class="milestone-head"><h3>{title}</h3><span class="status {"pending" if status=="Not run" else ""}">{status}</span></div><p>{detail}</p></div></article>' for n,title,status,detail in milestones)
    progress=f'''
<section class="progress-intro"><p class="eyebrow">CURRENT POSITION</p><h2>The small pilot is complete.<br>The larger study is still ahead.</h2><p>The implementation, local verification and five-task comparison have recorded evidence. The planned final study has not been launched.</p></section>
<section>{section_title('01','Work completed')}<div class="timeline">{timeline}</div></section>
<section>{section_title('02','The interrupted task')}<div class="prose"><p>The first GPU campaign stopped during a request on <code>test/0146</code>. Its response was not saved, so that request remains unknown in the original record.</p><p>Before replacement inference and hidden evaluation, we fixed a rule: rerun <strong>that entire problem for all three methods</strong>, regardless of the outcomes. The comparison uses those three fresh trials and the twelve unaffected original trials.</p><p>The original runs were preserved. Source experiment IDs and checkpoint mappings are retained in the composition record. This was a replacement task run, not a claim that the lost response had been recovered.</p></div><div class="composition-strip"><div><strong>12</strong><span>unaffected original trials</span></div><span aria-hidden="true">+</span><div><strong>3</strong><span>fresh all-method trials</span></div><span aria-hidden="true">=</span><div><strong>15</strong><span>complete selected trials</span></div></div><div class="inline-links">{evidence_link('selection-protocol.json','Pre-evaluation selection rule')}{evidence_link('composition.json','Source mappings')}</div></section>
<section>{section_title('03','What to measure next')}<ol class="next-list"><li><h3>Separate the components</h3><p>Run progress-only and cost-only policies to identify their individual effects.</p></li><li><h3>Use more development tasks and seeds</h3><p>Test whether richer feedback and longer budgets produce different search trajectories.</p></li><li><h3>Freeze a final protocol</h3><p>Select settings on development data, then evaluate a separate held-out task set without retuning against its hidden scores.</p></li></ol></section>'''

    groups=[('Results and measurements',[
        ('FINDINGS.md','Comparison report','Measured findings, setup, provenance and interpretation limits.'),
        ('findings.json','Verified findings · JSON','Machine-readable counts, method results and full-work accounting.'),
        ('method_results.csv','Method results · CSV','Hidden success, calls, actual tokens and normalized call AUC.'),
        ('per_task_results.csv','Per-problem results · CSV','Repair and hidden scores for every selected trial.'),
        ('summary.csv','All checkpoints · CSV','Call/token checkpoints and descriptive bootstrap intervals.'),
        ('work_accounting.csv','Work accounting · CSV','Selected comparison and preserved source campaign costs.')]),
        ('Testing records',[
        ('offline-tests.xml','Offline suite · XML',f'{offline["passed"]} passed; current verification run.'),
        ('docker-tests.xml','Real Docker suite · XML',f'{docker["passed"]} passed; current real-container run.'),
        ('live-model-test.xml','Installed-model smoke · XML','Earlier recorded local-model verification; one passing test.'),
        ('scheduler-parity.json','Scheduler conformance · JSON','Six matched synthetic-domain traces against upstream REx.'),
        ('reference-audit-summary.json','Reference audit · JSON','Five tasks and 92 real reference-test executions.'),
        ('benchmark-checks.json','Benchmark integrity checks · JSON','Complete coverage, source immutability and sealed analysis checks.')]),
        ('Provenance and reproducibility',[
        ('composition.json','Trial source mapping · JSON','Which source campaign supplied each selected trial.'),
        ('selection-protocol.json','Replacement protocol · JSON','The all-method rerun rule fixed before new inference and hidden judging.'),
        ('seal.json','Search seal · JSON','Hash inventory and complete coverage of the selected analysis view.'),
        ('model-and-runner.json','Resolved model and judge · JSON','Exact model digest, sampling settings and runner configuration.'),
        ('policy.py','Policy implementation · Python','Actual arm initialization, selection and progress update code.'),
        ('cost_estimator.py','Cost estimation · Python','Initial estimate, online adaptation and observed-usage charging.'),
        ('sealed-benchmark.zip','Sealed benchmark bundle · ZIP','Analysis database, artifacts, evaluation checkpoints and full source mappings.')]),
        ('Recorded search traces',[
        ('replay.html','Representative trace · HTML','Saved prompts, code, arm selections and repair feedback.'),
        ('replay_success.html','Hidden-success trace · HTML','A recorded returned program that passed every hidden test.'),
        ('replay_loss.html','Hidden-failure trace · HTML','A recorded returned program that did not pass every hidden test.')])]
    evidence_groups=''
    for i,(title,items) in enumerate(groups,1):
        evidence_groups+='<section>'+section_title(f'{i:02d}',title)+'<div class="file-list">'
        for name,label,detail in items:
            size=(SITE/'evidence'/name).stat().st_size
            human=f'{size/1024:.0f} KB' if size<1024**2 else f'{size/1024**2:.1f} MB'
            evidence_groups+=f'<a href="evidence/{name}"'+(' download' if name.endswith(('.zip','.csv','.py')) else '')+f'>{icon("file")}<div><h3>{label}</h3><p>{detail}</p></div><span class="file-size">{human}</span>{icon("arrow")}</a>'
        evidence_groups+='</div></section>'
    files=f'''<section class="opening-note"><p>Open the recorded outputs below or download the sealed bundle to inspect the underlying measurements.</p><p class="small">The original project remains unchanged. The website contains the evidence needed to inspect this pilot; it does not contain model weights or a new benchmark run.</p></section>{evidence_groups}<section>{section_title('05','Snapshot identifiers')}<div class="hash-record"><span>Search seal</span><code>{esc(facts['search_seal'])}</code><span>Evaluation version</span><code>{esc(facts['evaluation_version'])}</code></div><p class="small">The bundle contains the analysis files bound by this seal. Source mappings explain the twelve original and three replacement trials.</p></section>'''
    pages={
        'index.html':('Overview','',overview),
        'methods.html':('Methods','How the search works, and the two changes to REx.',methods),
        'results.html':('Results','The measured comparison, with calls, tokens and per-problem scores.',results),
        'testing.html':('Testing','What was checked, what passed, and where the records are.',testing),
        'progress.html':('Progress','Implementation, pilot completion, and the remaining research work.',progress),
        'files.html':('Files & evidence','The recorded measurements, test reports and source mappings.',files),
    }
    for filename,(title,subtitle,body) in pages.items():
        (SITE/filename).write_text(page(filename,title,subtitle,body),encoding='utf-8')
    (SITE/'README.txt').write_text('Open index.html in a browser. No server, installation or internet connection is required. Keep the assets and evidence folders alongside the HTML files. The site contains real recorded pilot results; worked examples are labeled separately.\n',encoding='utf-8')
    print(json.dumps({'site':str(SITE),'pages':len(pages),'offline_tests':offline['passed'],'docker_tests':docker['passed'],
                      'benchmark_bundle_bytes':(SITE/'evidence/sealed-benchmark.zip').stat().st_size}))


if __name__=='__main__':
    build()
