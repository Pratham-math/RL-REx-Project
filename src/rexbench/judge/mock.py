from ..types import EvaluationResult, Status, TestOutcome
from ..util import fingerprint


class MockJudge:
    """Synthetic status table; never parses or executes candidate source."""

    def __init__(self, script: dict):
        self.script = script
        self.image_digest = "synthetic:" + fingerprint(script)

    def evaluate(self, code, cases, comparator, limits):
        statuses = self.script.get(code, ["WRONG_ANSWER"] * len(cases))
        if isinstance(statuses, dict):
            statuses = [statuses.get(c.id, statuses.get("default", "WRONG_ANSWER")) for c in cases]
        if len(statuses) != len(cases):
            raise ValueError("Synthetic outcomes must match the entire suite")
        return EvaluationResult(outcomes=[TestOutcome(case_id=c.id, status=Status(s),
                                                      lifecycle={"synthetic": True}) for c, s in zip(cases, statuses)],
                                execution_fingerprint=fingerprint([code, [c.model_dump() for c in cases],
                                                                  comparator, limits.model_dump(), self.image_digest]))
