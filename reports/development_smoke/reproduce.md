# Regenerate from sealed evidence

Search seal: 7c23983b68c999803cb8c3db8ad75a130985eac49e6fc863dd9c4f2cad8905f1
Evaluation: 5f0a7e4ddb2266b4ef81410b5ad41f8df9dba2a13b43c174194e73da3664cbf5

```powershell
rexbench report --experiment "runs\development_smoke" --evaluation 5f0a7e4ddb2266b4ef81410b5ad41f8df9dba2a13b43c174194e73da3664cbf5 --out "reports\development_smoke"
```

No model calls or generated-code execution occur during report/replay. Install with Python 3.11 and `uv sync --frozen --extra dev`. Source and dependencies are recorded in plan.json; model/template/image pins in resolved_config.json. Raw requests/responses and outcomes are content-addressed in artifacts/. Full raw responses are retained locally without automatic redaction. Do not redistribute dataset or statements without checking their terms. No credentials are accepted in endpoint URLs.
