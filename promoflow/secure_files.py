"""Encrypt the evidence files that were stored before encryption existed, and check that every file is protected.

    python -m promoflow.secure_files verify            list files that are not encrypted or cannot be decrypted
    python -m promoflow.secure_files encrypt --dry-run show what would be converted
    python -m promoflow.secure_files encrypt           convert every plain file in place (checked by reading it back)

Safe to run again: files that are already encrypted are skipped. Needs DOCUMENT_ENCRYPTION_KEY."""
import hashlib
import os
import sys
from pathlib import Path

from promoflow import config, storage


def _files() -> list[Path]:
    root = Path(config.EVIDENCE_DIR)
    return sorted(p for p in root.rglob("*") if p.is_file() and not p.name.endswith(".tmp")) if root.exists() else []


def verify() -> int:
    plain, broken, ok = [], [], 0
    for p in _files():
        blob = p.read_bytes()
        if not storage.is_encrypted(blob):
            plain.append(p)
            continue
        try:
            data = storage.decrypt(blob, storage._aad_for(p))
            if hashlib.sha256(data).hexdigest() != p.name.split("_", 1)[0]:
                broken.append((p, "content does not match its fingerprint"))
            else:
                ok += 1
        except storage.StorageError as exc:
            broken.append((p, str(exc)))
    print(f"{ok} encrypted and intact; {len(plain)} NOT encrypted; {len(broken)} broken")
    for p in plain:
        print("  plain  ", p)
    for p, why in broken:
        print("  broken ", p, "-", why)
    return 1 if plain or broken else 0


def encrypt_all(dry_run: bool) -> int:
    done = skipped = 0
    for p in _files():
        blob = p.read_bytes()
        if storage.is_encrypted(blob):
            skipped += 1
            continue
        if dry_run:
            print("would encrypt", p)
            done += 1
            continue
        enc = storage.encrypt(blob, storage._aad_for(p))
        if storage.decrypt(enc, storage._aad_for(p)) != blob:          # read it back before replacing the original
            print("round-trip check FAILED, left unchanged:", p)
            return 1
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_bytes(enc)
        os.replace(tmp, p)
        done += 1
    print(f"{'would encrypt' if dry_run else 'encrypted'} {done} file(s); {skipped} already encrypted")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    sys.exit(verify() if cmd == "verify" else encrypt_all("--dry-run" in sys.argv) if cmd == "encrypt" else print(__doc__) or 2)
