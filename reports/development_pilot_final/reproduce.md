# Regenerate from sealed evidence

Search seal: 13bc175912c47e14cdf263ec83563d56975fd3f98b5a1aa3a0e1af62b96638ba
Evaluation: c4a81f75b56a5c703a2d436ae2b26588ba790d0abda2d248b15078caf8e62282

```powershell
rexbench report --experiment "runs\viva_complete_pilot" --evaluation c4a81f75b56a5c703a2d436ae2b26588ba790d0abda2d248b15078caf8e62282 --out "reports\development_pilot_final"
```

No model calls or generated-code execution occur during report/replay. Install with Python 3.11 and `uv sync --frozen --extra dev`. Source and dependencies are recorded in plan.json; model/template/image pins in resolved_config.json. Raw requests/responses and outcomes are content-addressed in artifacts/. Full raw responses are retained locally without automatic redaction. Do not redistribute dataset or statements without checking their terms. No credentials are accepted in endpoint URLs.
