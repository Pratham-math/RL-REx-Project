import time
from types import SimpleNamespace

from rexbench.judge.docker import DockerJudge
from rexbench.types import Limits


def test_exec_created_but_not_started_is_not_completed():
    state = {"started": False, "killed": False}
    class API:
        def exec_create(self, *_args, **_kwargs):
            return {"Id": "fixture"}

        def exec_start(self, *_args, **_kwargs):
            time.sleep(.15)  # Force a start-ack delay longer than the old cleanup grace.
            state["started"] = True
            return iter([(b"ok", None)])

        def exec_inspect(self, _id):
            return {"Running": False, "ExitCode": 0 if state["started"] else None}

    class Container:
        id = "fixture"
        def kill(self):
            state["killed"] = True

    judge = object.__new__(DockerJudge)
    judge.client = SimpleNamespace(api=API())
    result, execution, timeout, _ = judge._exec(Container(), ["fixture"], Limits(), time.monotonic() + 2)
    assert result["stdout"] == b"ok" and execution["ExitCode"] == 0
    assert not timeout and not state["killed"]
