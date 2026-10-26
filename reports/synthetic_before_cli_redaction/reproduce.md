# Regenerate from sealed evidence

Search seal: 4b5f319471ee666e784938297761eea692e454d92e21d1d42675c7769eddddd6
Evaluation: 133b0202dbfd6cfcd741d49e04f7aca144f3c016061089bcbc66edcbcf8db41b

```powershell
rexbench report --experiment "runs\synthetic" --evaluation 133b0202dbfd6cfcd741d49e04f7aca144f3c016061089bcbc66edcbcf8db41b --out "reports\synthetic"
```

No model calls or generated-code execution occur during report/replay. Install with Python 3.11 and `uv sync --frozen --extra dev`. Source and dependencies are recorded in plan.json; model/template/image pins in resolved_config.json. Raw requests/responses and outcomes are content-addressed in artifacts/. Full raw responses are retained locally without automatic redaction. Do not redistribute dataset or statements without checking their terms. No credentials are accepted in endpoint URLs.
