import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .backends.mock import MockBackend
from .backends.ollama import OllamaBackend
from .config import load_config
from .experiment import environment
from .judge.docker import DockerJudge
from .util import read_json, write_json


def doctor(config_path: Path, out: Path):
    config = load_config(config_path)
    checks: dict[str, Any] = {"python": {"version": platform.python_version(), "supported": platform.python_version_tuple()[:2] == ("3", "11")},
              "environment": environment(), "strict_token_cap": {"supported": False, "reason": "No verified tokenizer/bound"},
              "model_calls": 0, "external_spend_usd": 0}
    try:
        backend = MockBackend(read_json(Path(config.model.mock_script))) if config.model.backend == "mock" else OllamaBackend(config.model)
        checks["model"] = {"available": True, **backend.info()}
    except Exception as exc:
        checks["model"] = {"available": False, "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
    try:
        if config.judge.backend == "mock":
            checks["judge"] = {"available": True, "synthetic": True}
        else:
            judge = DockerJudge(config.judge)
            checks["judge"] = {"available": True, "image_digest": judge.image_digest,
                               "runtime": judge.client.version(), "isolation_verified": "run pytest -m docker"}
    except Exception as exc:
        checks["judge"] = {"available": False, "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
    if shutil.which("docker"):
        process = subprocess.run(["docker", "version", "--format", "{{json .}}"], capture_output=True, text=True, timeout=40)
        checks["docker_cli"] = {"returncode": process.returncode, "stdout": process.stdout[:4000], "stderr": process.stderr[:1000]}
    checks["ready"] = checks["python"]["supported"] and checks["model"]["available"] and checks["judge"]["available"]
    checks["verification_scope"] = "capability inspection only; no generation or candidate execution"
    write_json(out, checks)
    return checks
