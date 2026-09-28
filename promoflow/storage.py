"""Evidence file storage: a local folder in development. The online test deployment will swap this module's
body for Supabase Storage without changing its callers (`save`/`read` stay the same two functions).

Files are content-addressed (sha256) inside a per-case folder, so re-uploading identical bytes never
duplicates on disk.
"""
from pathlib import Path

import hashlib

from promoflow import config


def _safe_name(filename: str) -> str:
    name = "".join(c for c in filename if c.isalnum() or c in "._-")
    return name or "file"


def save(case_id: int, filename: str, data: bytes) -> tuple[str, str]:
    """Write `data` under the case's evidence folder. Returns (stored_path, sha256)."""
    sha256 = hashlib.sha256(data).hexdigest()
    folder = Path(config.EVIDENCE_DIR) / str(case_id)
    folder.mkdir(parents=True, exist_ok=True)
    stored_path = folder / f"{sha256}_{_safe_name(filename)}"
    stored_path.write_bytes(data)
    return str(stored_path), sha256


def read(stored_path: str) -> bytes:
    return Path(stored_path).read_bytes()
