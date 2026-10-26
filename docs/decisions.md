# Decisions and departures

2026-10-25. Governing contract: user-supplied specification v1.0. Existing project retained, original files preserved in reference/starter. No applicable AGENTS.md was found in the project/ancestors. Unrelated work was preserved.

| Area | Decision and consequence |
| --- | --- |
| Study | Algorithm reproduction/controlled stdio APPS extension, not historical-model/full-paper reproduction. |
| Source | Authors' commit371e879da5b1fff0d32a695ad37dcac50f74721b, MIT retained. Direct scheduler conformance in fake domains, not its model stack. |
| Equation11 | Equations7-10 and source define mean denominator2+C+N; printed2+2C+N is not used. |
| Randomness | NumPy default_rng(base seed), arm creation order, lone-root draw. SHA-256 independent keyed feedback/model streams; record draws/estimates/priors. |
| Terminal | Match upstream no parent update on success; persist successful child and snapshot anyway. |
| Identity | One arm per generation, shared source blobs, evaluation cache off. Upstream APPS RefineAPPS merges task+source by hash equality. This is a disclosed domain departure. |
| Invalid output | Charged h=0 arm with no source, failed-generation feedback; cannot be returned as eligible code. Upstream APPS may add no arm. |
| Greedy | Root0.5 and seeded random ties; upstream uses first maximum. Not labeled paper_parity. Old root-excluding control preserved only as reference. |
| Controls | FIFO BFS branching2; fixed-width K4 replaces endpoint even on regressions. Main excludes these optional controls; decide real inclusion before final evaluation. |
| Data | Local official train/dev and test/final pools required. Single-partition fallback deliberately unsupported. No automatic large download. |
| Comparator | Tokens, exact text, or exact lines with one optional final newline. Explicit per-task justification; no global numeric tolerance/special judges. |
| Examples | Exact-byte identity; relaxed containment only for conservative leak flags. Known examples forced into repair; manual review required. Automatic checks do not prove no leakage. |
| References | Explicitly vetted indices, two audit-only executions on both suites. Failure blocks selection; no favorable automatic replacement. Archive/release identity and licenses must be supplied. |
| Judge | Fresh container/test; trusted non-root PID1 uid65534; compile/run exec uid65533. Exit/lifecycle metadata from Docker API, never program stdout. Expected output stays on host. CPU/peak-memory measurements null where unreliable. |
| Input | Base64 input passed to trusted in-container wrapper and delivered on stdin. Only source is mounted read-only. Importer bounds each input/output at20,000 bytes. |
| Image | Base manifest resolved with docker buildx imagetools inspect. Actual built runner image/runtime pinned in reports/runner_image.json; 15 real Docker fixtures pass. |
| Backend | Mock or explicitly local Ollama only. No hosted/compatible adapter, paid spending or fallback. Retain full HTTP body, including invalid JSON, before judging. |
| Context | UTF-8 bytes+256 overhead and output reservation: unverified conservative admission approximation, not certified hard bound. Explicit backend overflow pauses; strict token caps unsupported. Template/tokenizer validation remains a live prerequisite. |
| Usage | Actual prompt_eval_count/eval_count; preserve raw cached/duration fields. Repeated-prompt test must validate semantics. Unknown usage never replaced by estimated actuals. |
| Recovery | Durable intent cannot promise exactly-once inference. Unknown dispatch pauses; zero automatic inference retries. Saved responses/judgments reused only for that request. |
| Operations | One writer OS lock, serial trials/model concurrency1. Leases reclaimed under lock. Campaign controls pause; in-flight transport/judging receives remaining deadline. |
| Cancellation | SIGTERM/interrupt preserve state; container finally-removal kills descendants. Real fixtures verify interrupt cleanup and owner-scoped orphan removal. Active resume cleans only its own runners under the writer lock. Unreachable-daemon cleanup cannot be guaranteed. |
| Coverage | Context exhaustion/extension ceiling remain incomplete; no invented later outcomes. Visible success alone is absorbing. |
| Statistics | Completed-prefix token curves, all campaign spend retained, prefix and campaign cost ratios. Integer-call mean AUC; paired task bootstrap; components exploratory. |
| Retention | Full local prompt/response/source/outcomes by hash, no automatic redaction. Credential URLs rejected; secret environment values not captured. Check redistribution terms. |
| Release | No empirical gains, final study, remote CI pass or completed preregistration. M8/M9 blocked. |

Progress is fractional pseudo-count shaping, without an exact Bernoulli-posterior, policy-invariance or budgeted-bandit optimality guarantee. Details are in source and tests; these are operational departures, not paper claims.


2026-10-26 live development continuation: the user installed qwen2.5-coder:7b (digest dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364). The local two-request usage contract passed; CPU-only execution remains explicit. Proceed with the existing immutable smoke/pilot plans, without tuning or extending the approved one-hour/120-dispatch pilot allowance. Frozen scope and limitations are in docs/development_live_protocol.json. Follow-up data/recovery/reporting departures are documented in docs/followup_2026-10-26.md.

2026-10-26 GPU steering: the user requested GPU acceleration after questioning sparse repair feedback. Added the official small Vulkan runtime components, verified full RTX4060 offload and two repeated-prompt usage requests. Paused the CPU campaign after persisting a response and drained judging without dispatching another inference. All18 CPU requests committed. A separate empty-start GPU campaign keeps the same tasks/prompts/methods, receives the remaining102 dispatches and2138.8 active seconds, and must not be pooled with CPU outcomes. No repair/hidden suites changed. See docs/gpu_transition.json and reports/setup/cpu_to_gpu_pause.json.
