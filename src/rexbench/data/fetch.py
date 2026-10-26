"""Bounded official archive acquisition and safe extraction; no candidate execution."""
from __future__ import annotations

import hashlib
import os
import tarfile
import time
import math
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ..util import now, read_json, sha, write_json

OFFICIAL_URL = "https://people.eecs.berkeley.edu/~hendrycks/APPS.tar.gz"


def download_ranges(url: str, partial: Path, max_bytes: int, timeout_seconds: float = 300):
    """Resume bounded HTTP ranges against a stable ETag; no inference requests involved."""
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("Download timeout must be finite and positive")
    deadline = time.monotonic() + timeout_seconds
    with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=min(20, timeout_seconds)) as response:
        headers = dict(response.headers)
        size = int(response.headers["Content-Length"])
        etag = response.headers.get("ETag")
    if size <= 0 or size > max_bytes or not etag:
        raise ValueError("Official archive needs a bounded content length and stable ETag")
    parts = partial.parent / "APPS.parts"
    parts.mkdir(exist_ok=True)
    state_file = parts / "source.json"
    identity = {"url": url, "etag": etag, "bytes": size}
    if state_file.exists() and read_json(state_file) != identity:
        raise ValueError("Download source changed; use a new directory")
    write_json(state_file, identity)
    chunk_size = 4 * 1024**2
    count = (size + chunk_size - 1) // chunk_size

    def one(index):
        start, end = index * chunk_size, min(size, (index + 1) * chunk_size) - 1
        target = parts / f"{index:05d}.part"
        expected = end - start + 1
        if target.exists() and target.stat().st_size == expected:
            return target
        error = None
        for _ in range(3):
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Dataset download time allowance reached; completed ranges remain resumable")
                request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}", "If-Range": etag})
                with urllib.request.urlopen(request, timeout=min(20, remaining)) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{size}":
                        raise ValueError("Server did not preserve the requested archive range")
                    buffer = bytearray()
                    while len(buffer) <= expected:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Dataset download time allowance reached")
                        chunk = response.read1(min(65536, expected + 1 - len(buffer)))
                        if not chunk:
                            break
                        buffer.extend(chunk)
                    data = bytes(buffer)
                if len(data) != expected:
                    raise ValueError("Incomplete archive range")
                from ..util import atomic_bytes
                atomic_bytes(target, data)
                return target
            except (OSError, ValueError) as exc:
                error = exc
        raise RuntimeError(f"Archive range {index} failed after three transport attempts: {error}")

    done = 0
    pool = ThreadPoolExecutor(max_workers=8)
    futures = [pool.submit(one, i) for i in range(count)]
    try:
        for future in as_completed(futures):
            future.result()
            done += 1
            write_json(partial.parent / "download_progress.json", {"completed_ranges": done, "total_ranges": count,
                                                                 "percent": round(100 * done / count, 1)})
    finally:
        for future in futures:
            future.cancel()
        pool.shutdown(wait=True, cancel_futures=True)
    digest = hashlib.sha256()
    with partial.open("wb") as target:
        for i in range(count):
            data = (parts / f"{i:05d}.part").read_bytes()
            digest.update(data)
            target.write(data)
        target.flush()
        os.fsync(target.fileno())
    return digest.hexdigest(), size, headers


def extract_archive(archive: Path, destination: Path, max_bytes: int = 8 * 1024**3):
    destination = destination.resolve()
    total = 0
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            target = (destination / member.name).resolve()
            if not target.is_relative_to(destination) or member.issym() or member.islnk():
                raise ValueError("Unsafe archive path/link")
            if not member.isdir() and not member.isfile():
                raise ValueError("Unsupported archive member")
            if member.size < 0 or member.size > 256 * 1024**2:
                raise ValueError("Invalid archive member size")
            total += member.size
            if total > max_bytes:
                raise ValueError("Extracted dataset exceeds configured byte limit")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = source.extractfile(member)
                assert stream is not None
                # Refuse unexpected collisions; partial downloads/extraction can be resumed safely.
                payload = stream.read()
                if target.exists() and sha(target.read_bytes()) != sha(payload):
                    raise ValueError(f"Archive extraction would overwrite changed data: {member.name}")
                if not target.exists():
                    target.write_bytes(payload)
    return total


def fetch_apps(destination: Path, checksum: str | None = None, timeout_seconds: float = 300):
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "APPS.tar.gz"
    record_path = destination / "download.json"
    if not archive.exists():
        partial = archive.with_suffix(".gz.part")
        actual, size, headers = download_ranges(OFFICIAL_URL, partial, 2 * 1024**3, timeout_seconds)
        if checksum and actual != checksum:
            raise ValueError("Downloaded archive checksum mismatch")
        os.replace(partial, archive)
        record = {"schema_version": 1, "url": OFFICIAL_URL, "accessed": now(), "sha256": actual,
                  "bytes": size, "headers": headers, "published_checksum_supplied": checksum is not None,
                  "license": "Archive/problem licenses must be reviewed; repository MIT is recorded separately"}
        write_json(record_path, record)
    else:
        record = read_json(record_path)
        if sha(archive.read_bytes()) != record["sha256"] or (checksum and checksum != record["sha256"]):
            raise ValueError("Existing archive checksum mismatch")
    extracted = extract_archive(archive, destination)
    record["extracted_bytes"] = extracted
    write_json(record_path, record)
    return record
