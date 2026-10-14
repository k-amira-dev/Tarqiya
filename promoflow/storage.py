"""Evidence file storage: a local folder in development. The online test deployment will swap this module's
body for Supabase Storage without changing its callers (`save`/`read` stay the same two functions).

Files are content-addressed (sha256) inside a per-case folder, so re-uploading identical bytes never
duplicates on disk.
"""
from pathlib import Path

import hashlib

from promoflow import config


# Keep only letters, digits and . _ - so a file name can never contain path tricks like ../../ or odd characters.
def _safe_name(filename: str) -> str:
    name = "".join(c for c in filename if c.isalnum() or c in "._-")
    return name or "file"


# Store an uploaded file. Returns where it was stored and its SHA-256 fingerprint.
def save(case_id: int, filename: str, data: bytes) -> tuple[str, str]:
    """Write `data` under the case's evidence folder. Returns (stored_path, sha256)."""
    # The fingerprint of the file contents, used in the file name: the same bytes always get the same name.
    sha256 = hashlib.sha256(data).hexdigest()
    # One folder per case, so evidence from different applications never mixes.
    folder = Path(config.EVIDENCE_DIR) / str(case_id)
    folder.mkdir(parents=True, exist_ok=True)
    stored_path = folder / f"{sha256}_{_safe_name(filename)}"
    stored_path.write_bytes(data)
    return str(stored_path), sha256


# Read a stored file back, given the path saved in the case_document table.
def read(stored_path: str) -> bytes:
    return Path(stored_path).read_bytes()
