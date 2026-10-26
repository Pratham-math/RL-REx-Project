from pathlib import Path
from typing import Any

from ..types import HiddenTask
from ..util import fingerprint, jsonl, now, read_json, sha, write_json
from .apps import load_repair


def judging_version():
    package = Path(__file__).resolve().parents[1]
    return fingerprint({name: sha((package / name).read_bytes()) for name in
                        ["judge/compare.py", "judge/docker.py", "judge/mock.py", "types.py"]})


def audit_identity(manifest_path: Path, image_digest: str):
    return fingerprint(["audit_v2", sha(manifest_path.read_bytes()), image_digest,
                        sha(Path(__file__).read_bytes()), judging_version()])


def audit_dataset(manifest_path: Path, judge, out: Path):
    manifest = read_json(manifest_path)
    root = manifest_path.parent
    identity = audit_identity(manifest_path, judge.image_digest)
    for name, digest in manifest["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha(path.read_bytes()) != digest:
            raise ValueError(f"Dataset hash mismatch: {name}")
    references_path = root / manifest["audit_references"]
    if not references_path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Reference path leaves dataset directory")
    if sha(references_path.read_bytes()) != manifest["references_hash"]:
        raise ValueError("Reference hash mismatch")
    if out.exists():
        existing = read_json(out)
        if existing.get("audit_identity") != identity or existing.get("result_hash") != fingerprint(
                {k: v for k, v in existing.items() if k != "result_hash"}):
            raise ValueError("Existing audit differs; choose a new immutable output")
        return existing
    references = {r["task_id"]: r["solutions"] for r in jsonl(references_path)}
    checks = []
    for split in ("dev", "final"):
        public = load_repair(root / f"{split}_repair.jsonl") if manifest["task_ids"][split] else []
        hidden_rows = [HiddenTask.model_validate(r) for r in jsonl(root / f"{split}_hidden.jsonl")]
        hidden = {h.task_id: h for h in hidden_rows}
        if len(hidden) != len(hidden_rows):
            raise ValueError("Duplicate hidden task IDs")
        if set(hidden) != {p.task_id for p in public}:
            raise ValueError("Repair/hidden task mismatch")
        for task in public:
            other = hidden[task.task_id]
            if {sha(c.input) for c in task.repair_tests} & {sha(c.input) for c in other.hidden_tests}:
                raise ValueError("Cross-suite input leakage")
            if task.comparator != other.comparator or task.limits != other.limits:
                raise ValueError("Comparator/limit mismatch")
            statuses: list[dict[str, Any]] = []
            for code in references[task.task_id]:
                # Repeated reference runs detect some nondeterminism; never enter the search store.
                runs = []
                for repetition in range(2):
                    key = fingerprint([identity, task.task_id, sha(code), task.test_hash, other.test_hash, repetition])
                    path = out.parent / "audit_checkpoints" / (key + ".json")
                    if path.exists():
                        saved = read_json(path)
                        if saved["identity"] != key or fingerprint(saved["evaluation"]) != saved["evaluation_hash"]:
                            raise ValueError("Audit checkpoint hash mismatch")
                        from ..types import EvaluationResult
                        result = EvaluationResult.model_validate(saved["evaluation"])
                    else:
                        result = judge.evaluate(code, task.repair_tests + other.hidden_tests, task.comparator, task.limits)
                        if result.infrastructure_error:
                            raise RuntimeError("Reference judge infrastructure failure; resume the same audit")
                        payload = result.model_dump(mode="json")
                        write_json(path, {"identity": key, "evaluation": payload, "evaluation_hash": fingerprint(payload)})
                    runs.append(result)
                statuses.append({"code_hash": sha(code), "passes": [r.h == 1 and not r.infrastructure_error for r in runs],
                                 "nondeterministic_output_detected": [o.stdout_hash for o in runs[0].outcomes] !=
                                     [o.stdout_hash for o in runs[1].outcomes],
                                 "outcomes": [r.model_dump(mode="json") for r in runs]})
            checks.append({"task_id": task.task_id, "references": statuses,
                           "passed": bool(statuses) and all(all(r["passes"]) for r in statuses)})
    passed = bool(checks) and all(c["passed"] for c in checks)
    report = {"schema_version": 1, "created": now(), "passed": passed, "checks": checks, "audit_identity": identity,
              "manifest_hash": sha(manifest_path.read_bytes()), "image_digest": judge.image_digest,
              "synthetic": judge.image_digest.startswith("synthetic:"),
              "sample_audit": "manual review bound by manifest manual_review_hash; conservative example forcing",
              "limitations": "No complete proof against near duplicates, contamination or nondeterminism"}
    report["result_hash"] = fingerprint(report)
    write_json(out, report)
    return report
