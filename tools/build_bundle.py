"""Create a local handoff ZIP with hash inventory and a consistent SQLite backup."""
from __future__ import annotations

import hashlib
import argparse
import json
import sqlite3
import zipfile
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=root / "dist/rexbench_reproducibility.zip")
    parser.add_argument("--followup", action="store_true")
    parser.add_argument("--live", action="store_true", help="Include recorded local-model smoke/pilot evidence")
    args = parser.parse_args()
    include = ["src", "tests", "configs", "docker", "docs", "tools", ".github", "reference/starter",
               "vendor/REx", "reports/verification", "reports/synthetic", "runs/synthetic"]
    files = [root / name for name in ["pyproject.toml", "uv.lock", "README.md", "IMPLEMENTATION_STATUS.md", ".gitignore", ".dockerignore",
                                      "reports/doctor.json", "reports/parity.json", "reports/main_plan.json", "reports/runner_image.json"]]
    if args.followup:
        include += ["reports/synthetic_followup", "runs/synthetic_followup", "runs/development_pilot", "data/development_pilot",
                    "runs/development_smoke", "data/development_smoke"]
        files += [root / p for p in ["PROGRESS.md", "reports/doctor_followup.json", "reports/development_audit_summary.json", "reports/main_plan_followup.json"]]
        files += list((root / "reports/setup").glob("*.json"))
    if args.live:
        include += ["reports/development_smoke", "reports/development_pilot", "runs/development_smoke", "runs/development_pilot",
                    "reports/development_pilot_gpu", "runs/development_pilot_gpu"]
        files += [root / p for p in ["PROGRESS.md", "reports/doctor_ready.json", "reports/doctor_gpu.json",
                                    "reports/live_stage_status.json", "reports/campaign_accounting.json"]]
        files += list((root / "reports").glob("live_usage*.json"))
        files += list((root / "reports").glob("gpu_usage*.json"))
    for name in include:
        files.extend(p for p in (root / name).rglob("*") if p.is_file())
    files = sorted(set(p for p in files if p.is_file() and "__pycache__" not in p.parts and "audit_private" not in p.parts and "audit_checkpoints" not in p.parts and
                       not p.name.endswith((".pyc", ".sqlite-wal", ".sqlite-shm")) and p.name != ".writer.lock"))
    destination = args.out
    destination.parent.mkdir(exist_ok=True)
    entries = []
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            name = path.relative_to(root).as_posix()
            if path.name == "state.sqlite":
                source = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
                target = sqlite3.connect(":memory:")
                source.backup(target)
                payload = target.serialize()
                source.close()
                target.close()
            else:
                payload = path.read_bytes()
            archive.writestr("rexbench/" + name, payload)
            entries.append({"path": name, "sha256": digest(payload), "bytes": len(payload)})
        scope = ("implementation, labeled synthetic verification, real local-model smoke and bounded development-pilot evidence; inspect coverage before comparative claims; final study pending"
                 if args.live else "implementation, synthetic verification and documented audit evidence; real-model study pending")
        manifest = {"schema_version": 1, "scope": scope,
                    "entries": entries, "excluded": ["virtual environments", "complete APPS archive and private reference solutions", "model weights/runtime binaries", "paper PDF/extracted text",
                                                       "historical/regenerated duplicate reports", "SQLite transient files"]}
        archive.writestr("rexbench/BUNDLE_MANIFEST.json", json.dumps(manifest, sort_keys=True, indent=2))
    checksum = digest(destination.read_bytes())
    destination.with_suffix(".zip.sha256").write_text(checksum + "  " + destination.name + "\n")
    print(json.dumps({"archive": str(destination), "sha256": checksum, "files": len(entries), "bytes": destination.stat().st_size}))


if __name__ == "__main__":
    main()
