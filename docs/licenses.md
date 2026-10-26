# Source and redistribution records

- Authors' REx repository: MIT, commit371e879da5b1fff0d32a695ad37dcac50f74721b. Its LICENSE is retained in vendor/REx/LICENSE. Source hashes and parity evidence are recorded separately.
- Starter: user-supplied rex_project.zip, preserved in reference/starter. No separate starter license was supplied; no new public distribution license is asserted.
- Paper: user-supplied v3 PDF, unchanged outside the package. Its hash is recorded. The extracted reading text and PDF are excluded from the handoff ZIP; retrieve the paper at https://arxiv.org/abs/2405.17503v3.
- APPS: the follow-up local handoff includes the five selected development tasks and their frozen test splits, source metadata, hashes and audit results. They came from the official-linked Hugging Face APPS mirror; its dataset card declares MIT. The complete original archive and reference solutions are excluded. See docs/development_selection.json and docs/followup_2026-10-26.md for provenance and limitations. Check problem-source terms before any public redistribution; this local handoff is not a public release.
- Dependencies: exact distributions and hashes are in uv.lock; upstream distribution metadata supplies their licenses. Virtual environments and downloaded wheels are excluded from the bundle.
- New harness: no license has been assigned on the user's behalf. Choose one before public release. The requested local handoff is not public publication.

Synthetic fixture responses and judgments remain labeled separately from the real development-data audit. The bundle contains no model credentials, real APPS reference solutions, model weights or invented empirical benchmark results. Reference code used for the audit stays in the original workspace's private audit directory and is excluded from the ZIP.
