from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import signal
import time
from contextlib import contextmanager
from pathlib import Path

from .backends.mock import MockBackend
from .backends.ollama import OllamaBackend
from .config import Config, load_config
from .data.apps import load_repair
from .judge.docker import DockerJudge
from .judge.mock import MockJudge
from .prompts import PARSER_VERSION, template_hash
from .search import run_trial
from .store import Store
from .util import fingerprint, now, read_json, sha, write_json


class CampaignPaused(RuntimeError):
    pass


def source_pins() -> dict:
    package = Path(__file__).parent
    project = package.parents[1]
    files = {p.relative_to(project).as_posix(): sha(p.read_bytes()) for p in package.rglob("*.py")}
    for path in [project / "docker" / "execute.py", project / "docker" / "Dockerfile", project / "uv.lock", project / "pyproject.toml"]:
        if path.exists():
            files[path.relative_to(project).as_posix()] = sha(path.read_bytes())
    return files


def environment() -> dict:
    dependencies = {name: importlib.metadata.version(name) for name in
                    ["rexbench", "numpy", "pydantic", "PyYAML", "matplotlib", "docker"]}
    return {"python": platform.python_version(), "platform": platform.platform(), "dependencies": dependencies}


def adapters(config: Config):
    backend = (MockBackend(read_json(Path(config.model.mock_script))) if config.model.backend == "mock"
               else OllamaBackend(config.model))
    judge = (MockJudge(read_json(Path(config.judge.mock_script))) if config.judge.backend == "mock"
             else DockerJudge(config.judge))
    return backend, judge


def make_plan(config_path: Path, out: Path, pilot: Path | None = None):
    config = load_config(config_path)
    path = Path(config.data.repair_file).resolve()
    tasks = load_repair(path) if path.is_file() else []
    configured_count = config.data.dev_count if "dev_" in path.name else config.data.evaluation_count
    if tasks and len(tasks) != configured_count:
        raise ValueError(f"Frozen task count {len(tasks)} differs from configured count {configured_count}")
    if any(t.limits != config.judge.limits_only() for t in tasks):
        raise ValueError("Task limits differ from configured judge limits; re-audit before running")
    count = len(tasks) if tasks else configured_count
    jobs = [{"id": fingerprint([t.task_id, m, s])[:24], "task_id": t.task_id, "method": m, "seed": s}
            for t in tasks for m in config.experiment.methods for s in config.experiment.seeds]
    total = count * len(config.experiment.methods) * len(config.experiment.seeds)
    nominal = total * max(config.budgets.call_checkpoints)
    ceiling = total * config.budgets.coverage_extension_call_ceiling
    estimates = None
    if pilot:
        # A pilot resource JSON is measured evidence, not an invented runtime forecast.
        measured = read_json(pilot)
        if measured.get("synthetic"):
            raise ValueError("Synthetic fixtures cannot provide real campaign resource forecasts")
        estimates = {"source": str(pilot), "source_hash": sha(pilot.read_bytes()),
                     "nominal_tokens": nominal * measured["mean_tokens_per_call"],
                     "nominal_model_seconds": nominal * measured["mean_model_seconds_per_call"],
                     "hidden_judge_seconds": total * (max(config.budgets.call_checkpoints) +
                        len(config.budgets.token_checkpoints)) * measured["mean_hidden_judge_seconds"]}
    plan = {"schema_version": 1, "created": now(), "config": config.model_dump(mode="json"),
            "config_hash": config.config_hash, "repair_file": str(path),
            "data_hash": sha(path.read_bytes()) if tasks else None, "jobs": jobs,
            "source_pins": source_pins(), "environment": environment(),
            "prompt_hash": template_hash(), "parser_version": PARSER_VERSION,
            "status": "ready_for_resolution" if tasks else "blocked_missing_repair_dataset",
            "resources": {"task_count": count, "method_count": len(config.experiment.methods),
                          "seed_count": len(config.experiment.seeds), "trials": total,
                          "nominal_call_upper_bound": nominal, "extension_call_upper_bound": ceiling,
                          "extension_extra_upper_bound": ceiling - nominal,
                          "campaign_allowance": config.budgets.max_dispatched_calls,
                          "allowance_covers_nominal": config.budgets.max_dispatched_calls >= nominal,
                          "allowance_covers_extensions": config.budgets.max_dispatched_calls >= ceiling,
                          "wall_hours_pause_limit": config.budgets.campaign_wall_hours,
                          "external_allowance_usd": config.budgets.max_external_spend_usd,
                          "pilot_estimates": estimates, "dataset_audit": "separate reference runs, two per reference",
                          "tuning": "not included", "retries": "not included; unknown requests pause",
                          "local_compute": "time and electricity; no claim of zero computation cost"}}
    plan["plan_hash"] = fingerprint(plan)
    if out.exists():
        raise FileExistsError("Plan is immutable; choose a new output")
    write_json(out, plan)
    return plan


def validate_plan(plan: dict):
    payload = {k: v for k, v in plan.items() if k != "plan_hash"}
    if fingerprint(payload) != plan["plan_hash"]:
        raise ValueError("Plan hash mismatch")
    if source_pins() != plan["source_pins"]:
        raise ValueError("Source/dependency-lock drift: create a new experiment plan")
    if environment() != plan["environment"]:
        raise ValueError("Runtime/dependency drift: create a new plan")
    config = Config.model_validate(plan["config"])
    if config.config_hash != plan["config_hash"]:
        raise ValueError("Config hash mismatch")
    return config


@contextmanager
def writer_lock(root: Path):
    """OS lock released on crash. Stale worker leases are reclaimed only under this lock."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".writer.lock").open("a+b") as stream:
        stream.seek(0)
        stream.write(b"0")
        stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


def _audit_gate(config: Config):
    if not config.data.require_audit:
        if config.experiment.track != "synthetic":
            raise ValueError("Controlled study requires dataset audit")
        return
    manifest_path = Path(config.data.manifest)
    audit = read_json(manifest_path.with_name("audit.json"))
    manifest = read_json(manifest_path)
    from .data.audit import audit_identity
    if not config.judge.image_digest:
        raise ValueError("Runner digest must be resolved before audit verification")
    if audit.get("result_hash") != fingerprint({k: v for k, v in audit.items() if k != "result_hash"}) or audit.get("audit_identity") != audit_identity(manifest_path, config.judge.image_digest):
        raise ValueError("Dataset audit integrity/judge version mismatch; re-audit using a new output")
    if not audit["passed"] or audit["synthetic"] or audit["manifest_hash"] != sha(manifest_path.read_bytes()):
        raise ValueError("Dataset audit is missing, failed, synthetic or stale")
    task_file = Path(config.data.repair_file)
    if manifest["files"].get(task_file.name) != sha(task_file.read_bytes()):
        raise ValueError("Repair dataset does not match audited manifest")
    if audit["image_digest"] != config.judge.image_digest:
        raise ValueError("Dataset references were audited under a different runner")
    return {"manifest_hash": sha(manifest_path.read_bytes()), "audit_hash": sha(manifest_path.with_name("audit.json").read_bytes())}


def execute(plan_path: Path, root: Path | None = None):
    plan = read_json(plan_path)
    root = root or plan_path.parent
    if (root / "seal.json").exists():
        return status(root)  # A completed resume is an inert no-op, including after software upgrades.
    if (root / "state.sqlite").exists() and status(root).get("complete"):
        return status(root)
    config = validate_plan(plan)
    if not plan["jobs"] or plan["status"] != "ready_for_resolution":
        raise ValueError("Plan lacks actual frozen repair tasks; run dataset preparation and audit")
    with writer_lock(root):
        backend, judge = adapters(config)
        if (root / "resolved_config.json").exists() and hasattr(judge, "cleanup_owned"):
            judge.owner = fingerprint([fingerprint(read_json(root / "resolved_config.json")), str(root.resolve())])
            judge.cleanup_owned()
        info = backend.info()
        resolved = config.model_copy(deep=True)
        resolved.model.digest = info["digest"]
        resolved.judge.image_digest = judge.image_digest
        if config.model.backend == "ollama":
            backend.config = resolved.model
        audited = _audit_gate(resolved)
        pins = {"plan_hash": plan["plan_hash"], "config": resolved.model_dump(mode="json"),
                "model_info": info, "image_digest": judge.image_digest, "audit": audited,
                "source_pins": plan["source_pins"], "environment": plan["environment"]}
        resolved_path = root / "resolved_config.json"
        if resolved_path.exists():
            if read_json(resolved_path) != pins:
                raise ValueError("Resolved model/image/config/environment drift; resume refused")
        else:
            write_json(resolved_path, pins)
        repair = Path(plan["repair_file"])
        if sha(repair.read_bytes()) != plan["data_hash"]:
            raise ValueError("Repair data drift")
        tasks = {t.task_id: t for t in load_repair(repair)}
        if set(tasks) != {j["task_id"] for j in plan["jobs"]}:
            raise ValueError("Planned matrix does not match frozen tasks")
        copy = root / "repair.jsonl"
        if copy.exists() and sha(copy.read_bytes()) != plan["data_hash"]:
            raise ValueError("Frozen repair artifact drift")
        if not copy.exists():
            from .util import atomic_bytes
            atomic_bytes(copy, repair.read_bytes())
        if plan_path.resolve() != (root / "plan.json").resolve():
            if (root / "plan.json").exists() and read_json(root / "plan.json") != plan:
                raise ValueError("Different experiment exists at destination")
            write_json(root / "plan.json", plan)
        store = Store(root)
        identity = fingerprint(pins)
        if hasattr(judge, "cleanup_owned"):
            judge.owner = fingerprint([identity, str(root.resolve())])
            judge.cleanup_owned()
        with store.transaction():
            store.db.execute("INSERT OR IGNORE INTO experiments VALUES(?,?)", (identity, json.dumps(pins)))
            for job in plan["jobs"]:
                store.db.execute("INSERT OR IGNORE INTO planned_trials VALUES(?,?,?,?)",
                                 (job["id"], job["task_id"], job["method"], job["seed"]))
                store.db.execute("INSERT OR IGNORE INTO trial_states(id,status) VALUES(?,'planned')", (job["id"],))
            store.db.execute("UPDATE trial_states SET lease_owner=NULL,lease_until=NULL")
        active = store.db.execute("SELECT value FROM metadata WHERE key='active_seconds'").fetchone()
        previous_seconds = float(active[0]) if active else 0.
        started = time.monotonic()
        backend.deadline = started + max(0., resolved.budgets.campaign_wall_hours * 3600 - previous_seconds)
        judge.deadline = backend.deadline
        cancelled = False

        def cancel(_sig, _frame):
            nonlocal cancelled
            cancelled = True
            raise KeyboardInterrupt

        previous_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, cancel)

        def check():
            count = store.db.execute("SELECT COUNT(*) FROM requests WHERE state NOT IN ('prepared','rejected')").fetchone()[0]
            elapsed = previous_seconds + time.monotonic() - started
            if cancelled or count >= resolved.budgets.max_dispatched_calls:
                raise CampaignPaused("Campaign inference allowance reached")
            if elapsed >= resolved.budgets.campaign_wall_hours * 3600:
                raise CampaignPaused("Campaign elapsed-time allowance reached")

        try:
            for job in plan["jobs"]:
                checkpoint = store.load(job["id"])
                if checkpoint and checkpoint.stop_reason:
                    continue
                store.db.execute("UPDATE trial_states SET lease_owner=?,lease_until=? WHERE id=?",
                                 (f"pid:{os.getpid()}", time.time() + 3600, job["id"]))
                try:
                    run_trial(store, tasks[job["task_id"]], job, resolved, backend, judge, identity, check)
                except (CampaignPaused, KeyboardInterrupt):
                    raise
                except Exception as exc:
                    with store.transaction():
                        store.event(job["id"], "controller_error", {"type": type(exc).__name__, "message": str(exc)[:1000]})
                        store.db.execute("UPDATE trial_states SET status='error',stop_reason=? WHERE id=?",
                                         (type(exc).__name__, job["id"]))
                finally:
                    store.db.execute("UPDATE trial_states SET lease_owner=NULL,lease_until=NULL WHERE id=?", (job["id"],))
        except (CampaignPaused, KeyboardInterrupt) as exc:
            with store.transaction():
                store.db.execute("UPDATE trial_states SET status='paused',stop_reason=? WHERE status IN ('planned','running')",
                                 (str(exc) or "cancelled",))
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)
            store.db.execute("INSERT OR REPLACE INTO metadata VALUES('active_seconds',?)",
                             (str(previous_seconds + time.monotonic() - started),))
            store.close()
    return status(root)


def status(root: Path):
    plan = read_json(root / "plan.json")
    if not (root / "state.sqlite").exists():
        return {"expected": len(plan["jobs"]), "completed": 0, "status": plan["status"], "resources": plan["resources"]}
    store = Store(root, readonly=True)
    try:
        trials = store.rows("SELECT p.*,s.status,s.stop_reason,s.checkpoint FROM planned_trials p JOIN trial_states s ON p.id=s.id")
        requests = store.rows("SELECT * FROM requests")
        states: dict[str, int] = {}
        for trial in trials:
            states[trial["status"]] = states.get(trial["status"], 0) + 1
        usage = 0
        unknown = 0
        for r in requests:
            if r["state"] in ("dispatched", "unknown"):
                unknown += 1
            elif r["response_blob"]:
                raw = store.object(r["response_blob"])
                input_tokens = raw.get("input_tokens", raw.get("prompt_eval_count"))
                output_tokens = raw.get("output_tokens", raw.get("eval_count"))
                valid_input = type(input_tokens) is int and input_tokens >= 0
                valid_output = type(output_tokens) is int and output_tokens >= 0
                if not valid_input or not valid_output:
                    unknown += 1
                usage += (input_tokens if valid_input else 0) + (output_tokens if valid_output else 0)
        from .evaluate import coverage
        checked = coverage(root, store)
        return {"expected": len(plan["jobs"]), "observed": len(trials), "states": states, "trials": trials,
                "inference_attempts": sum(r["state"] not in ("prepared", "rejected") for r in requests),
                "known_actual_tokens": usage, "unknown_usage_requests": unknown,
                "coverage": checked,
                "complete": checked["complete"] and unknown == 0}
    finally:
        store.close()
