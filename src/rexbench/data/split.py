import numpy as np

from ..config import Data
from ..judge.compare import compare
from ..types import Case
from ..util import seed_for, sha


def partition(task_id: str, statement: str, pairs: list[tuple[str, str]], comparator, config: Data,
              examples: list[str] | None = None):
    unique: dict[str, Case] = {}
    for inp, out in pairs:
        key = sha(inp)  # Exact UTF-8 input bytes, never whitespace normalization.
        if key in unique and not compare(unique[key].output, out, comparator):
            raise ValueError("conflicting_outputs")
        unique.setdefault(key, Case(id=f"{task_id}:{key}", input=inp, output=out))
    cases = list(unique.values())
    order = np.random.default_rng(seed_for("split", config.split_seed, task_id)).permutation(len(cases))
    cases = [cases[int(i)] for i in order]
    relaxed_statement = " ".join(statement.split())
    known = set(examples or [])
    repair: list[Case] = []
    rest: list[Case] = []
    for case in cases:
        relaxed = " ".join(case.input.split())
        # Relaxed matching is ONLY a conservative leakage flag, never test identity/comparator.
        visible = case.input in known or bool(relaxed and relaxed in relaxed_statement)
        (repair if visible else rest).append(case)
    forced = [c.id for c in repair]
    if len(repair) > config.max_repair_tests:
        raise ValueError("too_many_statement_examples")
    target = config.repair_target_tests or config.max_repair_tests
    required = max(config.min_repair_tests, min(target, len(cases) - config.min_hidden_tests))
    take = max(0, required - len(repair))
    repair += rest[:take]
    hidden = rest[take:take + config.max_hidden_tests]
    if len(repair) < config.min_repair_tests or len(hidden) < config.min_hidden_tests:
        raise ValueError("insufficient_disjoint_tests")
    return repair, hidden, {"forced_example_ids": forced, "deduplicated": len(pairs) - len(unique),
                            "unused_tests": len(cases) - len(repair) - len(hidden)}
