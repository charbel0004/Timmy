"""Illustrative read-only local prompt registry loader (stdlib only).

NOT a tool-execution or authorization layer. CN must bind trusted nodes and verify
source/ref scopes separately. Keep runtime pinned to reviewed Git version.
"""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]

def _safe_read(rel_path: str) -> str:
    if not isinstance(rel_path, str) or rel_path.startswith(("/", "\\")) or ".." in Path(rel_path).parts:
        raise ValueError("Invalid prompt registry path")
    root = ROOT.resolve()
    full = (root / rel_path).resolve()
    if not full.is_relative_to(root) or not full.is_file():
        raise ValueError("Prompt path escapes registry or is missing")
    return full.read_text(encoding="utf-8")

def load_action_prompt(action_id: str) -> dict:
    if not re.fullmatch(r"ACT-(0[0-9]|1[0-6])", action_id):
        raise ValueError("Unregistered action ID")
    registry = json.loads(_safe_read("manifest.json"))
    row = next((a for a in registry["actions"] if a["action_id"] == action_id), None)
    if row is None or row["prompt_access"] != "READ_ONLY":
        raise ValueError("Action not registered")
    shared = ["system/MAIN_SYSTEM.md", "shared/REQUEST_LIFECYCLE.md",
              "shared/DATA_SECURITY_AND_PROMPT_INJECTION.md",
              "shared/IDENTITY_ALIASES.md",
              "shared/SOURCE_AUTHORITIES_AND_GATES.md",
              "shared/AUDIT_ISSUES_REPORTS.md"]
    selected_paths = shared + [row["prompt_path"]]
    payloads = {p: _safe_read(p) for p in selected_paths}
    # Recommended additional deployment control: pin approved prompt SHA/release version.
    return {"action_id": action_id, "prompts": payloads,
            "digests": {p: hashlib.sha256(t.encode("utf-8")).hexdigest() for p, t in payloads.items()},
            "allowed_read_capabilities": row["allowed_read_capabilities"]}
