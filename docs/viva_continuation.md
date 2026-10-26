# Continuation after completed benchmark

The latest user instruction is to defer viva material until requested later. No final viva notes, presentation or PDF was generated. The benchmark itself is complete.

Read `PROGRESS.md` and `reports/development_pilot_final/FINDINGS.md`. Use the already measured JSON/CSV and graphs when the user asks for explanation or viva materials. No further model calls or hidden evaluation are needed to use these results.

The method comparison is 20% hidden-suite success for resampling, 80% for baseline REx and 80% for the combined extension across five tasks, one seed. Both REx methods used 34 calls and 27,247 tokens versus 40 calls and 25,819 tokens for resampling. The extension's branch/code sequences matched REx. Explain the implemented changes and the measured result without inventing a baseline improvement.

A sealed analysis view combines 12 original trials and three whole-task replacement trials under a fixed pre-evaluation rule. Both source logical hashes remain unchanged. Detailed costs include discarded work and the original unknown request. See `reports/verification/completed_pilot_checks.json`.

Draft helper source for future artifact generation exists in `tools/build_viva_report.py` and `tools/build_viva_pdf.py`, but neither authored a final artifact. Run them only after the user requests viva materials, check all claims against final data, and follow the relevant artifact skill/visual QA workflow. The reporting worker `tools/finish_viva.py` was stopped and changed to scientific benchmark-report-only mode.
