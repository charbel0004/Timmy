"""Pinned, read-only loader for the approved action pack."""
from .observability import reference
import json
from functools import lru_cache
from hashlib import sha256
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
PACK = "backend/app/ai/instructions/"
DIGEST = "c1e5edd8a3f4609a1935cf43c8ce7bbcebe5e07d9f990d30ccc1d09bc80187e0"


@lru_cache(maxsize=1)
def _verified():
    raw = (ROOT / PACK / "contracts/FILE_DIGESTS.json").read_bytes()
    if sha256(raw).hexdigest() != DIGEST:
        raise ValueError("Instruction manifest integrity failure")
    files = {}
    for name, digest in json.loads(raw)["files"].items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Invalid instruction path")
        resolved = (ROOT / name).resolve()
        if not resolved.is_relative_to(ROOT):
            raise ValueError("Instruction path outside repository")
        value = resolved.read_bytes()
        if sha256(value).hexdigest() != digest:
            raise ValueError(f"Instruction integrity failure: {name}")
        files[name] = value.decode("utf-8")
    return files


def action_instructions(action_id: str) -> str:
    files = _verified()
    manifest = json.loads(files[PACK + "manifest.json"])
    entries = {item["action_id"]: item["prompt_path"] for item in manifest["actions"]}
    if action_id not in entries:
        raise ValueError("Unknown action ID")
    paths = [entries[action_id] if item == "actions/<selected-action>.md" else item
             for item in manifest["load_order"]]
    for path in paths:
        reference(path, 'retrieved', DIGEST)
    return "\n\n".join(files[PACK + path] for path in paths)
