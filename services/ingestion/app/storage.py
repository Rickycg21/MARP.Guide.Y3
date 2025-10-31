import os, pathlib, shutil
from typing import Tuple

STORAGE_DIR = os.getenv("STORAGE_DIR", "/data/pdfs")

pathlib.Path(STORAGE_DIR).mkdir(parents=True, exist_ok=True)

def save_bytes(doc_id: str, filename: str, content: bytes) -> Tuple[str, int]:
    safe = filename.replace("/", "_")
    path = os.path.join(STORAGE_DIR, f"{doc_id}-{safe}")
    with open(path, "wb") as f:
        f.write(content)
    return path, os.path.getsize(path)
