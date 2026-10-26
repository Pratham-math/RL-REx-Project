"""Create and render a six-page viva report from final measured JSON and PNGs."""
import html
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak


def build():
    root=Path('reports/viva')
    facts=json.loads((root/'results.json').read_text(encoding='utf-8'))
    out=Path('output/pdf/rex_viva_results.pdf')
    out.parent.mkdir(parents=True,exist_ok=True)
    regular=Path('C:/Windows/Fonts/arial.ttf')
    bold=Path('C:/Windows/Fonts/arialbd.ttf')
    pdfmetrics.registerFont(TTFont('Viva',str(regular)))
    pdfmetrics.registerFont(TTFont('VivaBold',str(bold)))
    pdfmetrics.registerFontFamily('Viva',normal='Viva',bold='VivaBold',italic='Viva',boldItalic='VivaBold')
    ink=colors.HexColor('#173046')
    teal=colors.HexColor('#127b70')
    muted=colors.HexColor('#526777')
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='VTitle',fontName='VivaBold',fontSize=23,leading=27,textColor=ink,spaceAfter=14))
    styles.add(ParagraphStyle(name='VHead',fontName='VivaBold',fontSize=13,leading=17,textColor=teal,spaceBefore=10,spaceAfter=6))
    styles.add(ParagraphStyle(name='VBody',fontName='Viva',fontSize=10,leading=14,textColor=ink,spaceAfter=8))
    styles.add(ParagraphStyle(name='VSmall',fontName='Viva',fontSize=8.5,leading=12,textColor=muted,spaceAfter=7))
    styles.add(ParagraphStyle(name='VFormula',fontName='VivaBold',fontSize=10,leading=15,textColor=ink,
                              backColor=colors.HexColor('#eaf4f1'),borderPadding=8,spaceBefore=4,spaceAfter=9))
    styles.add(ParagraphStyle(name='VCell',fontName='Viva',fontSize=9,leading=13,textColor=ink))
    story=[]
    def text(value,style='VBody'):
        story.append(Paragraph(value,styles[style]))
    def title(value):
        text(value,'VTitle')
    def heading(value):
        text(value,'VHead')
    def bullet(value):
        text('- '+value)
    def image(name,width=490,height=None):
        from PIL import Image as PILImage
        path=root/'figures'/name
        with PILImage.open(path) as pic:
            w,h=pic.size
        natural=width*h/w
        story.append(Image(str(path),width=width,height=natural if height is None else height,hAlign='CENTER'))
        story.append(Spacer(1,7))
    def page():
        story.append(PageBreak())
    methods=['resample','rex','rex_progress_cost']
    labels={'resample':'Resampling','rex':'REx baseline','rex_progress_cost':'Progress + cost REx'}
    def footer(canvas,doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#d8e5e9'))
        canvas.line(45,39,A4[0]-45,39)
        canvas.setFont('Viva',8)
        canvas.setFillColor(muted)
        canvas.drawString(45,25,'RExBench | measured development pilot | 26 Oct 2026')
        canvas.drawRightString(A4[0]-45,25,f'{doc.page}')
        canvas.restoreState()
    text('VIVA RESULTS / FROZEN LOCAL LLM','VSmall')
    title('Progress- and cost-aware<br/>code repair with bandit search')
    text(html.escape(facts['finding']))
    text('<b>Setup:</b> Qwen2.5-Coder 7B, Q4_K_M; NVIDIA RTX 4060 Laptop. Five paired development problems, three methods, seed 0. Up to eight nominal model calls per trial. No model training.')
    data=[['Method','Hidden success','Calls','Actual tokens']]
    for method in methods:
        group=[r for r in facts['trials'] if r['method']==method]
        value=facts['headline'][method]
        data.append([labels[method],f'{value["hidden_successes"]}/5 ({value["success"]:.0%})',str(sum(r['calls'] for r in group)),f'{sum(r["actual_tokens"] for r in group):,}'])
    data=[[Paragraph(html.escape(str(x)),styles['VCell']) for x in row] for row in data]
    table=Table(data,colWidths=[185,112,60,138],repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e4f1ed')),('TOPPADDING',(0,0),(-1,-1),9),
                               ('BOTTOMPADDING',(0,0),(-1,-1),9),('VALIGN',(0,0),(-1,-1),'TOP'),
                               ('LINEBELOW',(0,0),(-1,-1),.5,colors.HexColor('#d7e4e9'))]))
    story.append(table)
    story.append(Spacer(1,12))
    image('hidden_success.png',width=480)
    text('Hidden success means the repair-selected program passed every one of its five hidden tests. These are observed pilot results, not an official APPS score or evidence of general superiority.','VSmall')
    page()
    title('What I implemented differently')
    heading('Starting point: REx')
    text('REx treats candidate programs as arms in a growing bandit search. A repair-test pass fraction h initializes an arm\'s Beta distribution. Thompson sampling balances refining promising candidates and exploring other candidates or a fresh root generation.')
    text('alpha = 1 + 20h; beta = 1 + 20(1 - h)','VFormula')
    heading('Change 1: reward partial repair progress')
    text('For an incomplete repair of a non-root candidate, give fractional credit only for an increase in repair pass fraction:')
    text('r = 0.5 max(0, h_child - h_parent)<br/>alpha &lt;- alpha + r; beta &lt;- beta + (1 - r)','VFormula')
    text('Worked example: an improvement from h=0.3 to h=0.7 gives r=0.2. Baseline REx gives zero success credit to an incomplete repair. Root partial generations receive zero progress credit. A full repair pass is saved and stops search before updating its parent.')
    heading('Change 2: normalize by estimated token cost')
    text('priority = sampled_Beta_value / max(1, estimated_tokens)<super>0.5</super>','VFormula')
    text('The initial estimate is prompt characters / 4 + 512 output tokens. It is updated from current-trial usage with an exponential moving average. Actual cost reports use observed backend counts; estimates are only for selection.')
    heading('Contribution and scope')
    bullet('Implemented search-policy extension, shared baselines, isolated Docker judging, exact usage ledgers, sealed evaluation and saved trace replay.')
    bullet('Frozen model weights: this is inference-time bandit search, not LLM training or RLHF.')
    bullet('Progress shaping is a heuristic pseudo-count update; no exact posterior or optimality claim is made.')
    text('Baseline reference: Tang et al., Code Repair with LLMs gives an Exploration-Exploitation Tradeoff, NeurIPS 2024. https://arxiv.org/abs/2405.17503. Implementation: src/rexbench/policies/__init__.py and budgets.py.','VSmall')
    page()
    title('How the comparison was measured')
    bullet('Same model digest, sampling settings, prompts, parser, task bytes, comparator and container limits across methods.')
    bullet('Search used 3-6 repair tests per task. One failed repair case was included as feedback; five hidden tests per task stayed separate.')
    bullet('The returned program was selected by repair score, then the complete 15-trial analysis view was sealed before hidden evaluation.')
    bullet('Eight integer call checkpoints and two token checkpoints produce 150 hidden evaluations: 750 individual test executions.')
    image('per_task_hidden.png',width=480)
    heading('Interrupted-run provenance')
    text('One original request lost its response. The original campaign was preserved. Before new inference and hidden judging, a rule was fixed to rerun the entire affected problem for all three methods. Those three fresh trials and the twelve unaffected original trials form the analysis view. Source experiment IDs, raw responses, ledgers and hashes are retained; no favorable run was selected after seeing hidden scores.')
    text('Traceability: docs/viva_selection_protocol.json; runs/viva_complete_pilot/composition.json; the search seal and evaluation version are in reports/viva/results.json.','VSmall')
    page()
    title('Success across inference budgets')
    image('success_vs_calls.png',width=485)
    image('success_vs_tokens.png',width=485)
    text('Each curve evaluates the repair-selected return. Token checkpoints use only completed generations at or below the threshold; a crossing generation remains charged to total work. Shading is a paired task-bootstrap 95% interval. With five tasks, these intervals are descriptive and cannot establish broad generalization.','VSmall')
    page()
    title('What worked, and what it shows')
    text(html.escape(facts['finding']))
    text(html.escape(facts['mechanism']))
    image('cost_comparison.png',width=490)
    heading('Bounded conclusions')
    bullet('The system produced real candidate code, executed isolated tests and completed a traceable hidden evaluation. The extension is implemented and tested.')
    bullet('A tie with REx does not establish an improvement or population-level equivalence. Identical observed outcomes can produce a zero-width paired bootstrap interval in this tiny sample.')
    bullet('Only the combined extension was evaluated. Progress-only and cost-only component effects are unmeasured.')
    bullet('Sparse repair feedback, one seed, public development tasks and five hidden tests per task limit the conclusion. More tasks/seeds and a frozen held-out evaluation are future work.')
    text(f'Selected comparison: {facts["selected_requests"]} requests and {facts["selected_actual_tokens"]:,} actual tokens. All pilot work including archived CPU and discarded GPU trials: {facts["all_pilot_requests_including_archived_cpu"]} requests and {facts["all_pilot_known_tokens_including_archived_cpu"]:,} known tokens plus one request with unknown usage. Setup, smoke, audits and hidden judging are separate.','VSmall')
    page()
    title('What to say in the viva')
    heading('A short speaking script')
    script=(root/'SPEAKING_SCRIPT.txt').read_text(encoding='utf-8').strip().strip('"')
    text(html.escape(script))
    heading('If asked: did your change improve REx?')
    text('"In this small pilot it matched REx. I verified that the implementation changes the update and priority formulas, but the measured branch choices were identical. That tells me this budget and feedback did not exercise the modification strongly enough to demonstrate an advantage. A larger, component-wise study is needed."')
    heading('If asked: what is your contribution?')
    text('"I implemented the progress/cost extension and an auditable evaluation system around an existing REx scheduler. I did not invent REx, train the LLM or reproduce the paper\'s historical model and full benchmark. My report separates the measured finding from the hypothesis."')
    heading('Useful files to open')
    text('reports/viva/OPEN_FOR_VIVA.html - presentation and graphs<br/>reports/viva/VIVA_NOTES.md - extended answers<br/>reports/viva/replay.html - recorded search demonstration<br/>reports/viva/per_task_results.csv - exact task-level outcomes','VSmall')
    doc=SimpleDocTemplate(str(out),pagesize=A4,rightMargin=45,leftMargin=45,topMargin=48,bottomMargin=52,
                          title='Progress- and cost-aware REx: measured pilot results',author='RExBench development study')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    # Render every page for visual inspection, independently of text extraction.
    import pymupdf
    document=pymupdf.open(out)
    render=Path('tmp/pdfs/viva')
    render.mkdir(parents=True,exist_ok=True)
    for number,page_obj in enumerate(document,1):
        page_obj.get_pixmap(matrix=pymupdf.Matrix(1.3,1.3),alpha=False).save(render/f'page-{number}.png')
    pages=len(document)
    text_pages=[p.get_text() for p in document]
    document.close()
    if pages!=6:
        raise RuntimeError(f'Expected six report pages; got {pages}. Inspect layout before delivery.')
    if any(len(t.strip())<100 for t in text_pages):
        raise RuntimeError('Unexpected nearly empty report page')
    shutil_target=root/'VIVA_REPORT.pdf'
    import shutil
    shutil.copy2(out,shutil_target)
    print(json.dumps({'pdf':str(out),'pages':pages,'rendered_pages':str(render)}))


if __name__=='__main__':
    build()
