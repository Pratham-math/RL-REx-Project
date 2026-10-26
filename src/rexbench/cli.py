from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError


def parser():
    root = argparse.ArgumentParser(prog="rexbench", description="Auditable local REx code-repair harness")
    commands = root.add_subparsers(dest="command", required=True)
    p = commands.add_parser("doctor", help="Inspect capabilities; no model inference")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("reports/doctor.json"))
    p = commands.add_parser("dataset", help="Prepare and audit separate repair/hidden datasets")
    ds = p.add_subparsers(dest="dataset_command", required=True)
    p = ds.add_parser("fetch", help="Download/hash the official APPS archive and safely extract it")
    p.add_argument("--out", type=Path, default=Path("data/raw"))
    p.add_argument("--sha256")
    p.add_argument("--download-seconds", type=float, default=300)
    p = ds.add_parser("fetch-hf", help="Freeze an explicitly labeled small APPS mirror snapshot")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--split", choices=["train", "test"], default="train")
    p.add_argument("--offset", type=int, required=True)
    p.add_argument("--length", type=int, default=100)
    p.add_argument("--revision")
    p = ds.add_parser("prepare", help="Import official local APPS; requires manual comparator/example metadata")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("data"))
    p = ds.add_parser("audit", help="Validate vetted references in the isolated runner")
    p.add_argument("--config", type=Path, default=Path("configs/main.yaml"))
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p = commands.add_parser("parity", help="Run pinned upstream fake-domain conformance")
    p.add_argument("--upstream", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p = commands.add_parser("experiment", help="Plan a matrix without model inference")
    sub = p.add_subparsers(dest="experiment_command", required=True)
    p = sub.add_parser("plan", help="Freeze matrix and resource bounds")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--pilot-resources", type=Path)
    p = commands.add_parser("run", help="Execute a frozen plan with serial trials")
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--experiment", type=Path)
    p = commands.add_parser("reconcile", help="Import proven response/usage evidence for the same uncertain request")
    p.add_argument("--experiment", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    for command, help_text in [("resume", "Recover persisted work; never replay independent model draws"),
                               ("status", "Inspect the expected trial matrix and resource ledger"),
                               ("seal", "Hash complete search evidence for offline evaluation")]:
        p = commands.add_parser(command, help=help_text)
        p.add_argument("--experiment", type=Path, required=True)
    p = commands.add_parser("evaluate", help="Judge frozen returned solutions against hidden suites")
    p.add_argument("--experiment", type=Path, required=True)
    p.add_argument("--hidden", type=Path, required=True)
    p = commands.add_parser("report", help="Coverage-checked statistics/plots from stored hidden results")
    p.add_argument("--experiment", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--evaluation")
    p = commands.add_parser("trace", help="Inert self-contained replay of recorded events")
    p.add_argument("--experiment", type=Path, required=True)
    p.add_argument("--select", default="representative")
    p.add_argument("--evaluation")
    p.add_argument("--out", type=Path, required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "doctor":
            from .doctor import doctor
            result = doctor(args.config, args.out)
        elif args.command == "dataset":
            if args.dataset_command == "fetch-hf":
                from .data.mirror import fetch_mirror
                print(json.dumps(fetch_mirror(args.out, args.split, args.offset, args.length, args.revision)))
                return 0
            if args.dataset_command == "fetch":
                from .data.fetch import fetch_apps
                print(json.dumps(fetch_apps(args.out, args.sha256, args.download_seconds)))
                return 0
            from .config import load_config
            config = load_config(args.config)
            if args.dataset_command == "prepare":
                from .data.apps import prepare_dataset
                result = prepare_dataset(config, args.out)
            else:
                from .data.audit import audit_dataset
                from .judge.docker import DockerJudge
                result = audit_dataset(args.manifest, DockerJudge(config.judge), args.out)
        elif args.command == "parity":
            from .parity import parity
            result = parity(args.upstream, args.out)
        elif args.command == "experiment":
            from .experiment import make_plan
            result = make_plan(args.config, args.out, args.pilot_resources)
        elif args.command in ("run", "resume"):
            from .experiment import execute
            result = execute(args.plan, args.experiment) if args.command == "run" else execute(args.experiment / "plan.json", args.experiment)
        elif args.command == "reconcile":
            from .reconcile import reconcile
            result = reconcile(args.experiment, args.evidence)
        elif args.command == "status":
            from .experiment import status
            result = status(args.experiment)
        elif args.command == "seal":
            from .evaluate import seal
            from .experiment import writer_lock
            with writer_lock(args.experiment):
                result = seal(args.experiment)
        elif args.command == "evaluate":
            from .config import Config
            from .evaluate import evaluate
            from .judge.docker import DockerJudge
            from .judge.mock import MockJudge
            from .util import read_json
            from .experiment import writer_lock
            config = Config.model_validate(read_json(args.experiment / "resolved_config.json")["config"])
            judge = MockJudge(read_json(Path(config.judge.mock_script))) if config.judge.backend == "mock" else DockerJudge(config.judge)
            with writer_lock(args.experiment):
                result = evaluate(args.experiment, args.hidden, judge)
        elif args.command == "report":
            from .report import report
            result = report(args.experiment, args.out, args.evaluation)
        elif args.command == "trace":
            from .replay import replay
            result = replay(args.experiment, args.select, args.out, args.evaluation)
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        if args.command == "doctor" and not result["ready"]:
            return 1
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        # Validation exceptions normally echo rejected input, which could contain URL credentials.
        message = "; ".join(".".join(str(x) for x in item["loc"]) + ": " + item["msg"]
                            for item in exc.errors(include_input=False, include_url=False)) if isinstance(exc, ValidationError) else str(exc)
        print(json.dumps({"error": type(exc).__name__, "message": message}), file=sys.stderr)
        return 130 if isinstance(exc, KeyboardInterrupt) else 2


if __name__ == "__main__":
    raise SystemExit(main())
