from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()


def sha(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def fingerprint(value: Any) -> str:
    return sha(canonical(value))


def seed_for(*parts: Any) -> int:
    return int(fingerprint(parts)[:16], 16)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".rex-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        if sha(path.read_bytes()) != sha(data):
            raise OSError("Atomic artifact verification failed")
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def write_json(path: Path, value: Any) -> None:
    atomic_bytes(path, canonical(value) + b"\n")


def read_json(path: Path) -> Any:
    return json.loads(path.read_bytes())


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    atomic_bytes(path, b"".join(canonical(row) + b"\n" for row in rows))
