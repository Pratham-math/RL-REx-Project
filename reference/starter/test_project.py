"""Deterministic algorithm checks, not LLM benchmark results."""
import random
import unittest
from unittest.mock import patch
import contextlib
import io
import json
from pathlib import Path
import tempfile

from rex import Evaluation, make_node, update, search, METHODS
from prepare_apps import partition_tests
from evaluate import choose_event
from report import aggregates


def ev(passed):
    return Evaluation(passed, ['repair feedback'] * len(passed))


class ScriptedModel:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.prompts = []

    def generate(self, prompt, seed):
        self.prompts.append(prompt)
        return {'text': next(self.outputs), 'input_tokens': 40, 'output_tokens': 20}


class Tests(unittest.TestCase):
    def test_original_penalizes_incomplete_progress(self):
        parent = make_node('old', ev([1, 0, 0, 0]), constant=20)
        self.assertEqual((parent.alpha, parent.beta), (6, 16))
        update(parent, ev([1, 1, 1, 0]))
        self.assertEqual((parent.alpha, parent.beta), (6, 17))

    def test_progress_credit_and_regression(self):
        parent = make_node('old', ev([1, 0, 0, 0]), constant=20)
        self.assertEqual(update(parent, ev([1, 1, 1, 0]), eta=.5), .25)
        self.assertEqual((parent.alpha, parent.beta), (6.25, 16.75))
        self.assertEqual(update(parent, ev([0, 0, 0, 0]), eta=.5), 0)
        self.assertEqual((parent.alpha, parent.beta), (6.25, 17.75))

    def test_null_is_uniform_and_has_no_progress_credit(self):
        root = make_node(None, None, 20)
        self.assertEqual((root.alpha, root.beta), (1, 1))
        update(root, ev([1, 0]), eta=.5)
        self.assertEqual((root.alpha, root.beta), (1, 2))

    def test_same_one_call_result_across_methods(self):
        outputs = []
        for method in METHODS:
            model = ScriptedModel(['x'])
            result = search('problem', [1,2], model, lambda c,t:ev([1,0]),
                            method=method, max_calls=1)
            outputs.append((result['selected_code'], result['total_tokens']))
        self.assertEqual(len(set(outputs)), 1)

    def test_duplicate_calls_charged_and_arm_not_reset(self):
        calls = []
        def judge(code, tests):
            calls.append(code)
            return ev([1,0])
        result = search('problem', [1,2], ScriptedModel(['x','x','x']), judge,
                        method='greedy', max_calls=3)
        self.assertEqual(calls, ['x'])
        self.assertEqual(result['total_tokens'], 180)
        self.assertEqual(result['events'][-1]['parent_beta'], 13)
        self.assertEqual([e['duplicate'] for e in result['events']], [False,True,True])

    def test_first_full_visible_pass_stops(self):
        result = search('problem', [1,2], ScriptedModel(['a','b']),
                        lambda c,t:ev([1,1] if c=='b' else [1,0]),
                        max_calls=8)
        self.assertEqual(result['calls'], 2)
        self.assertTrue(result['visible_solved'])

    def test_zero_eta_gamma_recovers_original(self):
        def run(method):
            return search('problem',[1,2],ScriptedModel(['a','b','c','d']),
                          lambda c,t:ev([c in 'ab', 0]), method=method,
                          max_calls=4, eta=0, gamma=0)
        left, right = run('rex'), run('rex_progress_cost')
        self.assertEqual([e['parent_index'] for e in left['events']],
                         [e['parent_index'] for e in right['events']])
        self.assertEqual([e['parent_beta'] for e in left['events']],
                         [e['parent_beta'] for e in right['events']])

    def test_partition_no_duplicates_or_example_inputs_in_hidden(self):
        pairs = [(f'{i} {i+1}\n',f'{i*2+1}\n') for i in range(10,30)]
        pairs += pairs[:3]
        repair, hidden = partition_tests('Example: 10 11, answer 21.',pairs,random.Random(0))
        self.assertFalse({c['input'] for c in repair} & {c['input'] for c in hidden})
        self.assertIn('10 11\n', [c['input'] for c in repair])
        self.assertEqual(len(repair)+len(hidden), 20)

    def test_no_hidden_feedback_used_for_snapshot_selection(self):
        events = [{'call':1,'total_tokens':60,'selected_code':'first'},
                  {'call':2,'total_tokens':120,'selected_code':'second'}]
        self.assertIsNone(choose_event(events, tokens=59))
        self.assertEqual(choose_event(events,tokens=119)['selected_code'],'first')
        self.assertEqual(choose_event(events,calls=1)['selected_code'],'first')

    def test_paired_task_bootstrap_and_censoring(self):
        rows = [{'axis':'calls','budget':2,'method':m,'task_id':str(t),'seed':s,
                 'censored':False,'solved':m!='rex','actual_tokens':100,
                 'actual_calls':2,'visible_fraction':.5}
                for m in ['rex','rex_progress'] for t in range(3) for s in range(2)]
        summary = aggregates(rows)
        improved = next(r for r in summary if r['method']=='rex_progress')
        self.assertEqual(improved['delta_vs_rex'], 1)
        self.assertEqual(improved['delta_ci_low'], 1)
        self.assertEqual(improved['n_tasks'], 3)
        rows[0]['censored'] = True
        self.assertEqual(aggregates(rows), [])

    def test_pipeline_keeps_hidden_failures_out_of_search(self):
        import run as run_cli
        import evaluate as evaluate_cli
        import report as report_cli

        class FakeModel:
            def __init__(self, *args):
                pass
            def info(self):
                return {'test_only': True}
            def generate(self, prompt, seed):
                return {'text': 'print(1)', 'input_tokens': 40, 'output_tokens': 20}

        class FakeJudge:
            def __init__(self, *args):
                self.image_info = 'test-only-image'
            def __call__(self, code, tests):
                return ev([t['output'] != 'hidden-failure' for t in tests])

        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(tmp)
            public = root / 'repair.jsonl'
            hidden = root / 'hidden.jsonl'
            runs = root / 'runs'
            public.write_text(json.dumps({'id':'task-1','statement':'Print one.',
                'repair_tests':[{'input':'','output':'1'}]})+'\n')
            hidden.write_text(json.dumps({'id':'task-1',
                'hidden_tests':[{'input':'','output':'hidden-failure'}]})+'\n')
            with patch.object(run_cli, 'Ollama', FakeModel), \
                 patch.object(run_cli, 'DockerEvaluator', FakeJudge), \
                 patch('sys.argv', ['run.py','--tasks',str(public),'--out',str(runs),
                                    '--budget','2','--seeds','0','--methods','rex','rex_progress_cost']):
                run_cli.main()
            logs_before = {p.name:p.read_bytes() for p in runs.glob('*.jsonl')}
            with patch.object(evaluate_cli, 'DockerEvaluator', FakeJudge), \
                 patch('sys.argv', ['evaluate.py','--runs',str(runs),'--hidden',str(hidden),
                                    '--call-budgets','1','2','--token-budgets','60','120']):
                evaluate_cli.main()
            rows = json.loads((runs/'evaluation.json').read_text())
            self.assertTrue(rows)
            self.assertTrue(all(not r['solved'] and r['actual_calls']==1 for r in rows))
            self.assertEqual(logs_before, {p.name:p.read_bytes() for p in runs.glob('*.jsonl')})
            with patch('sys.argv',['report.py','--runs',str(runs)]):
                report_cli.main()
            self.assertTrue((runs/'summary.csv').exists())
            self.assertTrue((runs/'success_vs_tokens.png').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
