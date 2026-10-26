# Continuation

The Linux Docker engine and built runner are now verified by 15 real fixtures. Remaining prerequisites are installed/serving local Ollama/model, official APPS and manual comparator/example/reference review. reports/doctor.json records current capabilities. No model inference or paid compute occurred during implementation.

From this project in PowerShell:

```powershell
uv sync --frozen --extra dev
docker build -t rexbench-runner:local -f docker/Dockerfile .
uv run pytest -m docker -rs --junitxml=reports/verification/docker_live.xml
ollama pull qwen2.5-coder:7b
uv run rexbench doctor --config configs/live_smoke.yaml --out reports/doctor.json
uv run pytest -m live -rs --junitxml=reports/verification/ollama_live.xml
```

Start Docker Desktop with Linux containers and install/start Ollama first. Do not substitute host execution. Linux/WSL needs the same lock and fresh environment identity; this host was Windows. Real-stage skips are unverified.

Follow dataset.md; fill source_revision/license/raw/manual fields first. Smoke exports a small audit pool (one train/one test), then uses its single development task:

```powershell
uv run rexbench dataset prepare --config configs/live_smoke.yaml --out data/smoke
uv run rexbench dataset audit --config configs/live_smoke.yaml --manifest data/smoke/manifest.json --out data/smoke/audit.json
uv run rexbench experiment plan --config configs/live_smoke.yaml --out runs/live_smoke/plan.json
uv run rexbench run --plan runs/live_smoke/plan.json
uv run rexbench resume --experiment runs/live_smoke
uv run rexbench status --experiment runs/live_smoke
uv run rexbench seal --experiment runs/live_smoke
uv run rexbench evaluate --experiment runs/live_smoke --hidden data/smoke/dev_hidden.jsonl
uv run rexbench report --experiment runs/live_smoke --out reports/live_smoke
uv run rexbench trace --experiment runs/live_smoke --select representative --out reports/live_smoke/replay.html
```

Investigate every infrastructure/usage/context problem before pilot. Uncertain requests deliberately do not retry: reconcile persisted/provider evidence or keep the trial incomplete. V1 has no CLI that guesses a missing response. Other jobs may continue, but uncertainty blocks sealing.

Run pilot only after smoke. Its480 nominal dispatch allowance may not cover token extensions. Choose resources before planning, rather than editing an active identity. Report exports measured pilot_resources.json; synthetic resource forecasts are rejected.

reports/main_plan.json is planning-only: no invented task IDs or executable jobs. After pilot, preregistration and chosen final scope/resources:

```powershell
uv run rexbench experiment plan --config configs/main.yaml --pilot-resources reports/pilot/pilot_resources.json --out runs/main/plan.json
```

Main launching is pending that scope and prerequisites. Defaults are safeguards, not a completion forecast. A12-hour/8,640-call stop does not establish a complete token comparison.
