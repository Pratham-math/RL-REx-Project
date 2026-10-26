from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .evaluate import coverage, verify_seal
from .metrics import aggregate, auc_statistics, call_auc, validate_rows
from .replay import replay
from .store import Store
from .util import atomic_bytes, fingerprint, read_json, write_json

matplotlib.rcParams["svg.hashsalt"] = "rexbench-v1"


def csv_file(path: Path, rows: list[dict]):
    if not rows:
        atomic_bytes(path, b"category,count,representative_trial\n")
        return
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    atomic_bytes(path, stream.getvalue().encode())


def describe_finding(synthetic: bool, primary: dict | None, call_max: int) -> str:
    if synthetic:
        return "Synthetic fixtures verify plumbing and calculations; they establish no comparative model performance."
    if not primary or primary.get("delta_vs_rex") is None:
        return "Measured local-model run; no combined-policy versus REx comparison is available in this method matrix."
    text = (f"Combined policy minus REx at {call_max} calls: {primary['delta_vs_rex']:.4f} "
            f"(paired task bootstrap 95% CI {primary['delta_ci_low']:.4f}, {primary['delta_ci_high']:.4f}). ")
    if primary["delta_ci_low"] <= 0 <= primary["delta_ci_high"]:
        return text + "Inconclusive: interval spans zero."
    return text + "This difference applies only to the measured setting; inspect component results and cost."


def report(root: Path, out: Path, evaluation_version: str | None = None):
    out.mkdir(parents=True, exist_ok=True)
    preflight = Store(root, readonly=True)
    try:
        checked = coverage(root, preflight)
        write_json(out / "coverage.json", checked)
        if not checked["complete"]:
            raise ValueError("Final report blocked by incomplete planned coverage; see coverage.json")
    finally:
        preflight.close()
    frozen = verify_seal(root)
    plan = read_json(root / "plan.json")
    choices = sorted((root / "evaluations").glob("*/evaluation.json"))
    if evaluation_version:
        choices = [root / "evaluations" / evaluation_version / "evaluation.json"]
    if len(choices) != 1:
        raise ValueError("Select exactly one immutable evaluation version with --evaluation")
    evaluated = read_json(choices[0])
    if evaluated["result_hash"] != fingerprint({k: v for k, v in evaluated.items() if k != "result_hash"}):
        raise ValueError("Evaluation hash mismatch")
    if evaluated["seal_hash"] != frozen["seal_hash"]:
        raise ValueError("Evaluation is for another search seal")
    store = Store(root, readonly=True)
    try:
        checked = coverage(root, store)
        out.mkdir(parents=True, exist_ok=True)
        write_json(out / "coverage.json", checked)
        if not checked["complete"]:
            raise ValueError("Final report blocked by incomplete planned coverage")
        config = plan["config"]
        call_max = max(config["budgets"]["call_checkpoints"])
        validate_rows(evaluated["rows"], plan["jobs"], call_max, config["budgets"]["token_checkpoints"])
        settings = config["report"]
        methods = config["experiment"]["methods"]
        summary = aggregate(evaluated["rows"], methods, settings["bootstrap_samples"], settings["bootstrap_seed"])
        summary = [{"synthetic": evaluated["synthetic"], "study_metric": config["experiment"]["primary_metric"], **row} for row in summary]
        write_json(out / "summary.json", summary)
        csv_file(out / "summary.csv", summary)
        auc_rows = [{"synthetic": evaluated["synthetic"], **row} for row in auc_statistics(
            evaluated["rows"], methods, call_max, settings["bootstrap_samples"], settings["bootstrap_seed"])]
        write_json(out / "auc.json", auc_rows)
        csv_file(out / "auc.csv", auc_rows)
        synthetic = evaluated["synthetic"]
        resolved = read_json(root / "resolved_config.json")
        model_digest = resolved["config"]["model"]["digest"]
        title = ("SYNTHETIC FIXTURE — " if synthetic else "") + config["model"]["name"] + f" [{model_digest[:12]}]"
        subtitle = f"{len({j['task_id'] for j in plan['jobs']})} tasks; {len(config['experiment']['seeds'])} seeds; task bootstrap 95% CI"
        for axis in ("calls", "tokens"):
            fig, ax = plt.subplots(figsize=(9, 5.5))
            for method in methods:
                group = sorted([r for r in summary if r["axis"] == axis and r["method"] == method], key=lambda r: r["budget"])
                if group:
                    x = [r["budget"] for r in group]
                    y = [r["success"] for r in group]
                    ax.plot(x, y, marker="o", markersize=3, label=method)
                    ax.fill_between(x, [r["ci_low"] for r in group], [r["ci_high"] for r in group], alpha=.1)
            ax.set(xlabel="Inference calls" if axis == "calls" else "Observed tokens: completed-generation prefixes",
                   ylabel="Returned solution hidden success", ylim=(-.02, 1.02), title=title + "\n" + subtitle)
            if ax.get_legend_handles_labels()[0]:
                ax.legend(fontsize=8)
            else:
                ax.text(.5, .5, "No token grid configured", ha="center", transform=ax.transAxes)
            ax.grid(alpha=.2)
            fig.tight_layout()
            for suffix in ("png", "svg"):
                fig.savefig(out / f"success_vs_{axis}.{suffix}", dpi=160, metadata={"Date": None} if suffix == "svg" else None)
            plt.close(fig)
        ablation = [r for r in summary if r["axis"] == "calls" and r["budget"] == call_max and r["method"].startswith("rex")]
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar([r["method"] for r in ablation], [r["success"] for r in ablation], color="#287d8e",
               yerr=[[max(0., r["success"] - r["ci_low"]) for r in ablation],
                     [max(0., r["ci_high"] - r["success"]) for r in ablation]], capsize=4)
        ax.set(ylabel="Returned hidden success", ylim=(0, 1.05), title=f"{title}: {call_max}-call ablation\n{subtitle}")
        ax.tick_params(axis="x", rotation=15)
        fig.tight_layout()
        for suffix in ("png", "svg"):
            fig.savefig(out / f"ablation.{suffix}", dpi=160, metadata={"Date": None} if suffix == "svg" else None)
        plt.close(fig)
        events = [(r["trial_id"], json.loads(r["payload"])) for r in store.rows("SELECT trial_id,payload FROM events WHERE kind='step_committed'")]
        estimates = np.array([e["estimated_tokens"] for _, e in events])
        actuals = np.array([e["actual_tokens"] for _, e in events])
        fig, ax = plt.subplots(figsize=(6.5, 5))
        ax.scatter(estimates, actuals, s=16, alpha=.5)
        if len(estimates):
            maximum = max(max(estimates), max(actuals))
            ax.plot([0, maximum], [0, maximum], color="black", linestyle="--", linewidth=1)
        ax.set(xlabel="Pre-request estimated tokens", ylabel="Actual backend tokens", title=title + ": estimator calibration")
        fig.tight_layout()
        fig.savefig(out / "cost_estimator.png", dpi=160)
        plt.close(fig)
        failures: dict[str, dict] = {}
        for trial_id, event in events:
            categories = [o["status"] for o in event["child"]["evaluation"]["outcomes"] if o["status"] != "PASS"]
            if event["parse_status"] == "INVALID_COMPLETION":
                categories.append("INVALID_COMPLETION")
            if event["duplicate"]:
                categories.append("DUPLICATE_GENERATION")
            for category in categories:
                unit = "generation" if category in ("INVALID_COMPLETION", "DUPLICATE_GENERATION") else "test_outcome"
                denominator = len(events) if unit == "generation" else sum(len(e["child"]["evaluation"]["outcomes"]) for _, e in events)
                row = failures.setdefault(category, {"category": category, "count": 0, "unit": unit,
                                                    "denominator": denominator, "rate": 0., "representative_trial": trial_id})
                row["count"] += 1
                row["rate"] = row["count"] / row["denominator"]
        csv_file(out / "failure_analysis.csv", list(failures.values()))
        states = [store.load(j["id"]) for j in plan["jobs"]]
        ledgers = [s.ledger for s in states if s is not None]
        active = store.db.execute("SELECT value FROM metadata WHERE key='active_seconds'").fetchone()
        active_seconds = float(active[0]) if active else None
        backend_durations = []
        missing_backend_durations = 0
        for row in store.rows("SELECT result_blob FROM generations"):
            value = store.object(row["result_blob"])["raw"].get("total_duration")
            if type(value) is int and value >= 0:
                backend_durations.append(value / 1e9)
            else:
                missing_backend_durations += 1
        diagnostics = {"synthetic": synthetic, "generations": len(events),
                       "invalid_completions": sum(e["parse_status"] == "INVALID_COMPLETION" for _, e in events),
                       "duplicate_generations": sum(e["duplicate"] for _, e in events),
                       "root_generation_share": sum(e["parent_id"] == "root" for _, e in events) / len(events) if events else None,
                       "mean_depth": float(np.mean([e["child"]["depth"] for _, e in events])) if events else None,
                       "estimator_mae_tokens": float(np.mean(np.abs(estimates - actuals))) if events else None,
                       "estimator_mape": float(np.mean(np.abs(estimates - actuals) / np.maximum(1, actuals))) if events else None,
                       "actual_campaign_tokens": sum(x.prompt_tokens + x.output_tokens for x in ledgers),
                       "model_seconds": sum(x.model_seconds for x in ledgers), "judge_seconds": sum(x.judge_seconds for x in ledgers),
                       "model_time_definition": "client request round-trip; native backend duration exported separately",
                       "backend_total_duration_seconds": sum(backend_durations) if not missing_backend_durations else None,
                       "missing_backend_duration_requests": missing_backend_durations,
                       "orchestration_seconds": sum(x.orchestration_seconds for x in ledgers),
                       "active_campaign_seconds": active_seconds,
                       "timing_remainder_seconds": max(0., active_seconds - sum(x.model_seconds + x.judge_seconds + x.orchestration_seconds for x in ledgers)) if active_seconds is not None else None,
                       "extension_calls": sum(e["extension"] for _, e in events),
                       "extension_actual_tokens": sum(e["actual_tokens"] for _, e in events if e["extension"]),
                       "normalized_call_auc": {m: call_auc(evaluated["rows"], m, call_max) for m in methods}}
        write_json(out / "diagnostics.json", diagnostics)
        write_json(out / "pilot_resources.json", {
            "synthetic": synthetic, "source_evaluation": evaluated["version"],
            "mean_tokens_per_call": float(np.mean(actuals)) if len(actuals) else None,
            "mean_model_seconds_per_call": sum(x.model_seconds for x in ledgers) / len(events) if events else None,
            "mean_hidden_judge_seconds": float(np.mean([
                sum(o["wall_seconds"] + o["startup_seconds"] for o in e["evaluation"]["outcomes"])
                for e in evaluated["outcomes"]])) if evaluated["outcomes"] else None})
        replay(root, "representative", out / "replay.html", evaluated["version"])
        for selection in ("success", "loss"):
            try:
                replay(root, selection, out / f"replay_{selection}.html", evaluated["version"])
            except ValueError as exc:
                if "No recorded" not in str(exc):
                    raise
        primary = next((r for r in summary if r["method"] == "rex_progress_cost" and r["axis"] == "calls" and r["budget"] == call_max), None)
        finding = describe_finding(synthetic, primary, call_max)
        text = (f"# {'Synthetic verification' if synthetic else 'Measured results'}\n\n{finding}\n\n"
                f"Model: {config['model']['name']}. Exact setup: resolved_config.json, seal {frozen['seal_hash']}.\n\n"
                f"{subtitle}. All methods use the same prompts, parser, repair tests and limits.\n\n"
                "Success is correctness of the repair-selected returned solution on every hidden test. "
                "Call AUC is the arithmetic mean over all integer call checkpoints. "
                "Token curves use completed-generation prefixes; crossing requests remain charged to the campaign. "
                "Null tokens-per-success means undefined (zero successes), never zero cost.\n\n"
                "Progress credit is fractional pseudo-count shaping, with no inherited Bernoulli-posterior or optimality guarantee. "
                "This restricted stdio APPS study is not an official APPS score or full-paper reproduction. "
                "Public contamination, finite repair coverage, model seed behavior, nondeterministic programs, "
                "and near-duplicate tasks limit interpretation. Component comparisons are exploratory.\n")
        atomic_bytes(out / "results.md", text.encode())
        reproduce = ("# Regenerate from sealed evidence\n\n"
                     f"Search seal: {frozen['seal_hash']}\nEvaluation: {evaluated['version']}\n\n"
                     f"```powershell\nrexbench report --experiment \"{root}\" --evaluation {evaluated['version']} --out \"{out}\"\n```\n\n"
                     "No model calls or generated-code execution occur during report/replay. "
                     "Install with Python 3.11 and `uv sync --frozen --extra dev`. Source and dependencies are recorded in plan.json; "
                     "model/template/image pins in resolved_config.json. Raw requests/responses and outcomes are content-addressed "
                     "in artifacts/. Full raw responses are retained locally without automatic redaction. Do not redistribute dataset "
                     "or statements without checking their terms. No credentials are accepted in endpoint URLs.\n")
        atomic_bytes(out / "reproduce.md", reproduce.encode())
        return {"out": str(out), "evaluation": evaluated["version"], "synthetic": synthetic, "summary_rows": len(summary)}
    finally:
        store.close()
