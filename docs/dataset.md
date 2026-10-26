# Official data and manual audit

The official APPS repository links https://people.eecs.berkeley.edu/~hendrycks/APPS.tar.gz (checked2026-10-25 at https://github.com/hendrycks/apps). No official checksum was supplied here. Record the downloaded archive hash and relevant distribution/problem licenses; do not invent either.

```powershell
New-Item -ItemType Directory -Force data/raw
curl.exe -L https://people.eecs.berkeley.edu/~hendrycks/APPS.tar.gz -o data/raw/APPS.tar.gz
Get-FileHash -Algorithm SHA256 data/raw/APPS.tar.gz
tar -xzf data/raw/APPS.tar.gz -C data/raw
```

Inspect the extracted layout; update raw_train/raw_test, source_revision (actual archive/release hash), license and export paths in the chosen profile. Statements and decoded UTF-8 test strings retain line endings/whitespace. JSON escapes are not semantic input bytes. Exports include a source-file/tree inventory hash.

Create data/manual_audit.json keyed by original partition/ID. This is an illustrative shape, not an attestation for a real task:

```json
{"train/0000":{"comparator":"tokens_v1","comparator_justification":"Explain output whitespace semantics","examples_reviewed":true,"examples":["EXACT INPUT WITH NEWLINES"],"vetted_reference_indices":[0]}}
```

Review statement examples (including HTML/layout), output requirements, special judges and reference source/language before attesting. Unsupported tasks, unknown comparators, missing references and insufficient tests have exclusion records with original IDs. Select enough reviewed interview tasks in train and test. SHA-256 keyed order fixes selection before model outcomes. Source-URL and normalized exact statement checks reject cross-pool duplicates; near duplicates still need human review.

Default minima are3 repair/5 hidden and maxima10/50; known examples are forced into repair. Exact input duplicates share a case; comparator-inconsistent outputs exclude the task. Whitespace-equivalent inputs are not universally merged. Too many examples exclude a task. All references remain under audit_private, never in search exports/prompts/logs. Audit repeats each vetted reference twice with the same runner/limits on both suites. Investigate failures before creating a new selection; do not replace tasks based on method outcomes.

Use a NEW export directory, because prepare refuses overwrite:

```powershell
uv run rexbench dataset prepare --config configs/main.yaml --out data/frozen
uv run rexbench dataset audit --config configs/main.yaml --manifest data/frozen/manifest.json --out data/frozen/audit.json
```

Set data.manifest to data/frozen/manifest.json and data.repair_file to data/frozen/final_repair.jsonl (pilot uses dev_repair). Exports include dev/final repair/hidden JSONL, manifest.json and the separate audit.json. A passing non-synthetic audit is bound to the manifest and runner. Search rejects hidden/reference fields; evaluation checks hidden hashes, disjoint cases and matching comparator/limits. This restricted study is not the official APPS score, and public contamination remains a limitation.
