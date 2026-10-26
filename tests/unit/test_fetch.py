import hashlib
import io
import tarfile

import pytest

from rexbench.data.fetch import download_ranges, extract_archive


@pytest.mark.parametrize("name,kind", [("../escape", "file"), ("/absolute", "file"), ("safe/link", "symlink")])
def test_archive_traversal_links_rejected(tmp_path, name, kind):
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        item = tarfile.TarInfo(name)
        if kind == "symlink":
            item.type, item.linkname = tarfile.SYMTYPE, "../../escape"
            stream.addfile(item)
        else:
            item.size = 3
            stream.addfile(item, io.BytesIO(b"bad"))
    with pytest.raises(ValueError, match="Unsafe"):
        extract_archive(archive, tmp_path / "safe")
    assert not (tmp_path / "escape").exists()


def test_bounded_extraction_and_collision(tmp_path):
    archive = tmp_path / "fixture.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        item = tarfile.TarInfo("APPS/task/question.txt")
        item.size = 5
        stream.addfile(item, io.BytesIO(b"hello"))
    assert extract_archive(archive, tmp_path / "out") == 5
    assert extract_archive(archive, tmp_path / "out") == 5
    with pytest.raises(ValueError, match="byte limit"):
        extract_archive(archive, tmp_path / "limited", max_bytes=4)
    (tmp_path / "out/APPS/task/question.txt").write_bytes(b"changed")
    with pytest.raises(ValueError, match="overwrite"):
        extract_archive(archive, tmp_path / "out")


def test_range_download_resume_and_hash(tmp_path, monkeypatch):
    data = b"known official-fixture bytes" * 100
    gets = []
    class Response(io.BytesIO):
        def __init__(self, payload, status, headers):
            super().__init__(payload)
            self.status, self.headers = status, headers
    def urlopen(request, timeout):
        if request.get_method() == "HEAD":
            return Response(b"", 200, {"Content-Length": str(len(data)), "ETag": '"fixture"'})
        gets.append(request.get_header("Range"))
        return Response(data, 206, {"Content-Range": f"bytes 0-{len(data)-1}/{len(data)}"})
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    first = download_ranges("https://fixture.invalid/archive", tmp_path / "archive.part", 10000)
    second = download_ranges("https://fixture.invalid/archive", tmp_path / "archive.part", 10000)
    assert first == second
    assert first[0] == hashlib.sha256(data).hexdigest()
    assert (tmp_path / "archive.part").read_bytes() == data
    assert len(gets) == 1
