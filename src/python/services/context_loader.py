import os
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("agnetic-context")

CONTEXT_FILE_NAMES = [
    ".hermes.md",
    "AGENTS.md",
    "CLAUDE.md",
    "SOUL.md",
    ".cursorrules",
    ".claude.md",
    "CONTEXT.md",
    "README.md",
]


def discover_context_files(paths: list = None) -> list:
    paths = paths or [os.getcwd(), "/root", "/opt/agnetic"]
    found = []
    seen = set()

    for base in paths:
        p = Path(base).expanduser().resolve()
        if not p.exists():
            continue

        for name in CONTEXT_FILE_NAMES:
            candidate = p / name
            if candidate.exists() and candidate.is_file():
                key = str(candidate.resolve())
                if key not in seen:
                    seen.add(key)
                    found.append(key)

        for sub in p.iterdir():
            if sub.is_dir() and not sub.name.startswith("."):
                for name in CONTEXT_FILE_NAMES:
                    candidate = sub / name
                    if candidate.exists() and candidate.is_file():
                        key = str(candidate.resolve())
                        if key not in seen:
                            seen.add(key)
                            found.append(key)

    return found


def load_context(label: str = "") -> str:
    files = discover_context_files()
    if not files:
        return ""

    parts = []
    parts.append(f"## Discovered Context Files\n")

    for fpath in files:
        try:
            content = Path(fpath).read_text(errors="replace").strip()
            if content:
                rel = Path(fpath).name
                parts.append(f"### {rel} ({fpath})")
                parts.append(f"```\n{content[:2000]}\n```")
                if len(content) > 2000:
                    parts.append(f"*[truncated, {len(content)} total chars]*")
        except Exception as e:
            log.warning("Failed to read context file %s: %s", fpath, e)

    return "\n\n".join(parts)


def find_project_root(path: str = None) -> Optional[str]:
    path = path or os.getcwd()
    p = Path(path).resolve()
    for parent in [p] + list(p.parents):
        for marker in [".git", ".hermes.md", "AGENTS.md", "package.json", "pyproject.toml", "go.mod"]:
            if (parent / marker).exists():
                return str(parent)
    return None
