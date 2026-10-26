"""Local Ollama backend and isolated, standard-input Python test execution."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request
import uuid

from rex import Evaluation


class Ollama:
    def __init__(self, model='qwen2.5-coder:7b', url='http://localhost:11434',
                 temperature=1.0, max_tokens=2048, context=32768):
        self.model, self.url = model, url.rstrip('/')
        self.temperature, self.max_tokens, self.context = temperature, max_tokens, context

    def _request(self, path, payload):
        request = urllib.request.Request(self.url + path,
            data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=900) as response:
            return json.load(response)

    def info(self):
        # Store the full local model configuration, including underlying model hash.
        return self._request('/api/show', {'model': self.model})

    def generate(self, prompt, seed):
        out = self._request('/api/chat', {
            'model': self.model, 'stream': False,
            'messages': [{'role': 'user', 'content': prompt}],
            'options': {'temperature': self.temperature, 'seed': seed,
                        'num_predict': self.max_tokens, 'num_ctx': self.context}})
        if 'prompt_eval_count' not in out or 'eval_count' not in out:
            raise RuntimeError('Actual token counts are required for cost evaluation.')
        return {'text': out['message']['content'],
                'input_tokens': out['prompt_eval_count'], 'output_tokens': out['eval_count']}


class DockerEvaluator:
    def __init__(self, image='python:3.11-slim', timeout=5.0):
        self.image, self.timeout = image, timeout
        if not shutil.which('docker'):
            raise RuntimeError('Docker is required; generated programs are never run on the host.')
        check = subprocess.run(['docker', 'image', 'inspect', image],
                               capture_output=True, text=True)
        if check.returncode:
            raise RuntimeError(f'First download the runner image: docker pull {image}')
        self.image_info = json.loads(check.stdout)[0]['Id']

    def __call__(self, code, tests):
        try:
            compile(code, 'candidate.py', 'exec')  # Syntax check only, never executes.
        except (SyntaxError, ValueError, OverflowError) as exc:
            return Evaluation([False] * len(tests), [f'Syntax error: {exc}'] * len(tests))
        passed, feedback = [], []
        with tempfile.TemporaryDirectory(prefix='rex_candidate_') as folder:
            os.chmod(folder, 0o755)
            path = Path(folder) / 'main.py'
            path.write_text(code)
            path.chmod(0o644)
            for case in tests:
                name = 'rex-' + uuid.uuid4().hex
                cmd = ['docker', 'run', '--rm', '-i', '--name', name,
                       '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                       '--security-opt', 'no-new-privileges', '--user', '65534:65534',
                       '--memory', '128m', '--memory-swap', '128m', '--cpus', '1',
                       '--pids-limit', '32', '--ulimit', 'fsize=131072:131072',
                       '--tmpfs', '/tmp:rw,noexec,nosuid,size=8m',
                       '--mount', f'type=bind,source={folder},target=/work,readonly',
                       self.image, 'sh', '-c',
                       'python -I /work/main.py >/tmp/out 2>/tmp/err; rc=$?; '
                       'head -c 65536 /tmp/out; head -c 4096 /tmp/err >&2; exit $rc']
                try:
                    proc = subprocess.run(cmd, input=case['input'], text=True,
                                          capture_output=True, timeout=self.timeout)
                    if proc.returncode in (125, 126, 127):
                        raise RuntimeError('Container infrastructure failed: ' + proc.stderr[-1000:])
                    ok = proc.returncode == 0 and proc.stdout.split() == case['output'].split()
                    detail = (f'Input:\n{case["input"][:3000]}\nExpected output:\n'
                              f'{case["output"][:3000]}\nActual output:\n{proc.stdout[:1500]}')
                    if proc.returncode:
                        detail += f'\nExit status: {proc.returncode}\nError:\n{proc.stderr[-1500:]}'
                except subprocess.TimeoutExpired:
                    ok, detail = False, f'Time limit exceeded. Input:\n{case["input"][:3000]}'
                    subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=30)
                passed.append(ok)
                feedback.append(detail)
        return Evaluation(passed, feedback)


def load_jsonl(path):
    with open(path) as stream:
        return [json.loads(line) for line in stream if line.strip()]


def dump_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2))
