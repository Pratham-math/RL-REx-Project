"""Small APPS development snapshots from the dataset linked by the authors.

The viewer does not expose an immutable revision parameter: preserve the exact response
hash and disclose that distinction rather than pretending it is a verified full archive.
"""
import json
import urllib.parse
import urllib.request
from pathlib import Path

from ..util import atomic_bytes, now, sha, write_json

REPOSITORY = "https://huggingface.co/datasets/codeparrot/apps"
INFO = "https://huggingface.co/api/datasets/codeparrot/apps"


def get_json(url, cap):
    with urllib.request.urlopen(url, timeout=30) as response:
        body = response.read(cap + 1)
        if len(body) > cap:
            raise ValueError("Dataset response exceeded its byte cap")
        return json.loads(body), body


def fetch_mirror(out: Path, split: str, offset: int, length: int, revision: str | None = None):
    if split not in ("train", "test") or offset < 0 or not 1 <= length <= 100:
        raise ValueError("Expected train/test, nonnegative offset and 1..100 rows")
    if out.exists():
        raise FileExistsError("Mirror snapshot output must be a new directory")
    before, _ = get_json(INFO, 1024**2)
    if revision and before["sha"] != revision:
        raise ValueError("Dataset repository revision drift")
    query = urllib.parse.urlencode({"dataset": "codeparrot/apps", "config": "all", "split": split,
                                    "offset": offset, "length": length})
    url = "https://datasets-server.huggingface.co/rows?" + query
    snapshot, raw = get_json(url, 16 * 1024**2)
    after, _ = get_json(INFO, 1024**2)
    if before["sha"] != after["sha"]:
        raise ValueError("Dataset repository changed while acquiring the snapshot")
    rows = snapshot.get("rows", [])
    if len(rows) != length or any(r.get("truncated_cells") for r in rows):
        raise ValueError("Missing/truncated mirror rows cannot be used as complete tasks")
    ids = [r["row"]["problem_id"] for r in rows]
    if any(type(i) is not int or i < 0 for i in ids) or len(ids) != len(set(ids)):
        raise ValueError("Invalid or duplicate mirror task IDs")
    out.mkdir(parents=True)
    atomic_bytes(out / "rows_snapshot.json", raw)
    for item in rows:
        row = item["row"]
        task = out / split / f"{row['problem_id']:04d}"
        task.mkdir(parents=True)
        atomic_bytes(task / "question.txt", row["question"].encode("utf-8"))
        write_json(task / "metadata.json", {"difficulty": row["difficulty"], "url": row["url"]})
        write_json(task / "input_output.json", json.loads(row["input_output"]) if row["input_output"] else {})
        write_json(task / "solutions.json", json.loads(row["solutions"]) if row["solutions"] else [])
    record = {"schema_version": 1, "source_url": url, "repository": REPOSITORY,
              "repository_revision_observed_before_and_after": before["sha"], "accessed": now(),
              "snapshot_sha256": sha(raw), "source_revision": f"rows-sha256:{sha(raw)};repo:{before['sha']}",
              "split": split, "offset": offset, "length": length, "task_ids": ids,
              "license": "MIT per codeparrot/apps dataset card; retain original problem-source attribution",
              "revision_limitation": "Rows API has no revision parameter; exact response is frozen by hash, not claimed to be an archive checksum",
              "byte_policy": "Question and test strings preserved after JSON decoding; no whitespace/line-ending normalization"}
    write_json(out / "source_snapshot.json", record)
    return record
