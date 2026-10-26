from __future__ import annotations

import re

from ..types import ArmState, RepairTask, Status
from ..util import fingerprint, seed_for

VERSION = "prompts_v1-feedback_2000_2000_2000_1000-keyed"
PARSER_VERSION = "parser_v1"
GENERATION = """Write a complete Python 3 program using only the standard library.
Read from standard input and write only the required output to standard output.
Return one Python code block containing the complete program.

Problem:
{statement}"""
REPAIR = """Write a corrected complete Python 3 program using only the standard library.
Read from standard input and write only the required output to standard output.
Return one Python code block containing the complete program.

Problem:
{statement}

Candidate program:
<candidate>
{candidate_code}
</candidate>

One failed repair test:
{failure_feedback}

Fix the program for the full specification, including edge cases."""


def template_hash() -> str:
    return fingerprint([VERSION, GENERATION, REPAIR, PARSER_VERSION])


def bounded(text: str, maximum: int) -> str:
    return text if len(text) <= maximum else text[:maximum] + "\n[TRUNCATED: original is longer]"


def prepare(task: RepairTask, arm: ArmState, code: str, seed: int, iteration: int) -> tuple[str, str | None]:
    if arm.arm_id == "root":
        return GENERATION.format(statement=task.statement), None
    failed = [o for o in arm.evaluation.outcomes if o.status != Status.PASS] if arm.evaluation else []
    if not failed:
        feedback = "INVALID_COMPLETION: no usable program was returned."
        case_id = None
    else:
        # A keyed independent stream: enumerating other arms cannot perturb an existing prompt.
        outcome = failed[seed_for("feedback", task.task_id, seed, iteration, arm.arm_id) % len(failed)]
        case = next(t for t in task.repair_tests if t.id == outcome.case_id)
        case_id = case.id
        feedback = (f"Failure: {outcome.status}\nInput:\n{bounded(case.input, 2000)}\n"
                    f"Expected output:\n{bounded(case.output, 2000)}\n"
                    f"Actual output:\n{bounded(outcome.stdout_preview, 2000)}\n"
                    f"Stderr/details:\n{bounded(outcome.stderr, 1000)}")
    return REPAIR.format(statement=task.statement, candidate_code=code, failure_feedback=feedback), case_id


def extract_code(text: str) -> tuple[str | None, str]:
    try:
        text.encode("utf-8", errors="strict")
    except UnicodeError:
        return None, "INVALID_COMPLETION"
    value = text.strip()
    if not value:
        return None, "INVALID_COMPLETION"
    if "```" in value:
        match = re.fullmatch(r"```(?:python|py)?[ \t]*\r?\n(.*?)\r?\n?```", value, flags=re.S)
        if not match or "```" in match.group(1) or not match.group(1).strip():
            return None, "INVALID_COMPLETION"
        return match.group(1), "EXTRACTED"
    # A lexical admission rule only. Python syntax is checked exclusively in the runner.
    start = r"(?:\#|import\s|from\s|def\s|class\s|async\s|if\s|for\s|while\s|try:|with\s|raise\s|[A-Za-z_]\w*\s*(?:\(|=|:|\[)|['\"]{3})"
    if not re.match(start, value) or re.search(r"(?m)^\s*(?:Here is|The code|This program|Explanation:)", value):
        return None, "INVALID_COMPLETION"
    return value, "EXTRACTED"


def admissible(prompt: str, context: int, output: int) -> bool:
    # Unverified conservative byte allowance plus 256 envelope tokens. No strict-cap claim.
    return len(prompt.encode("utf-8")) + 256 + output <= context
