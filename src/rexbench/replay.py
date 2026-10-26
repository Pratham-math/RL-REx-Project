from __future__ import annotations

import html
import json
from pathlib import Path

from .store import Store
from .util import atomic_bytes, read_json


def tree_svg(events: list[dict]) -> str:
    nodes = {"root": (45, 45)}
    parts = []
    maximum_depth = 0
    for i, event in enumerate(events, 1):
        child = event["child"]
        depth = int(child["depth"])
        maximum_depth = max(maximum_depth, depth)
        nodes[child["arm_id"]] = (70 + i * 115, 45 + depth * 90)
        x0, y0 = nodes[event["parent_id"]]
        x1, y1 = nodes[child["arm_id"]]
        parts.append(f"<line x1='{x0}' y1='{y0}' x2='{x1}' y2='{y1}' stroke='#8a99a6' stroke-width='2'/>")
    for arm_id, (x, y) in nodes.items():
        record = next((e for e in events if e["child"]["arm_id"] == arm_id), None)
        h = float(record["child"]["h"]) if record else 0.
        color = f"rgb({int(40 + h * 15)},{int(70 + h * 70)},{int(150 - h * 70)})" if record else "#66717c"
        parts.append(f"<circle cx='{x}' cy='{y}' r='25' fill='{color}'/>")
        label = f"{h:.2f}" if record else "root"
        parts.append(f"<text x='{x}' y='{y+5}' text-anchor='middle' fill='white' font-size='13'>{html.escape(label)}</text>")
        parts.append(f"<text x='{x}' y='{y+43}' text-anchor='middle' fill='#172b3a' font-size='12'>{html.escape(arm_id)}</text>")
    return (f"<div style='overflow:auto'><svg xmlns='http://www.w3.org/2000/svg' role='img' aria-label='Recorded repair tree' "
            f"width='{max(420, 160 + len(events)*115)}' height='{120 + maximum_depth*90}'>" + "".join(parts) + "</svg></div>")


def replay(root: Path, selection: str, out: Path, evaluation_version: str | None = None):
    store = Store(root, readonly=True)
    try:
        plan = read_json(root / "plan.json")
        trials = store.rows("SELECT p.*,s.status FROM planned_trials p JOIN trial_states s ON p.id=s.id ORDER BY p.rowid")
        recorded = [t for t in trials if store.snapshots(t["id"])]
        if not recorded:
            raise ValueError("No actual saved search events available")
        evals = sorted((root / "evaluations").glob("*/evaluation.json"))
        if evaluation_version:
            selected_evaluation = root / "evaluations" / evaluation_version / "evaluation.json"
            if selected_evaluation not in evals:
                raise ValueError("Requested saved evaluation does not exist")
            evals = [selected_evaluation]
        elif len(evals) > 1:
            raise ValueError("Select an evaluation version explicitly for replay annotations")
        if selection in ("success", "loss"):
            if len(evals) != 1:
                raise ValueError("Success/loss selection requires exactly one saved evaluation version")
            evaluation = read_json(evals[0])
            final_budget = max(plan["config"]["budgets"]["call_checkpoints"])
            ids = {r["trial_id"] for r in evaluation["rows"] if r["axis"] == "calls" and r["budget"] == final_budget
                   and bool(r["solved"]) == (selection == "success")}
            candidates = [t for t in recorded if t["id"] in ids]
            if not candidates:
                raise ValueError(f"No recorded {selection} case exists; no example was invented")
            trial = candidates[0]
        elif selection == "representative":
            trial = max(recorded, key=lambda t: max(s["step"] for s in store.snapshots(t["id"])))
        else:
            candidates = [t for t in recorded if t["id"] == selection]
            if not candidates:
                raise ValueError("Requested trial has no saved events")
            trial = candidates[0]
        events = store.rows("SELECT * FROM events WHERE trial_id=? AND kind='step_committed' ORDER BY number", (trial["id"],))
        repair_rows = [json.loads(line) for line in (root / "repair.jsonl").read_bytes().splitlines()]
        task = next(t for t in repair_rows if t["task_id"] == trial["task"])
        escape = html.escape
        parts = ["<!doctype html><html><head><meta charset='utf-8'>",
                 "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'\">",
                 "<title>REx recorded search</title><style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem;background:#f4f6f8;color:#172b3a}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:1rem;border:1px solid #ccd}details{margin:1rem 0;padding:.8rem;border:1px solid #aaa}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:.4rem}</style></head><body>"]
        label = "SYNTHETIC FIXTURE TRACE — no empirical model result" if plan["config"]["experiment"]["track"] == "synthetic" else "Recorded local-model search"
        parts += [f"<h1>{escape(label)}</h1><p>{escape(trial['task'])} · {escape(trial['method'])} · seed {trial['seed']}</p>",
                  f"<h2>Problem</h2><pre>{escape(task['statement'])}</pre>",
                  "<p>Nodes follow generation order. Each parent → child is a recorded refinement edge. Hidden tests did not select these returns.</p>"]
        parts.append(tree_svg([json.loads(e["payload"]) for e in events]))
        for event in events:
            data = json.loads(event["payload"])
            child = data["child"]
            code = store.get(child["code_hash"]).decode() if child["code_hash"] else "[INVALID COMPLETION]"
            parts.append(f"<details open><summary>{escape(data['parent_id'])} → {escape(child['arm_id'])}: repair h={child['h']:.3f}, depth {child['depth']}</summary>")
            parts.append(f"<p>Estimated tokens {data['estimated_tokens']:.1f}; actual {data['actual_tokens']}; cumulative {data['snapshot']['tokens']}; parent α,β after: {escape(str(data['parent_after']))}</p>")
            parts.append(f"<pre>{escape(code)}</pre><details><summary>Selection draws, priorities and priors</summary><pre>{escape(json.dumps(data['decision'], indent=2))}</pre></details>")
            parts.append(f"<details><summary>Exact prompt and failure feedback</summary><pre>{escape(data['prompt'])}</pre></details>")
            parts.append(f"<details><summary>Resource ledger</summary><pre>{escape(json.dumps(data['ledger'], indent=2))}</pre></details></details>")
        if evals:
            evaluation = read_json(evals[-1])
            annotations = [r for r in evaluation["rows"] if r["trial_id"] == trial["id"]]
            parts.append("<h2>Post-search hidden evaluation annotations</h2><p>Evaluation version " + escape(evaluation["version"]) + "</p><pre>" + escape(json.dumps(annotations, indent=2)) + "</pre>")
        parts.append("</body></html>")
        atomic_bytes(out, "".join(parts).encode())
        return {"trial_id": trial["id"], "events": len(events), "out": str(out), "label": label}
    finally:
        store.close()
