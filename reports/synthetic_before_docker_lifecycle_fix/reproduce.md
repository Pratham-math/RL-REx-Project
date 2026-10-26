# Regenerate from sealed evidence

Search seal: dc106c56dccf5d7d52d860240e8b7e038819950cebd0b192e76924b5e23333a0
Evaluation: d97a143c03d80c38b684749c0e6add298a9e790e07759915be78ec7cec2bac88

```powershell
rexbench report --experiment "runs\synthetic" --evaluation d97a143c03d80c38b684749c0e6add298a9e790e07759915be78ec7cec2bac88 --out "reports\synthetic"
```

No model calls or generated-code execution occur during report/replay. Install with Python 3.11 and `uv sync --frozen --extra dev`. Source and dependencies are recorded in plan.json; model/template/image pins in resolved_config.json. Raw requests/responses and outcomes are content-addressed in artifacts/. Full raw responses are retained locally without automatic redaction. Do not redistribute dataset or statements without checking their terms. No credentials are accepted in endpoint URLs.
