from __future__ import annotations

from pathlib import Path

from .budgets import checkpoint_snapshot
from .data.apps import load_repair
from .store import Store
from .types import HiddenTask
from .util import fingerprint, jsonl, now, read_json, sha, write_json


def coverage(root: Path, store: Store) -> dict:
    plan = read_json(root / "plan.json")
    expected = {(j["id"], j["task_id"], j["method"], j["seed"]) for j in plan["jobs"]}
    actual = {(r["id"], r["task"], r["method"], r["seed"]) for r in store.rows("SELECT * FROM planned_trials")}
    states = store.rows("SELECT * FROM trial_states")
    incomplete = [s["id"] for s in states if s["status"] != "completed"]
    unknown = store.rows("SELECT id,state FROM requests WHERE state!='committed'")
    censored = []
    for job in plan["jobs"]:
        state = store.load(job["id"])
        if not state:
            incomplete.append(job["id"])
            continue
        snapshots = store.snapshots(job["id"])
        for axis, budgets in [("calls", range(1, max(plan["config"]["budgets"]["call_checkpoints"]) + 1)),
                              ("tokens", plan["config"]["budgets"]["token_checkpoints"])]:
            for budget in budgets:
                _, censor = checkpoint_snapshot(snapshots, axis, budget, state.stop_reason)
                if censor:
                    censored.append({"trial": job["id"], "axis": axis, "budget": budget})
    return {"expected_jobs": len(expected), "observed_jobs": len(actual), "missing": sorted(expected - actual),
            "unexpected": sorted(actual - expected), "incomplete": sorted(set(incomplete)),
            "uncommitted_or_unknown_requests": unknown, "censored": censored,
            "complete": bool(expected) and expected == actual and len(states) == len(expected) and
                        not incomplete and not unknown and not censored}


def seal(root: Path):
    if (root / "seal.json").exists():
        return verify_seal(root)
    store = Store(root, readonly=True)
    try:
        checked = coverage(root, store)
        if not checked["complete"]:
            raise ValueError(f"Cannot seal incomplete matrix/checkpoints: {checked}")
        files = {name: sha((root / name).read_bytes()) for name in ["plan.json", "resolved_config.json", "repair.jsonl"]}
        artifacts = {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in (root / "artifacts").glob("*/*") if p.is_file()}
        # Content-addressed paths are verified as well as the aggregate hash.
        for name, digest in artifacts.items():
            parts = name.split("/")
            if parts[-2] + parts[-1] != digest:
                raise ValueError("Artifact path/hash mismatch")
        frozen = {"schema_version": 1, "created": now(), "files": files, "artifacts": artifacts,
                  "logical_store_hash": fingerprint(store.logical_dump()), "coverage": checked}
        frozen["seal_hash"] = fingerprint(frozen)
        write_json(root / "seal.json", frozen)
        return frozen
    finally:
        store.close()


def verify_seal(root: Path):
    frozen = read_json(root / "seal.json")
    if fingerprint({k: v for k, v in frozen.items() if k != "seal_hash"}) != frozen["seal_hash"]:
        raise ValueError("Seal hash mismatch")
    for name, digest in {**frozen["files"], **frozen["artifacts"]}.items():
        target = (root / name).resolve()
        if not target.is_relative_to(root.resolve()) or sha(target.read_bytes()) != digest:
            raise ValueError(f"Sealed file changed: {name}")
    store = Store(root, readonly=True)
    try:
        if fingerprint(store.logical_dump()) != frozen["logical_store_hash"]:
            raise ValueError("Sealed database changed")
        if not coverage(root, store)["complete"]:
            raise ValueError("Sealed coverage mismatch")
    finally:
        store.close()
    return frozen


def evaluate(root: Path, hidden_path: Path, judge):
    """Offline-only evaluator: no backend constructor, request or search mutation exists here."""
    frozen = verify_seal(root)
    plan, resolved = read_json(root / "plan.json"), read_json(root / "resolved_config.json")
    synthetic = plan["config"]["experiment"]["track"] == "synthetic"
    if not synthetic:
        manifest_path = Path(plan["config"]["data"]["manifest"])
        manifest = read_json(manifest_path)
        if sha(manifest_path.read_bytes()) != resolved["audit"]["manifest_hash"]:
            raise ValueError("Audited dataset manifest drift")
        if manifest["files"].get(hidden_path.name) != sha(hidden_path.read_bytes()):
            raise ValueError("Hidden data not bound to the frozen audited manifest")
    hidden_rows = [HiddenTask.model_validate(r) for r in jsonl(hidden_path)]
    hidden = {h.task_id: h for h in hidden_rows}
    task_ids = {j["task_id"] for j in plan["jobs"]}
    if set(hidden) != task_ids or len(hidden) != len(hidden_rows):
        raise ValueError("Hidden task matrix mismatch or duplicate IDs")
    repair = {r.task_id: r for r in load_repair(root / "repair.jsonl")}
    for task_id, task in hidden.items():
        public = repair[task_id]
        if task.comparator != public.comparator or task.limits != public.limits:
            raise ValueError("Hidden comparator/limits differ from audited repair task")
        if {sha(c.input) for c in task.hidden_tests} & {sha(c.input) for c in public.repair_tests}:
            raise ValueError("Hidden/repair input overlap")
    if judge.image_digest != resolved["image_digest"]:
        raise ValueError("Hidden judge image differs from search")
    from .data.audit import judging_version
    version = fingerprint({"seal": frozen["seal_hash"], "hidden": sha(hidden_path.read_bytes()),
                           "evaluator": sha(Path(__file__).read_bytes()), "image": judge.image_digest,
                           "judging_version": judging_version()})
    if hasattr(judge, "cleanup_owned"):
        judge.owner = fingerprint(["hidden", str(root.resolve()), version])
        judge.cleanup_owned()
    destination = root / "evaluations" / version
    result_path = destination / "evaluation.json"
    if result_path.exists():
        existing = read_json(result_path)
        if existing["result_hash"] != fingerprint({k: v for k, v in existing.items() if k != "result_hash"}):
            raise ValueError("Evaluation hash mismatch")
        return existing
    destination.mkdir(parents=True, exist_ok=True)
    store = Store(root, readonly=True)
    rows, outcomes = [], []
    try:
        for job in plan["jobs"]:
            task = hidden[job["task_id"]]
            state = store.load(job["id"])
            assert state is not None
            snapshots = store.snapshots(job["id"])
            for axis, budgets in [("calls", range(1, max(plan["config"]["budgets"]["call_checkpoints"]) + 1)),
                                  ("tokens", plan["config"]["budgets"]["token_checkpoints"])]:
                for budget in budgets:
                    snapshot, censor = checkpoint_snapshot(snapshots, axis, budget, state.stop_reason)
                    key = f"{job['id']}:{axis}:{budget}"
                    partial = 0.
                    if snapshot and snapshot["code_hash"]:
                        # Durable per-checkpoint judging: interruption can reuse this exact evaluation request.
                        checkpoint_path = destination / (sha(key) + ".json")
                        if checkpoint_path.exists():
                            saved = read_json(checkpoint_path)
                            if saved["identity"] != fingerprint([key, snapshot, task.test_hash, version]):
                                raise ValueError("Hidden evaluation checkpoint mismatch")
                            evaluation = saved["evaluation"]
                        else:
                            result = judge.evaluate(store.get(snapshot["code_hash"]).decode(), task.hidden_tests,
                                                    task.comparator, task.limits)
                            if result.infrastructure_error:
                                raise RuntimeError("Hidden judge infrastructure failure; resume same evaluator version")
                            evaluation = result.model_dump(mode="json")
                            write_json(checkpoint_path, {"identity": fingerprint([key, snapshot, task.test_hash, version]),
                                                        "evaluation": evaluation})
                        partial = sum(o["status"] == "PASS" for o in evaluation["outcomes"]) / len(task.hidden_tests)
                        outcomes.append({"key": key, "evaluation": evaluation})
                    rows.append({"trial_id": job["id"], "task_id": job["task_id"], "method": job["method"],
                                 "seed": job["seed"], "axis": axis, "budget": budget,
                                 "solved": partial == 1, "hidden_fraction": partial, "censored": censor,
                                 "code_hash": snapshot["code_hash"] if snapshot else None,
                                 "visible_fraction": snapshot["h"] if snapshot else 0.,
                                 "visible_success_stop": state.stop_reason == "visible_success",
                                 "prefix_tokens": snapshot["tokens"] if snapshot else 0,
                                 "prefix_calls": snapshot["calls"] if snapshot else 0,
                                 "campaign_trial_tokens": state.ledger.tokens,
                                 "campaign_trial_calls": state.ledger.inference_attempts})
        result = {"schema_version": 1, "version": version, "seal_hash": frozen["seal_hash"],
                  "hidden_hash": sha(hidden_path.read_bytes()), "synthetic": synthetic, "created": now(),
                  "rows": rows, "outcomes": outcomes}
        result["result_hash"] = fingerprint(result)
        write_json(result_path, result)
        # Recheck search invariance after hidden judging; no hidden failures can resume search.
        verify_seal(root)
        return result
    finally:
        store.close()
