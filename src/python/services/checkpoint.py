import os
import json
import shutil
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("agnetic-checkpoint")

CHECKPOINT_DIR = Path(os.getenv("CHECKPOINT_DIR", "/var/lib/agnetic/checkpoints"))
MAX_CHECKPOINTS = int(os.getenv("MAX_CHECKPOINTS", "50"))
AUTO_CHECKPOINT_BEFORE_WRITE = os.getenv("AUTO_CHECKPOINT", "true").lower() == "true"


class CheckpointManager:
    def __init__(self):
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    def _snapshot_path(self, checkpoint_id: str) -> Path:
        return CHECKPOINT_DIR / checkpoint_id

    def create(self, label: str = "", paths: list = None) -> dict:
        paths = paths or ["/opt/agnetic", "/root"]
        cid = datetime.now().strftime("cp-%Y%m%d-%H%M%S-%f")[:24]
        snap_dir = self._snapshot_path(cid)
        snap_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "id": cid,
            "label": label,
            "created": datetime.now(timezone.utc).isoformat(),
            "paths": [],
            "file_hashes": {},
        }

        for base_path in paths:
            p = Path(base_path)
            if not p.exists():
                continue
            rel_path = p.name
            dest = snap_dir / rel_path
            if p.is_file():
                shutil.copy2(p, dest)
                manifest["paths"].append(str(p))
                manifest["file_hashes"][str(p)] = self._hash_file(dest)
            elif p.is_dir():
                shutil.copytree(p, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', 'node_modules', '.git', '.cache'))
                for f in dest.rglob("*"):
                    if f.is_file():
                        orig = str(f.relative_to(dest))
                        manifest["paths"].append(f"/{rel_path}/{orig}")
                        manifest["file_hashes"][f"/{rel_path}/{orig}"] = self._hash_file(f)

        (snap_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        self._prune_old()
        log.info("Checkpoint created: %s (%s)", cid, label or "no label")
        return {"id": cid, "label": label, "files": len(manifest["paths"]), "created": manifest["created"]}

    def list(self) -> list:
        if not CHECKPOINT_DIR.exists():
            return []
        checkpoints = []
        for d in sorted(CHECKPOINT_DIR.iterdir(), reverse=True):
            manifest_path = d / "manifest.json"
            if manifest_path.exists():
                try:
                    m = json.loads(manifest_path.read_text())
                    checkpoints.append({
                        "id": m.get("id", d.name),
                        "label": m.get("label", ""),
                        "created": m.get("created", ""),
                        "files": len(m.get("paths", [])),
                    })
                except Exception:
                    checkpoints.append({"id": d.name, "label": "", "created": "", "files": 0})
        return checkpoints

    def restore(self, checkpoint_id: str, paths: list = None) -> dict:
        snap_dir = self._snapshot_path(checkpoint_id)
        manifest_path = snap_dir / "manifest.json"
        if not manifest_path.exists():
            return {"error": True, "message": f"Checkpoint '{checkpoint_id}' not found"}

        manifest = json.loads(manifest_path.read_text())
        restored = []
        failed = []

        for rel_path in manifest.get("paths", []):
            src = snap_dir / rel_path.lstrip("/")
            if not src.exists():
                failed.append(rel_path)
                continue
            dest = Path("/") / rel_path
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if src.is_file():
                    shutil.copy2(src, dest)
                    restored.append(rel_path)
                elif src.is_dir():
                    shutil.copytree(src, dest, dirs_exist_ok=True)
                    restored.append(rel_path)
            except Exception as e:
                failed.append(rel_path)
                log.warning("Restore failed for %s: %s", rel_path, e)

        log.info("Checkpoint restored: %s (%d ok, %d failed)", checkpoint_id, len(restored), len(failed))
        return {
            "id": checkpoint_id,
            "restored": restored,
            "failed": failed,
            "total": len(manifest.get("paths", [])),
        }

    def diff(self, checkpoint_id: str) -> dict:
        snap_dir = self._snapshot_path(checkpoint_id)
        manifest_path = snap_dir / "manifest.json"
        if not manifest_path.exists():
            return {"error": True, "message": f"Checkpoint '{checkpoint_id}' not found"}

        manifest = json.loads(manifest_path.read_text())
        changes = {"added": [], "modified": [], "deleted": [], "unchanged": []}

        for rel_path in manifest.get("paths", []):
            current = Path("/") / rel_path
            snapshot_file = snap_dir / rel_path.lstrip("/")

            if not current.exists():
                changes["deleted"].append(rel_path)
            elif not snapshot_file.exists():
                changes["added"].append(rel_path)
            else:
                cur_hash = self._hash_file(current) if current.is_file() else ""
                snap_hash = manifest.get("file_hashes", {}).get(rel_path, "")
                if cur_hash != snap_hash:
                    changes["modified"].append(rel_path)
                else:
                    changes["unchanged"].append(rel_path)

        return {"id": checkpoint_id, "changes": changes}

    def delete(self, checkpoint_id: str) -> dict:
        snap_dir = self._snapshot_path(checkpoint_id)
        if not snap_dir.exists():
            return {"error": True, "message": f"Checkpoint '{checkpoint_id}' not found"}
        shutil.rmtree(snap_dir)
        return {"id": checkpoint_id, "status": "deleted"}

    def auto_checkpoint_before_write(self, path: str) -> Optional[str]:
        if not AUTO_CHECKPOINT_BEFORE_WRITE:
            return None
        p = Path(path)
        if p.exists():
            cp = self.create(label=f"auto before write: {path}", paths=[str(p.parent)])
            return cp.get("id")
        return None

    def _hash_file(self, path: Path) -> str:
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        except Exception:
            return ""

    def _prune_old(self):
        all_cps = sorted(CHECKPOINT_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
        while len(all_cps) > MAX_CHECKPOINTS:
            old = all_cps.pop()
            try:
                shutil.rmtree(old)
                log.info("Pruned old checkpoint: %s", old.name)
            except Exception as e:
                log.warning("Failed to prune %s: %s", old.name, e)


_checkpoint = CheckpointManager()


def get_checkpoint_manager() -> CheckpointManager:
    return _checkpoint
