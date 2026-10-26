from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .util import fingerprint, sha


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_assignment=True)
    schema_version: Literal[1] = 1


class Limits(Record):
    memory_mib: int = Field(default=256, gt=0)
    cpus: float = Field(default=1, gt=0)
    pids_limit: int = Field(default=32, gt=0)
    tmp_mib: int = Field(default=16, gt=0)
    cpu_seconds: int = Field(default=2, gt=0)
    program_wall_seconds: float = Field(default=5, gt=0)
    startup_seconds: float = Field(default=30, gt=0)
    stdout_bytes: int = Field(default=65536, gt=0)
    stderr_bytes: int = Field(default=16384, gt=0)


class Case(Record):
    id: str = Field(min_length=1)
    input: str
    output: str

    @model_validator(mode="after")
    def valid_utf8(self):
        self.input.encode("utf-8")
        self.output.encode("utf-8")
        return self


Comparator = Literal["tokens_v1", "text_v1", "lines_v1"]


class RepairTask(Record):
    task_id: str = Field(min_length=1)
    source: str
    revision: str
    difficulty: str
    statement: str = Field(min_length=1)
    language: Literal["python"] = "python"
    io_mode: Literal["stdio"] = "stdio"
    repair_tests: list[Case] = Field(min_length=1)
    comparator: Comparator
    limits: Limits = Field(default_factory=Limits)
    statement_hash: str
    test_hash: str

    @model_validator(mode="after")
    def check_hashes(self):
        validate_cases(self.repair_tests)
        if self.statement_hash != sha(self.statement) or self.test_hash != suite_hash(self.repair_tests):
            raise ValueError("Repair data hash mismatch")
        return self


class HiddenTask(Record):
    task_id: str = Field(min_length=1)
    hidden_tests: list[Case] = Field(min_length=1)
    comparator: Comparator
    limits: Limits = Field(default_factory=Limits)
    test_hash: str

    @model_validator(mode="after")
    def check_hashes(self):
        validate_cases(self.hidden_tests)
        if self.test_hash != suite_hash(self.hidden_tests):
            raise ValueError("Hidden data hash mismatch")
        return self


def validate_cases(cases: list[Case]):
    if len({c.id for c in cases}) != len(cases):
        raise ValueError("Duplicate test IDs")
    if len({sha(c.input) for c in cases}) != len(cases):
        raise ValueError("Duplicate test inputs")


def suite_hash(cases: list[Case]) -> str:
    return fingerprint([c.model_dump(mode="json") for c in cases])


class Message(Record):
    role: Literal["system", "user", "assistant"]
    content: str


class GenerationRequest(Record):
    experiment_id: str
    trial_id: str
    attempt_id: str
    messages: list[Message] = Field(min_length=1)
    prompt_hash: str
    backend: str
    model_digest: str
    temperature: float = Field(ge=0)
    output_limit: int = Field(gt=0)
    context_tokens: int = Field(gt=0)
    generation_seed: int = Field(ge=0)
    kind: Literal["generation", "repair"]


class GenerationResult(Record):
    request_id: str
    text: str
    raw: dict[str, Any]
    finish_reason: str
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    usage_definition: str
    started: str
    finished: str
    latency_seconds: float = Field(ge=0)
    backend_error: str | None = None


class Status(StrEnum):
    PASS = "PASS"
    WRONG_ANSWER = "WRONG_ANSWER"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    TIME_LIMIT = "TIME_LIMIT"
    MEMORY_LIMIT = "MEMORY_LIMIT"
    OUTPUT_LIMIT = "OUTPUT_LIMIT"
    INFRA_ERROR = "INFRA_ERROR"


class TestOutcome(Record):
    case_id: str
    status: Status
    stdout_hash: str = ""
    stdout_preview: str = ""
    stderr: str = ""
    exit_code: int | None = None
    signal: int | None = None
    cpu_seconds: float | None = Field(default=None, ge=0)
    wall_seconds: float = Field(default=0, ge=0)
    startup_seconds: float = Field(default=0, ge=0)
    peak_memory_bytes: int | None = Field(default=None, ge=0)
    lifecycle: dict[str, Any] = Field(default_factory=dict)


class EvaluationResult(Record):
    outcomes: list[TestOutcome] = Field(min_length=1)
    execution_fingerprint: str

    @property
    def infrastructure_error(self) -> bool:
        return any(x.status == Status.INFRA_ERROR for x in self.outcomes)

    @property
    def passed(self) -> int:
        return sum(x.status == Status.PASS for x in self.outcomes)

    @property
    def h(self) -> float:
        return self.passed / len(self.outcomes)


class ArmState(Record):
    arm_id: str
    code_hash: str | None = None
    generation_id: str | None = None
    parent_id: str | None = None
    depth: int = Field(default=0, ge=0)
    h: float = Field(default=0, ge=0, le=1)
    alpha: float = Field(default=1, gt=0)
    beta: float = Field(default=1, gt=0)
    pulls: int = Field(default=0, ge=0)
    order: int = Field(default=0, ge=0)
    evaluation: EvaluationResult | None = None


class Ledger(Record):
    http_attempts: int = Field(default=0, ge=0)
    inference_attempts: int = Field(default=0, ge=0)
    usable_completions: int = Field(default=0, ge=0)
    policy_steps: int = Field(default=0, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    unknown_usage: int = Field(default=0, ge=0)
    reservations: int = Field(default=0, ge=0)
    model_seconds: float = Field(default=0, ge=0)
    judge_seconds: float = Field(default=0, ge=0)
    orchestration_seconds: float = Field(default=0, ge=0)
    external_spend_usd: float = Field(default=0, ge=0)

    @property
    def tokens(self) -> int | None:
        return None if self.unknown_usage else self.prompt_tokens + self.output_tokens


class SearchCheckpoint(Record):
    trial_id: str
    iteration: int = Field(default=0, ge=0)
    arms: list[ArmState] = Field(default_factory=lambda: [ArmState(arm_id="root")])
    best_id: str | None = None
    rng_state: dict[str, Any]
    estimator: dict[str, float] = Field(default_factory=lambda: {"chars_per_token": 4., "output_tokens": 512.})
    policy_state: dict[str, Any] = Field(default_factory=dict)
    ledger: Ledger = Field(default_factory=Ledger)
    committed_event: int = Field(default=0, ge=0)
    stop_reason: str | None = None


class TrialManifest(Record):
    trial_id: str
    task_id: str
    method: str
    seed: int = Field(ge=0)
    config_hash: str
    status: str = "planned"
    stop_reason: str | None = None
    planned_limits: dict[str, Any]
    consumed: Ledger = Field(default_factory=Ledger)
    checkpoint: str | None = None


class ExperimentManifest(Record):
    experiment_id: str
    config_hash: str
    data_hash: str
    environment: dict[str, Any]
    expected: list[dict[str, Any]]
    status: str = "planned"
    seal: str | None = None
