"""Evidence files are encrypted on disk, readable only with the key, and tied to their case."""
import base64
import shutil

import pytest

from promoflow import config, secure_files, storage


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EVIDENCE_DIR", str(tmp_path))
    return tmp_path


def test_stored_file_is_not_plain_and_reads_back(evidence):
    data = b"%PDF-1.4 certificate of Dr Example, passport 123456"
    path, sha = storage.save(7, "cert.pdf", data)
    on_disk = open(path, "rb").read()
    assert data not in on_disk and b"passport" not in on_disk
    assert on_disk.startswith(storage.MAGIC)
    assert storage.read(path) == data and len(sha) == 64


def test_same_bytes_get_the_same_name_but_a_fresh_nonce(evidence):
    p1, _ = storage.save(1, "a.pdf", b"same")
    first = open(p1, "rb").read()
    p2, _ = storage.save(1, "a.pdf", b"same")
    assert p1 == p2 and open(p2, "rb").read() != first and storage.read(p2) == b"same"


def test_no_key_means_no_storage(evidence, monkeypatch):
    monkeypatch.setattr(config, "DOCUMENT_ENCRYPTION_KEY", "")
    with pytest.raises(storage.StorageError):
        storage.save(1, "a.pdf", b"x")
    assert not list(evidence.rglob("*.pdf"))          # nothing was written in the clear


def test_wrong_key_is_rejected(evidence, monkeypatch):
    path, _ = storage.save(1, "a.pdf", b"secret")
    monkeypatch.setattr(config, "DOCUMENT_ENCRYPTION_KEY", base64.urlsafe_b64encode(b"z" * 32).decode())
    with pytest.raises(storage.StorageError):
        storage.read(path)


def test_tampering_is_detected(evidence):
    path, _ = storage.save(1, "a.pdf", b"secret")
    blob = bytearray(open(path, "rb").read())
    blob[-1] ^= 1
    open(path, "wb").write(bytes(blob))
    with pytest.raises(storage.StorageError):
        storage.read(path)


def test_file_cannot_be_moved_to_another_case(evidence):
    path, _ = storage.save(1, "a.pdf", b"secret")
    other = evidence / "2"
    other.mkdir()
    moved = other / path.split("\\")[-1].split("/")[-1]
    shutil.copy(path, moved)
    with pytest.raises(storage.StorageError):
        storage.read(str(moved))


def test_legacy_plain_file_still_reads_and_the_tool_converts_it(evidence):
    folder = evidence / "3"
    folder.mkdir()
    import hashlib
    data = b"old plain file"
    plain = folder / f"{hashlib.sha256(data).hexdigest()}_old.pdf"
    plain.write_bytes(data)
    assert storage.read(str(plain)) == data
    assert secure_files.verify() == 1                      # reports the plain file
    assert secure_files.encrypt_all(dry_run=True) == 0 and plain.read_bytes() == data
    assert secure_files.encrypt_all(dry_run=False) == 0
    assert plain.read_bytes().startswith(storage.MAGIC) and storage.read(str(plain)) == data
    assert secure_files.verify() == 0
