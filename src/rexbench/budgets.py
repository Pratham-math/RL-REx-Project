from dataclasses import dataclass

from .types import GenerationResult, Ledger


@dataclass
class CostEstimator:
    chars_per_token: float = 4.
    output_tokens: float = 512.

    def estimate(self, prompt: str) -> float:
        return max(1., len(prompt) / self.chars_per_token + self.output_tokens)

    def observe(self, prompt: str, result: GenerationResult):
        if result.input_tokens is not None and result.input_tokens > 0:
            ratio = min(10., max(1., len(prompt) / result.input_tokens))
            self.chars_per_token = .8 * self.chars_per_token + .2 * ratio
        if result.output_tokens is not None:
            self.output_tokens = .8 * self.output_tokens + .2 * result.output_tokens


def charge(ledger: Ledger, result: GenerationResult):
    if result.input_tokens is None or result.output_tokens is None:
        ledger.unknown_usage += 1
    ledger.prompt_tokens += result.input_tokens or 0
    ledger.output_tokens += result.output_tokens or 0
    ledger.model_seconds += result.latency_seconds
    ledger.reservations = max(0, ledger.reservations - 1)


def checkpoint_snapshot(snapshots: list[dict], axis: str, budget: int, stop: str | None) -> tuple[dict | None, bool]:
    """Select only completed prefixes. Absorbing repair success extends to all future budgets."""
    if axis not in ("calls", "tokens"):
        raise ValueError("Unknown checkpoint axis")
    if axis == "tokens" and any(s["tokens"] is None for s in snapshots):
        return None, True
    valid = [s for s in snapshots if s[axis] <= budget]
    chosen = valid[-1] if valid else None
    covered = bool(snapshots) and (snapshots[-1][axis] >= budget or stop == "visible_success")
    return chosen, not covered
