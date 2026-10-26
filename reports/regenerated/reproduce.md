# Regenerate from sealed evidence

Search seal: 2e9bf6a9b262894b94add98bb99dfa53740f9431181635d1f6ee0794374611dd
Evaluation: 838dc222294ad8ce0e699b3954562409fcfe6eb13710893ff28e1804f146f96e

```powershell
rexbench report --experiment "runs\synthetic" --evaluation 838dc222294ad8ce0e699b3954562409fcfe6eb13710893ff28e1804f146f96e --out "reports\regenerated"
```

No model calls or generated-code execution occur during report/replay. Install with Python 3.11 and `uv sync --frozen --extra dev`. Source and dependencies are recorded in plan.json; model/template/image pins in resolved_config.json. Raw requests/responses and outcomes are content-addressed in artifacts/. Full raw responses are retained locally without automatic redaction. Do not redistribute dataset or statements without checking their terms. No credentials are accepted in endpoint URLs.
