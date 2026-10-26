
import pytest

from rexbench.data.apps import load_repair, prepare_dataset
from rexbench.data.audit import audit_dataset
from rexbench.judge.mock import MockJudge
from rexbench.util import read_json, write_json


def test_local_release_import_audit_and_search_separation(tmp_path, config):
    reviews = {}
    for split in ("train", "test"):
        directory = tmp_path / "raw" / split / "0000"
        directory.mkdir(parents=True)
        statement = f"{split}: Echo integer.\nExample: 11"
        (directory / "question.txt").write_bytes(statement.encode())
        pairs = [(f"{i}\n", f"{i}\n") for i in range(10, 25)]
        write_json(directory / "input_output.json", {"inputs": [p[0] for p in pairs], "outputs": [p[1] for p in pairs]})
        write_json(directory / "metadata.json", {"difficulty": "interview", "url": f"https://fixture.invalid/{split}"})
        write_json(directory / "solutions.json", ["print(input())"])
        reviews[f"{split}/0000"] = {"comparator": "tokens_v1", "comparator_justification": "integer output",
                                    "examples_reviewed": True, "examples": ["11\n"], "vetted_reference_indices": [0]}
    manual = tmp_path / "manual.json"
    write_json(manual, reviews)
    config.data.raw_train = str(tmp_path / "raw/train")
    config.data.raw_test = str(tmp_path / "raw/test")
    config.data.dev_count = 1
    config.data.evaluation_count = 1
    config.data.source_revision = "fixture-sha"
    config.data.license = "handwritten synthetic fixture"
    config.data.manual_audit = str(manual)
    destination = tmp_path / "data"
    manifest = prepare_dataset(config, destination)
    assert manifest["task_ids"] == {"dev": ["train/0000"], "final": ["test/0000"]}
    public = load_repair(destination / "final_repair.jsonl")
    assert "11\n" in [c.input for c in public[0].repair_tests]
    serialized = (destination / "final_repair.jsonl").read_text()
    assert "solutions" not in serialized and "hidden_tests" not in serialized and "reference" not in serialized
    judge = MockJudge({"print(input())": {"default": "PASS"}})
    result = audit_dataset(destination / "manifest.json", judge, destination / "audit.json")
    assert result["passed"] and result["synthetic"]
    class NoCalls:
        image_digest = judge.image_digest
        def evaluate(self, *_args):
            raise AssertionError("Immutable completed audit should be reused without judging")
    assert audit_dataset(destination / "manifest.json", NoCalls(), destination / "audit.json") == result
    assert read_json(destination / "manifest.json")["audit_status"] == "pending"  # audit is a separate immutable record
    with (destination / "dev_hidden.jsonl").open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="hash mismatch"):
        audit_dataset(destination / "manifest.json", judge, destination / "other_audit.json")


def test_no_silent_comparator_or_reference_inference(tmp_path, config):
    with pytest.raises(ValueError, match="source_revision"):
        prepare_dataset(config, tmp_path / "data")
