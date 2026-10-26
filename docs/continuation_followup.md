# Continue the approved small pilot

## Current GPU continuation: no campaign time limit

The user removed the hard one-hour cutoff on 2026-10-26. All 14 recoverable GPU trials are now finished; the remaining interrupted trial has no saved response. The controller has exited. Status: `reports/development_pilot_gpu_status.md`. The authorized continuation controller is `tools/resume_without_time_limit.py`. Do not start another writer. Check status first; if stopped, continue with:

```powershell
.venv/Scripts/python.exe tools/resume_without_time_limit.py --experiment runs/development_pilot_gpu --no-wall-time-limit
```

The original plan remains immutable; the explicit operational amendment is `runs/development_pilot_gpu/wall_time_amendment.json`. The user also extended the GPU dispatch ceiling to 118 to finish the final recoverable trial; the continuation command reloads that persisted amendment. Source/model/data checks, per-trial limits and request/program timeouts remain in force. The interrupted unknown response is preserved without retry. Standard `rexbench resume` retains the historical plan's time limit. Older CPU/setup instructions below are historical; current state is in `PROGRESS.md`.

Update2026-10-26: the model is installed, the live usage contract and two-call smoke passed, and the approved pilot is running. See PROGRESS.md and reports/live_stage_status.json. The setup instructions below describe how to recover the same environment if needed; do not start a second writer while the pilot is active.

The local server is running at localhost:11434 with Ollama0.40.11. It uses the project-local .runtime/models directory. No models are installed. The runtime executable and CPU libraries were obtained from verified-size/CRC members of the official Windows release archive; per-file SHA256 records are in reports/setup/native_runtime.json. The full release archive checksum was not verified, and no GPU execution is claimed.

The user selected a small development pilot, up to one hour, rather than the final study. Download/setup retries have stopped at the stated final retry limit. Complete the model download when network access permits:

```powershell
& .runtime/ollama-0.40.11-cpu/ollama.exe pull qwen2.5-coder:7b
.venv/Scripts/python.exe -m rexbench doctor --config configs/development_pilot.yaml --out reports/doctor_ready.json
.venv/Scripts/python.exe -m pytest -m live -rs
```

The explicitly selected live test makes two local usage-validation requests. Verify their raw prompt/output counts before interpreting costs. It does not establish benchmark performance or bitwise seed reproducibility.

The one-task smoke dataset is already reference-audited. Run it first:

```powershell
.venv/Scripts/python.exe -m rexbench run --plan runs/development_smoke/plan.json
.venv/Scripts/python.exe -m rexbench status --experiment runs/development_smoke
.venv/Scripts/python.exe -m rexbench seal --experiment runs/development_smoke
.venv/Scripts/python.exe -m rexbench evaluate --experiment runs/development_smoke --hidden data/development_smoke/dev_hidden.jsonl
.venv/Scripts/python.exe -m rexbench report --experiment runs/development_smoke --out reports/development_smoke
```

Only after complete smoke coverage and correct accounting, run the approved pilot:

```powershell
.venv/Scripts/python.exe -m rexbench run --plan runs/development_pilot/plan.json
.venv/Scripts/python.exe -m rexbench status --experiment runs/development_pilot
.venv/Scripts/python.exe -m rexbench seal --experiment runs/development_pilot
.venv/Scripts/python.exe -m rexbench evaluate --experiment runs/development_pilot --hidden data/development_pilot/dev_hidden.jsonl
.venv/Scripts/python.exe -m rexbench report --experiment runs/development_pilot --out reports/development_pilot
.venv/Scripts/python.exe -m rexbench trace --experiment runs/development_pilot --select representative --out reports/development_pilot/replay.html
```

The pilot plans15 trials: five tasks x3 methods x1 seed, eight nominal calls,120 total dispatch ceiling, one hour of active search. Hidden judging/auditing are separate costs. Token coverage at1024/2048 may require extensions up to16 calls/trial, so the allowance can pause an incomplete campaign. Do not seal/report an incomplete matrix or discard difficult cells.

Data provenance and departures matter: these are five explicitly reserved development problems drawn from an official-linked APPS mirror snapshot of test rows100..199. The original train windows inspected did not provide five eligible stdio tasks. The five task IDs remain test-prefixed; they are not relabeled as original train data. All100 IDs in the development window are excluded from future final selection in configs/main.yaml. Exact mirror response hashes and the observed repository revision are retained; the rows API itself has no revision parameter. No complete original archive hash is claimed.

The repaired program sees only repair tests. Hidden and reference data remain separate. Source/model/config drift blocks active resume; regenerate a new plan before starting if source changes. Do not edit an active plan to bypass the drift gate.

Uncertain request outcomes can now be reconciled with independently recovered evidence:

```powershell
.venv/Scripts/python.exe -m rexbench reconcile --experiment runs/development_pilot --evidence recovered_response.json
```

See rexbench.reconcile.RecoveredResponse for the closed evidence schema. It requires the original request/prompt/model fingerprints, unique provider ID, timestamps, actual usage and transport/server evidence. It never calls the model or invents a response. Without such evidence keep the trial unknown/incomplete.

The larger final study, frozen final model/protocol and real comparative results remain pending. No model gains have been established.
