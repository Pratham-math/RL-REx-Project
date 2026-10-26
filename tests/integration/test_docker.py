"""Real containers only. A skip is unverified, never a mock integration pass."""
import os
import uuid

import pytest

from rexbench.config import Judge
from rexbench.judge.docker import DockerJudge
from rexbench.types import Case, Limits, Status

pytestmark = pytest.mark.docker


@pytest.fixture(scope="module")
def judge():
    try:
        return DockerJudge(Judge(image=os.environ.get("REXBENCH_IMAGE", "rexbench-runner:local")))
    except Exception as exc:
        pytest.skip(f"Real Linux runner unavailable: {exc}")


@pytest.mark.parametrize("code,input_text,expected,status", [
    ("print(input())", "hello\n", "hello\n", Status.PASS),
    ("print(2)", "", "1\n", Status.WRONG_ANSWER),
    ("def broken(:", "", "", Status.SYNTAX_ERROR),
    ("raise ValueError('fixture')", "", "", Status.RUNTIME_ERROR),
    ("import sys;sys.exit(125)", "", "", Status.RUNTIME_ERROR),
    ("import sys;sys.exit(126)", "", "", Status.RUNTIME_ERROR),
    ("import sys;sys.exit(127)", "", "", Status.RUNTIME_ERROR),
    ("while True: pass", "", "", Status.TIME_LIMIT),
    ("print('x'*1000000)", "", "x\n", Status.OUTPUT_LIMIT),
    ("import sys;sys.stderr.write('x'*1000000)", "", "", Status.OUTPUT_LIMIT)])
def test_real_statuses(judge, code, input_text, expected, status):
    outcome = judge.evaluate(code, [Case(id="fixture", input=input_text, output=expected)], "tokens_v1", Limits()).outcomes[0]
    assert outcome.status == status, outcome.model_dump()


def test_real_memory_limit(judge):
    code = "a=[]\nwhile True: a.append(bytearray(4*1024*1024))"
    outcome = judge.evaluate(code, [Case(id="memory", input="", output="")], "tokens_v1", Limits()).outcomes[0]
    assert outcome.status == Status.MEMORY_LIMIT, outcome.model_dump()


def test_real_isolation_process_cleanup_and_fresh_cases(judge):
    code = """import os,socket,subprocess
assert os.getuid()!=0
assert not os.path.exists('/var/run/docker.sock')
try:
 open('/runner/attack','w').write('bad')
 raise AssertionError('root writable')
except OSError: pass
try:
 socket.create_connection(('1.1.1.1',80),timeout=.2)
 raise AssertionError('network escaped')
except OSError: pass
assert not os.path.exists('/tmp/sentinel')
open('/tmp/sentinel','w').write('state')
subprocess.Popen(['python','-c','import time;time.sleep(20)'])
print('ok')
"""
    cases = [Case(id=str(i), input=str(i), output="ok") for i in range(2)]
    result = judge.evaluate(code, cases, "tokens_v1", Limits())
    assert result.h == 1, result.model_dump()
    assert not judge.client.containers.list(all=True, filters={"label": "rexbench=runner"})


def test_real_repeated_nondeterminism_diagnostic(judge):
    code = "import os;print(os.urandom(16).hex())"
    case = Case(id="random", input="", output="unmatchable")
    a = judge.evaluate(code, [case], "tokens_v1", Limits()).outcomes[0]
    b = judge.evaluate(code, [case], "tokens_v1", Limits()).outcomes[0]
    assert a.stdout_hash != b.stdout_hash


def test_real_cancellation_removes_container(judge, monkeypatch):
    owner = "test-cancel-" + uuid.uuid4().hex
    judge.owner = owner
    def interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt()
    monkeypatch.setattr(judge, "_exec", interrupt)
    with pytest.raises(KeyboardInterrupt):
        judge.evaluate("while True: pass", [Case(id="cancel", input="", output="")], "tokens_v1", Limits())
    assert not judge.client.containers.list(all=True, filters={"label": f"rexbench.owner={owner}"})


def test_real_owned_orphan_recovery(judge):
    owner = "test-orphan-" + uuid.uuid4().hex
    judge.owner = owner
    orphan = judge.client.containers.create(judge.image_digest, network_disabled=True, read_only=True,
                                          cap_drop=["ALL"], user="65534:65534",
                                          labels={"rexbench": "runner", "rexbench.owner": owner})
    try:
        orphan.start()
        assert orphan.id in judge.cleanup_owned()
        assert not judge.client.containers.list(all=True, filters={"label": f"rexbench.owner={owner}"})
    finally:
        try:
            orphan.remove(force=True)
        except Exception:
            pass
