"""Run the public synthetic workflow; retain every CLI response as verification evidence.

Run from project root with Python 3.11 after frozen installation. Output paths must be new.
This script dispatches only the configured synthetic fixture backend.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", type=Path, default=Path("runs/synthetic"))
    parser.add_argument("--reports", type=Path, default=Path("reports/synthetic"))
    args = parser.parse_args()
    evidence = Path("reports/verification/cli")
    evidence.mkdir(parents=True, exist_ok=True)
    root = str(args.experiment)
    plan = str(args.experiment / "plan.json")
    commands = [
        ["experiment", "plan", "--config", "configs/offline.yaml", "--out", plan],
        ["run", "--plan", plan],
        ["resume", "--experiment", root],
        ["status", "--experiment", root],
        ["seal", "--experiment", root],
        ["evaluate", "--experiment", root, "--hidden", "tests/fixtures/hidden.jsonl"],
        ["report", "--experiment", root, "--out", str(args.reports)],
        ["trace", "--experiment", root, "--select", "representative", "--out", str(args.reports / "replay.html")],
    ]
    for i, command in enumerate(commands):
        result = subprocess.run([sys.executable, "-m", "rexbench", *command], capture_output=True, timeout=120)
        (evidence / f"{i}_{command[0]}.json").write_bytes(result.stdout)
        (evidence / f"{i}_{command[0]}.stderr.txt").write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError(f"{command[0]} failed: {result.stderr.decode(errors='replace')}")
        payload = json.loads(result.stdout)
        if command[0] in ("run", "resume", "status") and not payload["complete"]:
            raise RuntimeError(f"Synthetic matrix incomplete: {payload}")
        print(f"{command[0]}: passed")


if __name__ == "__main__":
    main()
