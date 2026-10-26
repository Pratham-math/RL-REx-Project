# RExBench

Progress- and Cost-Aware Code Repair with Bandit Search. This is an algorithm reproduction and controlled APPS extension with frozen model weights. Six study methods and BFS/fixed-width controls share one controller. There is no model training.

**Current follow-up status:** [PROGRESS.md](PROGRESS.md) explains what is ready and what is left. Five real development problems are reference-audited; the local server is running, but model weights are still missing. New features and evidence are documented in [docs/followup_2026-10-26.md](docs/followup_2026-10-26.md), with [exact continuation commands](docs/continuation_followup.md). No real-model pilot or final study has run.

The harness has offline verification, 15 passing real Docker fixtures, and an explicitly synthetic end-to-end example. **No real-model benchmark or live pilot is established.** [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) records evidence and blockers. Synthetic reports cannot support performance claims.

The original starter is preserved byte-for-byte in `reference/starter/`; its 11 offline tests passed before migration. The supplied ZIP and paper remain untouched in the parent directory. Active code is `src/rexbench`. The authors' MIT code is pinned under `vendor/REx`; source records and conformance evidence are in `docs/source_records.json` and `reports/parity.json`.

Install and verify with Python 3.11 (PowerShell):

```powershell
uv sync --frozen --extra dev
uv run ruff check src tests
uv run mypy src/rexbench
uv run pytest -m 'not docker and not live'
uv run rexbench --help
```

`uv.lock` records installed versions and distribution hashes. Local verification used CPython3.11.13 on Windows. Linux containers are the execution target. CI configuration exists; no remote CI pass is claimed.

Run the synthetic workflow in a new output directory:

```powershell
uv run rexbench experiment plan --config configs/offline.yaml --out runs/synthetic/plan.json
uv run rexbench run --plan runs/synthetic/plan.json
uv run rexbench resume --experiment runs/synthetic
uv run rexbench status --experiment runs/synthetic
uv run rexbench seal --experiment runs/synthetic
uv run rexbench evaluate --experiment runs/synthetic --hidden tests/fixtures/hidden.jsonl
uv run rexbench report --experiment runs/synthetic --out reports/synthetic
uv run rexbench trace --experiment runs/synthetic --select representative --out reports/synthetic/replay.html
```

Mock responses, graphs and traces are labeled synthetic. The mock judge never executes source. A run with either mock component must use the synthetic track. Do not mix these rows with live results.

For real isolated execution, start Docker Desktop with Linux containers or a Linux daemon, then:

```powershell
docker build -t rexbench-runner:local -f docker/Dockerfile .
uv run pytest -m docker -rs
ollama pull qwen2.5-coder:7b
uv run rexbench doctor --config configs/live_smoke.yaml --out reports/doctor.json
uv run pytest -m live -rs
```

Install/start Ollama on localhost:11434 first. No model download, paid API or purchase is triggered automatically. Doctor only inspects metadata. The explicitly selected live test makes two local requests when available and retains raw payloads. A skip is unverified. Docker Desktop was started locally and the pinned runner built and validated with 15 real fixtures; its actual image/runtime records are in reports/runner_image.json. Use a disposable experiment machine for generated programs.

Prepare official APPS with [docs/dataset.md](docs/dataset.md). Manual comparator/example review and vetted references are required. Search accepts only closed-schema repair records; references stay audit-only. There is no host execution fallback.

```powershell
uv run rexbench dataset prepare --config configs/main.yaml --out data/frozen
uv run rexbench dataset audit --config configs/main.yaml --manifest data/frozen/manifest.json --out data/frozen/audit.json
uv run rexbench parity --upstream vendor/REx --out reports/parity.json
uv run rexbench experiment plan --config configs/pilot.yaml --out runs/pilot/plan.json
uv run rexbench run --plan runs/pilot/plan.json
```

Update profile paths to the chosen frozen export first. Smoke uses one audited development task and two inference dispatches. Pilot uses 10 development tasks, six methods, one seed and eight nominal calls (480). Main describes 30 evaluation tasks, six methods, three seeds and16 calls (8,640 nominal; up to34,560 with the64-call extension ceiling). Token extensions/tuning/audits are extra; planning flags insufficient allowance. A12-hour safeguard is not a runtime forecast. Main execution is pending prerequisites and chosen resources.

Freeze the development-selected real setup before final hidden evaluation. [docs/preregistered_protocol.md](docs/preregistered_protocol.md) is a pending template. [docs/continuation.md](docs/continuation.md) supplies exact continuation commands.

All commands support `--help`. JSON goes to stdout; structured errors to stderr (exit2, cancellation130, unavailable doctor1). A paused run can exit normally with `complete:false`; automation must inspect statuses. Completed resume is inert.

SQLite records request intent, raw response before normalization/judging, judged observations and atomic policy commits. Unknown in-flight outcomes pause as REQUEST_OUTCOME_UNKNOWN; no blind/free retry occurs. There are zero automatic inference retries. Missing usage/backend/judge errors block completion. Active resume rejects source/lock/config/data/runtime/model/image drift.

Reporting requires a complete Cartesian product, covered checkpoints, intact seal and immutable hidden evaluation. Seeds are averaged within tasks, then tasks bootstrapped in pairs. Prefix cost and total campaign cost (including crossings/extensions) are separate. Null tokens-per-success means undefined due to zero successes. Report/replay never execute source or contact models.

Compilation occurs only in the isolated runner. Exact source storage is deduplicated; search arms are distinct per generation; evaluation caching is off. Context admission is approximate, and strict token caps unsupported. Model seed/usage/template behavior awaits real local-model verification. See [docs/decisions.md](docs/decisions.md) for departures and limits.
