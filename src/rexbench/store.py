from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .types import SearchCheckpoint
from .util import atomic_bytes, canonical, now, sha

SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS experiments(id TEXT PRIMARY KEY, manifest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS planned_trials(
 id TEXT PRIMARY KEY, task TEXT NOT NULL, method TEXT NOT NULL, seed INTEGER NOT NULL,
 UNIQUE(task,method,seed));
CREATE TABLE IF NOT EXISTS trial_states(
 id TEXT PRIMARY KEY REFERENCES planned_trials(id), status TEXT NOT NULL, stop_reason TEXT,
 checkpoint TEXT, lease_owner TEXT, lease_until REAL);
CREATE TABLE IF NOT EXISTS requests(
 id TEXT PRIMARY KEY, trial_id TEXT NOT NULL REFERENCES planned_trials(id), iteration INTEGER NOT NULL,
 state TEXT NOT NULL, request_blob TEXT NOT NULL, context_blob TEXT NOT NULL,
 response_blob TEXT, evaluation_blob TEXT, error TEXT, started TEXT, finished TEXT, latency REAL,
 UNIQUE(trial_id,iteration));
CREATE TABLE IF NOT EXISTS generations(
 request_id TEXT PRIMARY KEY REFERENCES requests(id), code_hash TEXT, parse_status TEXT NOT NULL,
 result_blob TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS arms(
 trial_id TEXT NOT NULL REFERENCES planned_trials(id), arm_id TEXT NOT NULL, state TEXT NOT NULL,
 PRIMARY KEY(trial_id,arm_id));
CREATE TABLE IF NOT EXISTS edges(
 request_id TEXT PRIMARY KEY REFERENCES requests(id), parent_id TEXT NOT NULL, child_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS test_outcomes(
 request_id TEXT NOT NULL REFERENCES requests(id), case_id TEXT NOT NULL, outcome TEXT NOT NULL,
 PRIMARY KEY(request_id,case_id));
CREATE TABLE IF NOT EXISTS snapshots(
 trial_id TEXT NOT NULL REFERENCES planned_trials(id), step INTEGER NOT NULL, snapshot TEXT NOT NULL,
 PRIMARY KEY(trial_id,step));
CREATE TABLE IF NOT EXISTS events(
 number INTEGER PRIMARY KEY AUTOINCREMENT, trial_id TEXT REFERENCES planned_trials(id),
 kind TEXT NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT,'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT,'events are append-only'); END;
"""


class Store:
    def __init__(self, root: Path, readonly: bool = False):
        self.root = root
        self.artifacts = root / "artifacts"
        if readonly:
            self.db = sqlite3.connect(f"file:{(root / 'state.sqlite').as_posix()}?mode=ro", uri=True)
        else:
            root.mkdir(parents=True, exist_ok=True)
            self.artifacts.mkdir(exist_ok=True)
            self.db = sqlite3.connect(root / "state.sqlite", isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        if not readonly:
            self.db.execute("PRAGMA journal_mode=WAL")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError("Unsupported database schema")
            self.db.executescript(SCHEMA)
            self.db.execute("PRAGMA user_version=1")

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def put(self, value: bytes | str | dict | list) -> str:
        data = value if isinstance(value, bytes) else value.encode() if isinstance(value, str) else canonical(value)
        digest = sha(data)
        path = self.artifacts / digest[:2] / digest[2:]
        if not path.exists():
            atomic_bytes(path, data)
        if sha(path.read_bytes()) != digest:
            raise RuntimeError("Artifact hash mismatch")
        return digest

    def get(self, digest: str) -> bytes:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid artifact digest")
        data = (self.artifacts / digest[:2] / digest[2:]).read_bytes()
        if sha(data) != digest:
            raise RuntimeError("Artifact hash mismatch")
        return data

    def object(self, digest: str):
        return json.loads(self.get(digest))

    def event(self, trial_id: str, kind: str, payload: dict) -> int:
        result = self.db.execute("INSERT INTO events(trial_id,kind,payload,created) VALUES(?,?,?,?)",
                                 (trial_id, kind, canonical(payload).decode(), now())).lastrowid
        assert result is not None
        return result

    def checkpoint(self, state: SearchCheckpoint, status: str):
        digest = self.put(state.model_dump(mode="json"))
        self.db.execute("UPDATE trial_states SET status=?,stop_reason=?,checkpoint=? WHERE id=?",
                        (status, state.stop_reason, digest, state.trial_id))

    def load(self, trial_id: str) -> SearchCheckpoint | None:
        row = self.db.execute("SELECT checkpoint FROM trial_states WHERE id=?", (trial_id,)).fetchone()
        return SearchCheckpoint.model_validate(self.object(row[0])) if row and row[0] else None

    def pending(self, trial_id):
        return self.db.execute("SELECT * FROM requests WHERE trial_id=? AND state!='committed' ORDER BY iteration",
                               (trial_id,)).fetchone()

    def snapshots(self, trial_id):
        return [json.loads(r[0]) for r in self.db.execute(
            "SELECT snapshot FROM snapshots WHERE trial_id=? ORDER BY step", (trial_id,))]

    def rows(self, query, params=()):
        return [dict(r) for r in self.db.execute(query, params)]

    def logical_dump(self):
        tables = ["metadata", "experiments", "planned_trials", "trial_states", "requests", "generations",
                  "arms", "edges", "test_outcomes", "snapshots", "events"]
        return {t: self.rows(f"SELECT * FROM {t} ORDER BY rowid") for t in tables}
