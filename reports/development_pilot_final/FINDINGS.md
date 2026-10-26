# Completed development pilot

The combined progress/cost implementation and baseline REx each passed every hidden test on 4/5 development tasks (80%). Independent resampling did so on 1/5 tasks (20%). Both REx variants used 34 model calls versus resampling's 40 (15% fewer calls). Each REx variant consumed 27,247 tokens versus resampling's 25,819 (+5.5%); fewer calls did not mean fewer total tokens.

This supports a positive measured comparison for repair-based search against resampling in this small setting. It does not show an additional gain from the proposed combined extension over baseline REx: the two policies had identical selected branches, generated code sequences and actual token costs on all five tasks. The modified policy received two positive partial-progress updates without changing those selections.

## Measurement

Five development tasks x three methods x one seed = 15 complete selected trials. The model was frozen Qwen2.5-Coder 7B Q4_K_M on RTX 4060 Laptop via Ollama Vulkan. Settings: C=20, eta=0.5, gamma=0.5; eight nominal calls, integer checkpoints 1..8 and completed-prefix token checkpoints 1024/2048. The model, prompts, task bytes, parser and judge settings were shared. There was no model training.

Search saw only repair feedback. The returned program was fixed by repair score before hidden judging. The sealed analysis view has no missing or censored checkpoints and no unknown selected usage. All 150 hidden checkpoint evaluations (750 individual tests) completed without infrastructure errors.

## Provenance and accounting

One original response was lost during interruption. A rule fixed before replacement inference and hidden evaluation reran the affected problem for all three methods, irrespective of outcomes. The analysis uses those three fresh trials and twelve unaffected originals. Source experiment IDs, raw responses and hashes are preserved in `runs/viva_complete_pilot/composition.json`; originals were not overwritten.

Selected comparison: 108 requests and 80,313 actual tokens. Both GPU source campaigns, including discarded work: 131 requests, 101,706 known tokens and one unknown-usage request. The separately preserved CPU campaign adds 18 requests and 16,103 tokens. All pilot work therefore totals 149 requests and 117,809 known tokens plus the unresolved request's usage. Setup, smoke, reference audits and hidden judging are separate. These known-token sums are not an exact total project cost.

## Interpretation limits

This is a five-task, one-seed development pilot, not the planned final study or an official APPS score. There are only five hidden tests per task. Two returned REx programs pass all hidden cases while still failing some repair cases, so 80% hidden-suite success is not proof of full program correctness. Report both suites in `per_task_results.csv`.

Paired task-bootstrap intervals are descriptive with n=5. The zero-width extension-minus-REx interval arises from identical observed outcomes and does not establish population equivalence. Progress-only and cost-only ablations were not run. Strong priors, sparse feedback and the short call budget are plausible explanations for unchanged choices, not isolated causal findings.

## Files

- `method_results.csv`: success, requests, tokens and normalized call AUC.
- `per_task_results.csv`: hidden and repair fractions for every selected trial.
- `summary.csv`: full call/token checkpoints and bootstrap intervals.
- `findings.json`: machine-readable verified results and accounting.
- `hidden_success_comparison.png`, `per_task_hidden.png`, `success_vs_calls.png`, `success_vs_tokens.png`: scientific graphs.
- `mechanism_diagnostics.json`: direct trace comparison between baseline and extension.
- `work_accounting.csv`: full source campaign spend, including discarded and unknown work.
- `replay.html`, `replay_success.html`, `replay_loss.html`: inert recorded traces.

Regenerate standard analysis with `rexbench report --experiment runs/viva_complete_pilot --out reports/development_pilot_final`, then run `.venv/Scripts/python.exe tools/summarize_completed_pilot.py` to restore these supplemental findings and graph labels. Neither step invokes the model or reruns hidden judging.
