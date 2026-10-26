# Completed development pilot

Benchmark evaluation and scientific graphs are finished. The user explicitly deferred viva material. No final viva notes, presentation HTML or PDF was authored; wait until the user asks for those later.

Results: `reports/development_pilot_final/FINDINGS.md`. Machine-readable data: `findings.json`, `method_results.csv`, `per_task_results.csv`, `summary.csv`. Graphs include `hidden_success_comparison.png`, `per_task_hidden.png`, `success_vs_calls.png`, `success_vs_tokens.png`, and `baseline_vs_extension.png`. Recorded search demos: `replay.html`, `replay_success.html`, `replay_loss.html`.

At up to eight calls per problem (five tasks, one seed):

| Method | Hidden-suite success | Calls | Actual tokens |
| --- | --- | --- | --- |
| Resampling | 1/5 (20%) | 40 | 25,819 |
| Baseline REx | 4/5 (80%) | 34 | 27,247 |
| Progress + cost REx | 4/5 (80%) | 34 | 27,247 |

Both REx variants used 15% fewer calls than resampling but 5.5% more total tokens. The combined extension matched baseline REx and followed identical generated-code/branch sequences in this pilot. Two positive partial-progress updates did not change selections. This is evidence for the implemented repair system, not for an additional improvement over REx.

All 15 selected trials are complete, with 108 requests and 80,313 actual tokens and no unknown selected usage. All 150 hidden checkpoint evaluations (750 individual test executions) completed without infrastructure errors. Seal/source-immutability checks and three graph visual checks passed: `reports/verification/completed_pilot_checks.json`.

The analysis view in `runs/viva_complete_pilot` combines twelve unaffected original trials with three fresh all-method trials for the interrupted task test/0146. The replacement rule was fixed before new inference and hidden evaluation. Source IDs, hashes, responses and ledgers are preserved in `composition.json`; original campaigns are unchanged. Never execute model search in this sealed analysis view.

The original GPU campaign still has one unknown interrupted response. All original/discarded GPU work plus the separate archived CPU pilot totals 149 requests, 117,809 known tokens and one request with unknown usage. Setup/smoke/audits and hidden judging are separate costs. Selected comparison spend is not total project spend.

Limits: five development tasks, one seed, five hidden tests per task, no component ablations. Two returned REx programs pass hidden tests while failing some repair tests, so hidden-suite success does not prove full correctness. No model training occurred and the larger final study is not launched.

Regeneration requires no model calls: run `.venv/Scripts/python.exe -m rexbench report --experiment runs/viva_complete_pilot --out reports/development_pilot_final`, then `.venv/Scripts/python.exe tools/summarize_completed_pilot.py`. No benchmark process remains running. Resume later from these artifacts; do not rerun completed inference.

## Project website

The six-page website is now hosted at https://code-repair-project-notes.purplestork34.chatgpt.site (public, accessible to anyone with the link). Hosting checkout: `site_hosting`; preserve `.openai/hosting.json` and reuse its project ID for edits. Publication/version details and link checks: `reports/site_publication.json`. The offline copy remains in `website`.

## Beginner walkthrough

The user requested a complete beginner explanation of the published site. `WEBSITE_GUIDE.md` now walks through every page, controls, flowcharts, formulas, results, test evidence and likely questions. Its key counts and checkpoint table were checked against saved data. This adds a local guide only; no benchmark or hosted-site change was made.

## Synthetic UI fixtures

A separate `/test-fixtures/` page was added for the user's testing request. Its JSON/CSV token values are invented, explicitly labeled synthetic, and are not benchmark evidence. All six research pages and recorded benchmark token counts remain unchanged (REx 27,247; combined extension 27,247). Never merge the fixture values into measured reports or the beginner guide.
