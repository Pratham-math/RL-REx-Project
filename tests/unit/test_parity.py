from pathlib import Path

import pytest

from rexbench.parity import parity


def test_pinned_authors_scheduler(tmp_path):
    upstream = Path(__file__).resolve().parents[2] / "vendor" / "REx"
    if not (upstream / ".git").exists():
        pytest.skip("Fetch pinned upstream with docs/setup_upstream.ps1 for direct conformance")
    evidence = parity(upstream, tmp_path / "parity.json")
    assert evidence["upstream_commit"] == "371e879da5b1fff0d32a695ad37dcac50f74721b"
    assert len(evidence["fixtures"]) == 6
    assert all(f["matched"] for f in evidence["fixtures"])
    assert evidence["fixtures"][0]["actions"] == [0, 1, 0, 2, 2, 2, 4]
