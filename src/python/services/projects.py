import os
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("agnetic-projects")

PROJECTS_DIR = Path(os.getenv("PROJECTS_DIR", "/var/lib/agnetic/projects"))


class Project:
    def __init__(self, name: str, path: Path):
        self.name = name
        self.path = path
        self._manifest: dict = {}

    @property
    def manifest_path(self) -> Path:
        return self.path / "project.json"

    def load(self):
        if self.manifest_path.exists():
            try:
                self._manifest = json.loads(self.manifest_path.read_text())
            except Exception:
                self._manifest = {}
        return self

    def save(self):
        self.path.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(self._manifest, indent=2))

    @property
    def instructions(self) -> str:
        p = self.path / "INSTRUCTIONS.md"
        return p.read_text() if p.exists() else ""

    @instructions.setter
    def instructions(self, content: str):
        (self.path / "INSTRUCTIONS.md").write_text(content)

    @property
    def memory_path(self) -> Path:
        return self.path / "memory"

    @property
    def secrets_path(self) -> Path:
        return self.path / ".secrets.json"

    def get_secret(self, key: str) -> Optional[str]:
        if self.secrets_path.exists():
            try:
                return json.loads(self.secrets_path.read_text()).get(key)
            except Exception:
                pass
        return None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": str(self.path),
            "created": self._manifest.get("created", ""),
            "updated": self._manifest.get("updated", ""),
            "description": self._manifest.get("description", ""),
            "git_repo": self._manifest.get("git_repo", ""),
            "agents": self._manifest.get("agents", []),
            "memory_count": len(list(self.memory_path.glob("*"))) if self.memory_path.exists() else 0,
        }


class ProjectManager:
    def __init__(self):
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[Project]:
        projects = []
        for d in sorted(PROJECTS_DIR.iterdir()):
            if d.is_dir() and (d / "project.json").exists():
                try:
                    p = Project(d.name, d).load()
                    projects.append(p)
                except Exception as e:
                    log.warning("Failed to load project '%s': %s", d.name, e)
        return projects

    def get(self, name: str) -> Optional[Project]:
        path = PROJECTS_DIR / name
        if path.exists() and (path / "project.json").exists():
            return Project(name, path).load()
        return None

    def create(self, name: str, description: str = "", git_repo: str = "") -> Project:
        path = PROJECTS_DIR / name
        path.mkdir(parents=True, exist_ok=True)
        p = Project(name, path)
        p._manifest = {
            "name": name,
            "description": description,
            "git_repo": git_repo,
            "created": datetime.now(timezone.utc).isoformat(),
            "updated": datetime.now(timezone.utc).isoformat(),
            "agents": [],
        }
        p.save()
        (p.path / "memory").mkdir(exist_ok=True)
        log.info("Created project: %s", name)
        return p

    def delete(self, name: str) -> dict:
        path = PROJECTS_DIR / name
        if not path.exists():
            return {"error": True, "message": f"Project '{name}' not found"}
        import shutil
        shutil.rmtree(path)
        log.info("Deleted project: %s", name)
        return {"status": "deleted", "name": name}


_project_manager = ProjectManager()


def get_project_manager() -> ProjectManager:
    return _project_manager
