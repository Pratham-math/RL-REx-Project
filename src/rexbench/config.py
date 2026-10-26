from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml
from pydantic import Field, model_validator

from .types import Limits, Record
from .util import fingerprint

CORE = ["resample", "greedy", "rex", "rex_progress", "rex_cost", "rex_progress_cost"]
METHODS = CORE + ["bfs", "fixed_width"]


class Experiment(Record):
    name: str = "apps_main_v1"
    track: Literal["controlled_extension", "synthetic"] = "controlled_extension"
    methods: list[str] = Field(default_factory=lambda: CORE.copy(), min_length=1)
    seeds: list[int] = Field(default_factory=lambda: [0, 1, 2], min_length=1)
    primary_comparison: str = "rex_progress_cost_vs_rex"
    primary_metric: str = "hidden_success_at_16_calls"

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.methods)) != len(self.methods) or set(self.methods) - set(METHODS):
            raise ValueError("Unknown or duplicate methods")
        if len(set(self.seeds)) != len(self.seeds) or any(s < 0 for s in self.seeds):
            raise ValueError("Seeds must be unique and nonnegative")
        return self


class Data(Record):
    raw_train: str = "data/raw/APPS/train"
    raw_test: str = "data/raw/APPS/test"
    development_source_partition: Literal["train", "test"] = "train"
    exclude_task_ids: list[str] = Field(default_factory=list)
    dev_count: int = Field(default=10, ge=0)
    evaluation_count: int = Field(default=30, ge=0)
    difficulty: list[str] = Field(default_factory=lambda: ["interview"], min_length=1)
    split_seed: int = Field(default=2026, ge=0)
    min_repair_tests: int = Field(default=3, gt=0)
    min_hidden_tests: int = Field(default=5, gt=0)
    max_repair_tests: int = Field(default=10, gt=0)
    repair_target_tests: int | None = Field(default=None, gt=0)
    max_hidden_tests: int = Field(default=50, gt=0)
    io_mode: Literal["stdio"] = "stdio"
    require_audit: bool = True
    repair_file: str = "data/final_repair.jsonl"
    manifest: str = "data/manifest.json"
    source_url: str = "https://github.com/hendrycks/apps"
    source_revision: str | None = None
    license: str | None = None
    audit_only_references: str = "data/audit_private/references.jsonl"
    manual_audit: str = "data/manual_audit.json"

    @model_validator(mode="after")
    def limits(self):
        if self.dev_count + self.evaluation_count < 1:
            raise ValueError("At least one development or evaluation task required")
        if self.development_source_partition == "test" and self.dev_count and self.evaluation_count:
            raise ValueError("Test-sourced development must be prepared separately and reserved before final selection")
        if self.min_repair_tests > self.max_repair_tests or self.min_hidden_tests > self.max_hidden_tests:
            raise ValueError("Test minima exceed maxima")
        if self.repair_target_tests is not None and not self.min_repair_tests <= self.repair_target_tests <= self.max_repair_tests:
            raise ValueError("Repair target must lie between repair minimum and maximum")
        return self


class Model(Record):
    backend: Literal["mock", "ollama"] = "ollama"
    endpoint: str = "http://localhost:11434"
    name: str = "qwen2.5-coder:7b"
    digest: str | None = None
    temperature: float = Field(default=1, ge=0)
    max_output_tokens: int = Field(default=2048, gt=0)
    context_tokens: int = Field(default=16384, gt=0)
    request_timeout_seconds: float = Field(default=900, gt=0)
    mock_script: str = "tests/fixtures/model.json"

    @model_validator(mode="after")
    def local_only(self):
        parsed = urlparse(self.endpoint)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Endpoint must not contain credentials/query/fragment")
        if parsed.hostname not in ("localhost", "127.0.0.1", "::1") or parsed.scheme != "http":
            raise ValueError("v1 supports a local Ollama endpoint only; hosted spending unsupported")
        if self.max_output_tokens >= self.context_tokens:
            raise ValueError("Output cap must leave input context")
        return self


class Policy(Record):
    C: float = Field(default=20, ge=0)
    eta: float = Field(default=.5, ge=0, le=1)
    gamma: float = Field(default=.5, ge=0, le=1)
    greedy_root_score: float = Field(default=.5, ge=0, le=1)
    bfs_branching: int = Field(default=2, gt=0)
    fixed_width: int = Field(default=4, gt=0)
    arm_identity: Literal["generation"] = "generation"
    terminal_rule: Literal["first_full_repair_pass"] = "first_full_repair_pass"
    candidate_tie_rule: Literal["earliest_created"] = "earliest_created"
    terminal_update: Literal["upstream"] = "upstream"

    def toggles(self, method: str) -> tuple[float, float]:
        if method not in METHODS:
            raise ValueError("Unknown method")
        return (self.eta if method in ("rex_progress", "rex_progress_cost") else 0.,
                self.gamma if method in ("rex_cost", "rex_progress_cost") else 0.)


class Judge(Limits):
    backend: Literal["docker", "mock"] = "docker"
    image: str = "rexbench-runner:local"
    image_digest: str | None = None
    evaluation_cache: Literal[False] = False
    mock_script: str = "tests/fixtures/judge.json"

    def limits_only(self) -> Limits:
        return Limits.model_validate({k: getattr(self, k) for k in Limits.model_fields})


class Budgets(Record):
    call_checkpoints: list[int] = Field(default_factory=lambda: [1, 2, 4, 8, 16], min_length=1)
    token_checkpoints: list[int] = Field(default_factory=lambda: [2048, 4096, 8192])
    token_mode: Literal["completed_generation_checkpoints"] = "completed_generation_checkpoints"
    coverage_extension_call_ceiling: int = Field(default=64, gt=0)
    max_dispatched_calls: int = Field(default=8640, gt=0)
    max_external_spend_usd: float = Field(default=0, ge=0, le=0)
    campaign_wall_hours: float = Field(default=12, gt=0)

    @model_validator(mode="after")
    def grids(self):
        for grid in [self.call_checkpoints, self.token_checkpoints]:
            if grid != sorted(set(grid)) or any(x < 1 for x in grid):
                raise ValueError("Budget grids must be sorted, positive and unique")
        if self.coverage_extension_call_ceiling < max(self.call_checkpoints):
            raise ValueError("Extension ceiling below call study")
        return self


class Execution(Record):
    workers: Literal[1] = 1
    model_concurrency: Literal[1] = 1
    resume: bool = True
    require_exact_usage_for_cost_report: Literal[True] = True


class Report(Record):
    bootstrap_samples: int = Field(default=10000, gt=0)
    bootstrap_seed: int = Field(default=2026, ge=0)
    require_complete_matrix: Literal[True] = True
    emit_formats: list[Literal["csv", "json", "png", "svg", "html"]] = ["csv", "json", "png", "svg", "html"]


class Config(Record):
    experiment: Experiment = Field(default_factory=Experiment)
    data: Data = Field(default_factory=Data)
    model: Model = Field(default_factory=Model)
    policy: Policy = Field(default_factory=Policy)
    judge: Judge = Field(default_factory=Judge)
    budgets: Budgets = Field(default_factory=Budgets)
    execution: Execution = Field(default_factory=Execution)
    report: Report = Field(default_factory=Report)

    @model_validator(mode="after")
    def synthetic(self):
        if (self.model.backend == "mock" or self.judge.backend == "mock") and self.experiment.track != "synthetic":
            raise ValueError("Any mock component requires the synthetic track")
        return self

    @property
    def config_hash(self):
        return fingerprint(self.model_dump(mode="json"))


def load_config(path: Path) -> Config:
    class UniqueLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node)
            if key in result:
                raise ValueError(f"Duplicate configuration key: {key}")
            result[key] = loader.construct_object(value_node)
        return result

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    return Config.model_validate(yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader))
