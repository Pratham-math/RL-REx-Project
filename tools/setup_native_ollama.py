"""Extract official Windows CPU or Vulkan runtime members by verified ZIP ranges.

Downloads only the requested backend. This is trusted setup code, never a code judge.
The original HTTPS release URL, ZIP CRCs and extracted-file SHA256 values are recorded.
"""
import concurrent.futures
import argparse
import json
import struct
import time
import urllib.request
import zlib
from pathlib import Path

from rexbench.util import atomic_bytes, sha, write_json

URL = "https://github.com/ollama/ollama/releases/download/v0.40.11/ollama-windows-amd64.zip"


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=['cpu', 'vulkan'], default='cpu')
    args = parser.parse_args()
    members = json.loads((project / "reports/setup/ollama_standard_members.json").read_bytes())
    selected = [m for m in members if m["name"] == "ollama.exe" or
                (m["name"].startswith("lib/ollama/") and m["name"].count("/") == 2 and m["size"]) or
                (args.backend == 'vulkan' and m['name'].startswith('lib/ollama/vulkan/') and m['size'])]
    destination = project / (".runtime/ollama-0.40.11-" + args.backend)
    deadline = time.monotonic() + 180

    def get(start, size):
        if size > 1024**2:
            ranges = [(start + i, min(1024**2, size - i)) for i in range(0, size, 1024**2)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as chunks:
                return b"".join(chunks.map(lambda pair: get(*pair), ranges))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Native runtime setup deadline reached")
        request = urllib.request.Request(URL, headers={"Range": f"bytes={start}-{start+size-1}",
                                                      "User-Agent": "rexbench-local-setup"})
        with urllib.request.urlopen(request, timeout=min(15, remaining)) as response:
            if response.status != 206:
                raise ValueError("Official release server did not honor the range")
            result = bytearray()
            while len(result) < size:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Native runtime setup deadline reached")
                block = response.read1(min(65536, size - len(result)))
                if not block:
                    break
                result.extend(block)
        if len(result) != size:
            raise ValueError("Incomplete runtime member range")
        return bytes(result)

    def extract(member):
        path = (destination / member["name"]).resolve()
        if not path.is_relative_to(destination.resolve()):
            raise ValueError("Unsafe release member path")
        cached = project / '.runtime/ollama-0.40.11-cpu' / member['name']
        if path.exists():
            data = path.read_bytes()
        elif cached.exists():
            data = cached.read_bytes()
        else:
            header = get(member["header_offset"], 30)
            values = struct.unpack("<IHHHHHIIIHH", header)
            if values[0] != 0x04034B50:
                raise ValueError("Invalid ZIP local header")
            start = member["header_offset"] + 30 + values[-2] + values[-1]
            compressed = get(start, member["compressed"])
            data = zlib.decompress(compressed, -15) if member["compression"] == 8 else compressed
        if len(data) != member["size"] or zlib.crc32(data) != member["crc"]:
            raise ValueError("Release member size/CRC mismatch")
        atomic_bytes(path, data)
        return {"path": member["name"], "sha256": sha(data), "bytes": len(data), "zip_crc": member["crc"]}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(extract, selected))
    report = {"source": URL, "version": "0.40.11", "runtime": args.backend + " selected release members",
              "full_archive_checksum_verified": False, "validation": "HTTPS origin plus per-member ZIP CRC and retained SHA256",
              "files": records, "executable": str(destination / "ollama.exe")}
    name = 'native_runtime.json' if args.backend == 'cpu' else 'native_runtime_vulkan.json'
    write_json(project / 'reports/setup' / name, report)
    print(json.dumps({"files": len(records), "executable": report["executable"]}))


if __name__ == "__main__":
    main()
