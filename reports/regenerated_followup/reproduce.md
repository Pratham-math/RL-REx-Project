# Regenerate from sealed evidence

Search seal: 0576ca325dfef62ad4b7480d1532ae610be29b85baeb6239d6be3b81d45aef02
Evaluation: 004574a82fd069a6a17efd03b86da6622d98a6bf5b0092b4a99e2bb7813b7764

```powershell
rexbench report --experiment "runs\synthetic_followup" --evaluation 004574a82fd069a6a17efd03b86da6622d98a6bf5b0092b4a99e2bb7813b7764 --out "reports\regenerated_followup"
```

No model calls or generated-code execution occur during report/replay. Install with Python 3.11 and `uv sync --frozen --extra dev`. Source and dependencies are recorded in plan.json; model/template/image pins in resolved_config.json. Raw requests/responses and outcomes are content-addressed in artifacts/. Full raw responses are retained locally without automatic redaction. Do not redistribute dataset or statements without checking their terms. No credentials are accepted in endpoint URLs.
