import sqlite3

import pytest

from conftest import initialize
from rexbench.data.mirror import fetch_mirror


def test_event_log_rejects_update_and_delete(tmp_path, job):
    store = initialize(tmp_path, job)
    store.event(job["id"], "fixture", {"value": 1})
    for sql in ["UPDATE events SET kind='changed'", "DELETE FROM events"]:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store.db.execute(sql)
    assert len(store.rows("SELECT * FROM events")) == 1
    store.close()


@pytest.mark.parametrize("invalid", ["truncated", "revision"])
def test_mirror_rejects_unreliable_snapshot(tmp_path, monkeypatch, invalid):
    import rexbench.data.mirror as mirror
    versions = iter(["a", "b" if invalid == "revision" else "a"])
    def get(url, cap):
        if url == mirror.INFO:
            return {"sha": next(versions)}, b"{}"
        return {"rows": [{"truncated_cells": ["input_output"] if invalid == "truncated" else [],
                           "row": {"problem_id": 1}}]}, b"{}"
    monkeypatch.setattr(mirror, "get_json", get)
    with pytest.raises(ValueError, match="truncated|changed"):
        fetch_mirror(tmp_path / "data", "train", 0, 1)
    assert not (tmp_path / "data").exists()
