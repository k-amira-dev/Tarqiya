"""Evidence file storage: a local folder in development. The online test deployment will swap this module's
body for Supabase Storage without changing its callers (`save`/`read` stay the same two functions).

Files are content-addressed (sha256) inside a per-case folder, so re-uploading identical bytes never
duplicates on disk.

Every file is ENCRYPTED before it touches the disk (AES-256-GCM). The key lives only in .env / Streamlit Secrets
(DOCUMENT_ENCRYPTION_KEY), never next to the files or in the database. The file's case folder and fingerprint are
bound into the encryption, so a stolen copy cannot be moved to another case, and any change to the bytes is detected
when the file is read.
"""
import base64
import hashlib
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from promoflow import config

MAGIC = b"PFE1"          # marks an encrypted file (format version 1): MAGIC + 12-byte nonce + ciphertext and tag
NONCE_BYTES = 12


class StorageError(Exception):
    """The key is missing or wrong, or a stored file was damaged or changed."""


# The 32-byte key from the settings. Refuses to work without a good key, so a missing key can never mean "store in clear".
def _key() -> bytes:
    raw = config.DOCUMENT_ENCRYPTION_KEY
    if not raw:
        raise StorageError("DOCUMENT_ENCRYPTION_KEY is not set: refusing to store or read evidence files without it.")
    try:
        key = base64.urlsafe_b64decode(raw.encode())
    except Exception as exc:  # noqa: BLE001
        raise StorageError("DOCUMENT_ENCRYPTION_KEY is not valid URL-safe base64.") from exc
    if len(key) != 32:
        raise StorageError("DOCUMENT_ENCRYPTION_KEY must decode to exactly 32 bytes.")
    return key


# What the encryption is tied to: the case folder and the file fingerprint taken from the stored path.
def _aad_for(path: Path) -> bytes:
    return f"{path.parent.name}:{path.name.split('_', 1)[0]}".encode()


def encrypt(data: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    return MAGIC + nonce + AESGCM(_key()).encrypt(nonce, data, aad)


def decrypt(blob: bytes, aad: bytes) -> bytes:
    if not blob.startswith(MAGIC):
        raise StorageError("This file is not in the encrypted format.")
    nonce, body = blob[len(MAGIC):len(MAGIC) + NONCE_BYTES], blob[len(MAGIC) + NONCE_BYTES:]
    try:
        return AESGCM(_key()).decrypt(nonce, body, aad)
    except InvalidTag as exc:
        raise StorageError("The file could not be decrypted: wrong key, or the file was changed or moved.") from exc


def is_encrypted(blob: bytes) -> bool:
    return blob.startswith(MAGIC)


# Keep only letters, digits and . _ - so a file name can never contain path tricks like ../../ or odd characters.
def _safe_name(filename: str) -> str:
    name = "".join(c for c in filename if c.isalnum() or c in "._-")
    return name or "file"


# Store an uploaded file. Returns where it was stored and its SHA-256 fingerprint (of the original bytes).
def save(case_id: int, filename: str, data: bytes) -> tuple[str, str]:
    """Encrypt `data` and write it under the case's evidence folder. Returns (stored_path, sha256 of the original bytes)."""
    # The fingerprint of the file contents, used in the file name: the same bytes always get the same name.
    sha256 = hashlib.sha256(data).hexdigest()
    # One folder per case, so evidence from different applications never mixes.
    folder = Path(config.EVIDENCE_DIR) / str(case_id)
    folder.mkdir(parents=True, exist_ok=True)
    stored_path = folder / f"{sha256}_{_safe_name(filename)}"
    blob = encrypt(data, _aad_for(stored_path))           # fails before anything is written when the key is missing
    tmp = stored_path.with_name(stored_path.name + ".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, stored_path)                          # never leaves a half-written file behind
    return str(stored_path), sha256


# Read a stored file back, given the path saved in the case_document table. Returns the original bytes.
# A file still in the old unencrypted form (stored before encryption existed) is returned as it is, until
# `python -m promoflow.secure_files encrypt` has converted it.
def read(stored_path: str) -> bytes:
    path = Path(stored_path)
    blob = path.read_bytes()
    if not is_encrypted(blob):
        return blob
    return decrypt(blob, _aad_for(path))
