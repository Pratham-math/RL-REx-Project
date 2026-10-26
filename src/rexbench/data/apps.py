from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..types import HiddenTask, RepairTask, suite_hash
from ..util import fingerprint, jsonl, now, read_json, seed_for, sha, write_json, write_jsonl
from .split import partition


def load_repair(path: Path) -> list[RepairTask]:
    rows = [RepairTask.model_validate(row) for row in jsonl(path)]
    if not rows or len({r.task_id for r in rows}) != len(rows):
        raise ValueError("Empty repair file or duplicate task IDs")
    return rows


def prepare_dataset(config: Config, output: Path):
    data = config.data
    if output.exists():
        raise FileExistsError("Use a new dataset output directory")
    if not data.source_revision or not data.license:
        raise ValueError("Declare source_revision (archive hash/release) and license before import")
    manual_path = Path(data.manual_audit)
    if not manual_path.is_file():
        raise ValueError("Manual audit file required: comparator justification, examples_reviewed, vetted reference indices")
    manual = read_json(manual_path)
    pools: dict[str, list] = {"dev": [], "final": []}
    exclusions, references, identities, source_files = [], [], set(), {}
    for split, root in [("dev", Path(data.raw_train)), ("final", Path(data.raw_test))]:
        if (data.dev_count if split == "dev" else data.evaluation_count) == 0:
            continue
        paths = sorted(root.rglob("question.txt"))
        if not paths:
            raise FileNotFoundError(f"Official APPS partition unavailable: {root}")
        for path in paths:
            original_id = path.parent.relative_to(root).as_posix()
            task_id = ((data.development_source_partition + "/") if split == "dev" else "test/") + original_id
            try:
                if task_id in data.exclude_task_ids:
                    raise ValueError("reserved_development_task")
                raw_statement = path.read_bytes()
                statement = raw_statement.decode("utf-8")
                io_path, meta_path = path.with_name("input_output.json"), path.with_name("metadata.json")
                io, meta = read_json(io_path), read_json(meta_path)
                for item in [path, io_path, meta_path]:
                    source_files[f"{task_id}/{item.name}"] = sha(item.read_bytes())
                if meta["difficulty"] not in data.difficulty:
                    raise ValueError("difficulty")
                if io.get("fn_name"):
                    raise ValueError("function_call")
                if not io.get("inputs") or len(io["inputs"]) != len(io.get("outputs", [])):
                    raise ValueError("missing_or_mismatched_tests")
                pairs = list(zip(io["inputs"], io["outputs"]))
                if not all(isinstance(x, str) and isinstance(y, str) for x, y in pairs):
                    raise ValueError("non_string_or_alternative_output")
                if any(len(x.encode()) > 20000 or len(y.encode()) > 20000 for x, y in pairs):
                    raise ValueError("oversize_case")
                review = manual.get(task_id)
                if not review or not review.get("examples_reviewed") or not review.get("comparator_justification"):
                    raise ValueError("manual_comparator_or_example_review_pending")
                comparator = review["comparator"]
                if comparator not in ("tokens_v1", "text_v1", "lines_v1"):
                    raise ValueError("unsupported_comparator")
                statement_identity = sha(" ".join(statement.split()))
                source_identity = meta.get("url") or meta.get("source_url") or f"apps:{original_id}:{statement_identity}"
                if statement_identity in identities or source_identity in identities:
                    raise ValueError("cross_split_duplicate")
                repair, hidden, details = partition(task_id, statement, pairs, comparator, data, review.get("examples", []))
                solution_path = path.with_name("solutions.json")
                solutions = read_json(solution_path)
                indices = review.get("vetted_reference_indices", [])
                if not indices or any(type(i) is not int or i < 0 or i >= len(solutions) for i in indices):
                    raise ValueError("vetted_references_missing")
                vetted = [solutions[i] for i in indices]
                if not all(isinstance(s, str) and s for s in vetted):
                    raise ValueError("invalid_reference")
                public = RepairTask(task_id=task_id, source=data.source_url, revision=data.source_revision,
                                    difficulty=meta["difficulty"], statement=statement, repair_tests=repair,
                                    comparator=comparator, limits=config.judge.limits_only(),
                                    statement_hash=sha(statement), test_hash=suite_hash(repair))
                private = HiddenTask(task_id=task_id, hidden_tests=hidden, comparator=comparator,
                                     limits=public.limits, test_hash=suite_hash(hidden))
                pools[split].append((public, private, details))
                identities.update([statement_identity, source_identity])
                references.append({"task_id": task_id, "solutions": vetted})
            except (ValueError, KeyError, OSError, IndexError, TypeError) as exc:
                exclusions.append({"task_id": task_id, "reason": str(exc)[:200]})
    selected = {}
    for split, count in [("dev", data.dev_count), ("final", data.evaluation_count)]:
        ordered = sorted(pools[split], key=lambda x: seed_for("subset", data.split_seed, x[0].task_id))
        if len(ordered) < count:
            raise ValueError(f"Only {len(ordered)} eligible {split} tasks; need {count}. Exclusions: {exclusions[:10]}")
        selected[split] = ordered[:count]
    output.mkdir(parents=True)
    ids, details = {}, {}
    for split, tasks in selected.items():
        ids[split] = [p.task_id for p, _, _ in tasks]
        details.update({p.task_id: d for p, _, d in tasks})
        write_jsonl(output / f"{split}_repair.jsonl", [p.model_dump(mode="json") for p, _, _ in tasks])
        write_jsonl(output / f"{split}_hidden.jsonl", [h.model_dump(mode="json") for _, h, _ in tasks])
    selected_ids = set(ids["dev"] + ids["final"])
    reference_path = output / "audit_private" / "references.jsonl"
    write_jsonl(reference_path, [r for r in references if r["task_id"] in selected_ids])
    files = {p.name: sha(p.read_bytes()) for p in output.glob("*.jsonl")}
    manifest = {"schema_version": 1, "source": data.source_url, "revision": data.source_revision,
                "accessed": now(), "license": data.license, "source_file_hashes": source_files,
                "source_tree_hash": fingerprint(source_files), "line_endings": "preserved in decoded UTF-8 strings",
                "task_ids": ids, "files": files, "details": details, "exclusions": exclusions,
                "development_source_partition": data.development_source_partition,
                "excluded_task_ids": data.exclude_task_ids,
                "manual_review_hash": sha(manual_path.read_bytes()), "references_hash": sha(reference_path.read_bytes()),
                "audit_references": "audit_private/references.jsonl", "audit_status": "pending",
                "selection": "keyed SHA-256 order within explicitly declared source/role pools; before model outcomes",
                "near_duplicates": "manual review required; normalized exact statement and source URL checks only"}
    write_json(output / "manifest.json", manifest)
    return manifest
