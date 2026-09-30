"""Rolling content digest over a corpus."""
import hashlib
import os


def rolling_digest(root: str, files: list[str]) -> str:
    h = hashlib.sha256()
    for rel in files:
        h.update(rel.encode())
        with open(os.path.join(root, rel), "rb") as f:
            h.update(f.read())
    return h.hexdigest()
