from __future__ import annotations

import base64
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from docker import from_env  # type: ignore[attr-defined]
from docker.types import LogConfig

from ..config import Judge
from ..types import EvaluationResult, Limits, Status, TestOutcome
from ..util import fingerprint, sha
from .compare import compare


class DockerJudge:
    def __init__(self, config: Judge):
        self.config = config
        self.owner = "standalone-" + uuid.uuid4().hex
        self.client = from_env(timeout=config.startup_seconds)
        self.client.ping()
        image = self.client.images.get(config.image)
        self.image_digest = image.id
        if config.image_digest and self.image_digest != config.image_digest:
            raise RuntimeError("Runner image drift")
        if self.client.info().get("OSType") != "linux":
            raise RuntimeError("Linux containers required")

    def cleanup_owned(self):
        """Caller holds the experiment writer lock; remove only that experiment's old runners."""
        removed = []
        for container in self.client.containers.list(all=True, filters={"label": f"rexbench.owner={self.owner}"}):
            removed.append(container.id)
            container.remove(force=True)
        return removed

    def _exec(self, container, command: list[str], limits: Limits, deadline: float):
        """Bounded streaming and a host deadline; exit comes from Docker exec inspection."""
        api = self.client.api
        execution = api.exec_create(container.id, command, user="65533:65533", stdout=True, stderr=True)
        result: dict[str, Any] = {"stdout": bytearray(), "stderr": bytearray(), "overflow": False, "error": None}
        completed = threading.Event()
        started_ack = threading.Event()
        stream_holder = []

        def collect():
            try:
                stream = api.exec_start(execution["Id"], stream=True, demux=True)
                stream_holder.append(stream)
                started_ack.set()
                for out, err in stream:
                    for key, chunk, cap in [("stdout", out, limits.stdout_bytes),
                                            ("stderr", err, limits.stderr_bytes)]:
                        if chunk:
                            buffer = result[key]
                            remaining = max(0, cap - len(buffer))
                            buffer.extend(chunk[:remaining])
                            if len(chunk) > remaining:
                                result["overflow"] = True
                                return
            except Exception as exc:
                result["error"] = type(exc).__name__
            finally:
                started_ack.set()
                completed.set()

        thread = threading.Thread(target=collect, daemon=True)
        started = time.monotonic()
        thread.start()
        # A newly-created exec reports Running=False until the start request is accepted.
        # Never mistake that pre-start state for a completed program and kill the container.
        acknowledged = started_ack.wait(max(.01, deadline - started))
        inspected = api.exec_inspect(execution["Id"])
        while inspected["Running"] and not result["overflow"] and not result["error"] and time.monotonic() < deadline:
            time.sleep(min(.05, max(.001, deadline - time.monotonic())))
            inspected = api.exec_inspect(execution["Id"])
        timed_out = (not acknowledged or inspected["Running"]) and time.monotonic() >= deadline
        main_exited = acknowledged and not inspected["Running"] and inspected.get("ExitCode") is not None
        descendant_cleanup = False
        if main_exited and not completed.wait(.1):
            # A descendant may retain output descriptors after the main program has exited.
            container.kill()
            descendant_cleanup = True
        if timed_out or result["overflow"] or result["error"]:
            # Removing this container kills every descendant, including escaped process groups.
            container.kill()
        thread.join(timeout=2)
        for stream in stream_holder:
            try:
                stream.close()
            except Exception:
                pass
        inspected = api.exec_inspect(execution["Id"])
        if descendant_cleanup:
            result["error"] = None  # Expected stream closure after descendant cleanup, exit was observed separately.
        if inspected["Running"] and not timed_out:
            result["error"] = "Exec still running after output stream closed"
        return result, inspected, timed_out, time.monotonic() - started

    def _case(self, folder: str, case, comparator, limits: Limits) -> TestOutcome:
        container = None
        startup = time.monotonic()
        name = "rexbench-" + uuid.uuid4().hex
        try:
            startup_deadline = min(startup + limits.startup_seconds, getattr(self, "deadline", float("inf")))
            def startup_budget():
                remaining_startup = startup_deadline - time.monotonic()
                if remaining_startup <= 0:
                    raise TimeoutError("Container startup deadline reached")
                self.client.api.timeout = remaining_startup
            remaining = getattr(self, "deadline", float("inf")) - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Campaign deadline reached before judging")
            self.client.api.timeout = min(limits.startup_seconds, remaining)
            startup_budget()
            # No broad workspace mounts, socket, credentials or expected-output mounts.
            container = self.client.containers.create(
                self.image_digest, name=name, labels={"rexbench": "runner", "rexbench.owner": self.owner}, network_disabled=True,
                user="65534:65534", read_only=True, cap_drop=["ALL"], security_opt=["no-new-privileges"],
                mem_limit=f"{limits.memory_mib}m", memswap_limit=f"{limits.memory_mib}m",
                nano_cpus=int(limits.cpus * 1e9), pids_limit=limits.pids_limit,
                tmpfs={"/tmp": f"rw,noexec,nosuid,size={limits.tmp_mib}m,mode=1777"},
                volumes={folder: {"bind": "/candidate", "mode": "ro"}},
                environment={"PYTHONHASHSEED": "0", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC"},
                log_config=LogConfig(type="none"))
            startup_budget()
            container.start()
            startup_budget()
            container.reload()
            elapsed = time.monotonic() - startup
            if elapsed > limits.startup_seconds or not container.attrs["State"]["Running"]:
                raise RuntimeError("Container startup deadline/lifecycle failure")
            deadline = min(time.monotonic() + limits.program_wall_seconds, getattr(self, "deadline", float("inf")))
            self.client.api.timeout = min(limits.program_wall_seconds, max(.1, deadline - time.monotonic()))
            command = ["python", "-I", "/runner/execute.py", "compile", str(limits.cpu_seconds)]
            result, execution, timeout, wall = self._exec(container, command, limits, deadline)
            phase = "compile"
            if not timeout and not result["overflow"] and not result["error"] and execution["ExitCode"] == 0:
                phase = "program"
                command = ["python", "-I", "/runner/execute.py", "run", str(limits.cpu_seconds),
                           base64.b64encode(case.input.encode()).decode()]
                result, execution, timeout, run_wall = self._exec(container, command, limits, deadline)
                wall += run_wall
            container.reload()
            state = container.attrs["State"]
            # cgroup-v2 counter is read by another uid; generated stdout cannot forge it.
            oom = bool(state.get("OOMKilled"))
            if state.get("Running"):
                events = container.exec_run(["cat", "/sys/fs/cgroup/memory.events"], user="65534:65534")
                if events.exit_code == 0:
                    counters = dict(line.split() for line in events.output.decode().splitlines())
                    oom = oom or int(counters.get("oom_kill", "0")) > 0
            stdout = bytes(result["stdout"])
            stderr = bytes(result["stderr"]).decode("utf-8", errors="replace")
            exit_code = execution.get("ExitCode")
            if result["overflow"]:
                status = Status.OUTPUT_LIMIT
            elif oom:
                status = Status.MEMORY_LIMIT
            elif timeout and time.monotonic() >= getattr(self, "deadline", float("inf")):
                status = Status.INFRA_ERROR
            elif timeout or exit_code in (137, 152):
                # Exit 137 alone is ambiguous; do not call it Docker failure or proven OOM.
                status = Status.TIME_LIMIT if timeout or exit_code == 152 else Status.RUNTIME_ERROR
            elif result["error"]:
                status = Status.INFRA_ERROR
            elif phase == "compile" and exit_code == 42:
                status = Status.SYNTAX_ERROR
            elif phase == "compile" and exit_code != 0:
                status = Status.RUNTIME_ERROR
            elif exit_code != 0:
                status = Status.RUNTIME_ERROR
            else:
                try:
                    actual = stdout.decode("utf-8", errors="strict")
                    status = Status.PASS if compare(actual, case.output, comparator) else Status.WRONG_ANSWER
                except UnicodeError:
                    status = Status.WRONG_ANSWER
            return TestOutcome(case_id=case.id, status=status, stdout_hash=sha(stdout),
                               stdout_preview=stdout[:8000].decode(errors="replace"), stderr=stderr,
                               exit_code=exit_code, wall_seconds=wall, startup_seconds=elapsed,
                               lifecycle={"container": container.id, "state": state, "exec": execution,
                                          "phase": phase, "oom_evidence": oom,
                                          "cpu_memory_measurement": "unavailable per exec"})
        except Exception as exc:
            return TestOutcome(case_id=case.id, status=Status.INFRA_ERROR,
                               stderr=f"{type(exc).__name__}: {str(exc)[:1000]}",
                               startup_seconds=time.monotonic() - startup, lifecycle={"name": name})
        finally:
            self.client.api.timeout = self.config.startup_seconds
            if container is not None:
                container.remove(force=True)
            else:
                # An accepted create can time out before its ID reaches the client.
                try:
                    self.client.containers.get(name).remove(force=True)
                except Exception:
                    pass

    def evaluate(self, code: str, cases, comparator, limits: Limits):
        with tempfile.TemporaryDirectory(prefix="rexbench-code-") as folder:
            os.chmod(folder, 0o755)
            path = Path(folder) / "main.py"
            path.write_bytes(code.encode("utf-8"))
            path.chmod(0o444)
            outcomes = [self._case(folder, c, comparator, limits) for c in cases]
        return EvaluationResult(outcomes=outcomes, execution_fingerprint=fingerprint(
            ["docker_v1", sha(code), [c.model_dump() for c in cases], comparator, limits.model_dump(),
             self.image_digest, {"PYTHONHASHSEED": "0", "locale": "C.UTF-8", "TZ": "UTC"}]))
