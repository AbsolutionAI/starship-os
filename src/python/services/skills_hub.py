import os
import json
import asyncio
import logging
import tempfile
import shutil
import subprocess
import re
import yaml
from pathlib import Path
from typing import Optional

log = logging.getLogger("agnetic-skills-hub")

SKILLS_DIR = Path(os.getenv("SKILLS_DIR", "/opt/agnetic/skills"))
SKILLS_HUB_CACHE = Path(os.getenv("SKILLS_HUB_CACHE", "/tmp/agnetic-skills-hub"))
SKILLS_REGISTRY = Path(os.getenv("SKILLS_REGISTRY", "/opt/agnetic/lib/skills_registry.json"))

GITHUB_RAW = "https://raw.githubusercontent.com"
GITHUB_API = "https://api.github.com"

SANDBOX_TIMEOUT = int(os.getenv("SKILL_SANDBOX_TIMEOUT", "15"))


async def search_skills_hub(query: str = "", source: str = "all", limit: int = 30) -> list:
    results = []

    cache_file = SKILLS_HUB_CACHE / "skills_cache.json"
    if cache_file.exists():
        try:
            all_skills = json.loads(cache_file.read_text())
        except Exception:
            all_skills = []
    else:
        all_skills = await _fetch_skills_index()
        SKILLS_HUB_CACHE.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(all_skills, indent=2))

    for skill in all_skills:
        if query:
            q = query.lower()
            name = skill.get("name", "")
            desc = skill.get("description", "")
            if q not in name.lower() and q not in desc.lower():
                continue
        if source != "all" and skill.get("source") != source:
            continue
        results.append(skill)
        if len(results) >= limit:
            break

    installed_ids = _get_installed_ids()
    for s in results:
        s["installed"] = s["id"] in installed_ids

    return results


async def _fetch_skills_index() -> list:
    skills = []

    known_sources = [
        {"owner": "anthropics", "repo": "skills", "label": "anthropic"},
        {"owner": "vercel-labs", "repo": "agent-skills", "label": "vercel"},
        {"owner": "vercel-labs", "repo": "skills", "label": "vercel"},
        {"owner": "mattpocock", "repo": "skills", "label": "community"},
        {"owner": "microsoft", "repo": "azure-skills", "label": "microsoft"},
        {"owner": "firebase", "repo": "agent-skills", "label": "firebase"},
        {"owner": "supabase", "repo": "agent-skills", "label": "supabase"},
        {"owner": "sentry-devtools", "repo": "skills", "label": "sentry"},
        {"owner": "obra", "repo": "superpowers", "label": "community"},
        {"owner": "scrapegraphai", "repo": "just-scrape", "label": "community"},
        {"owner": "shadcn", "repo": "ui", "label": "shadcn"},
        {"owner": "nextlevelbuilder", "repo": "ui-ux-pro-max-skill", "label": "community"},
        {"owner": "leonxlnx", "repo": "taste-skill", "label": "community"},
        {"owner": "coreyhaines31", "repo": "marketingskills", "label": "community"},
        {"owner": "heygen-com", "repo": "hyperframes", "label": "heygen"},
        {"owner": "101-skills", "repo": "skills", "label": "community"},
        {"owner": "firecracker", "repo": "cli", "label": "firecracker"},
        {"owner": "browser-act", "repo": "skills", "label": "community"},
        {"owner": "pbakaus", "repo": "impeccable", "label": "community"},
        {"owner": "lllllllama", "repo": "rigorpilot-skills", "label": "community"},
        {"owner": "arvindrk", "repo": "extract-design-system", "label": "community"},
        {"owner": "roin-orca", "repo": "skills", "label": "community"},
        {"owner": "remotion-dev", "repo": "skills", "label": "remotion"},
        {"owner": "emilkowalski", "repo": "skills", "label": "community"},
    ]

    for src in known_sources:
        try:
            skill_names = await _list_repo_skills(src["owner"], src["repo"])
            for name in skill_names:
                skill_id = f"{src['owner']}/{src['repo']}/{name}"
                skills.append({
                    "id": skill_id,
                    "name": name,
                    "source": src["label"],
                    "owner": src["owner"],
                    "repo": src["repo"],
                    "url": f"https://github.com/{src['owner']}/{src['repo']}/tree/main/{name}",
                })
        except Exception as e:
            log.debug("Failed to index %s/%s: %s", src["owner"], src["repo"], e)

    skills.sort(key=lambda s: s["id"])
    return skills


async def _list_repo_skills(owner: str, repo: str) -> list:
    import httpx
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"Accept": "application/vnd.github.v3+json"})
            if resp.status_code != 200:
                return []
            contents = resp.json()
            skills = []
            for item in contents:
                if item.get("type") == "dir":
                    name = item.get("name", "")
                    if re.match(r'^[a-z][a-z0-9-]*$', name) and len(name) <= 64:
                        skills.append(name)
            return skills
    except Exception as e:
        log.debug("Failed to list %s/%s: %s", owner, repo, e)
        return []


async def preview_skill(skill_id: str) -> dict:
    parts = skill_id.split("/", 2)
    if len(parts) != 3:
        return {"error": True, "message": "Invalid skill ID format. Expected: owner/repo/skill-name"}
    owner, repo, skill_name = parts

    raw_url = f"{GITHUB_RAW}/{owner}/{repo}/main/{skill_name}/SKILL.md"
    fallback_branches = ["master"]

    import httpx
    content = None

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(raw_url)
        if resp.status_code == 200:
            content = resp.text
        else:
            for branch in fallback_branches:
                fb_url = f"{GITHUB_RAW}/{owner}/{repo}/{branch}/{skill_name}/SKILL.md"
                resp = await client.get(fb_url)
                if resp.status_code == 200:
                    content = resp.text
                    break

    if not content:
        return {"error": True, "message": f"SKILL.md not found for '{skill_id}'"}

    frontmatter, body = _parse_frontmatter(content)

    scripts = await _list_skill_files(owner, repo, skill_name, "scripts")
    references = await _list_skill_files(owner, repo, skill_name, "references")

    return {
        "id": skill_id,
        "name": frontmatter.get("name", skill_name),
        "description": frontmatter.get("description", ""),
        "version": frontmatter.get("version", "?"),
        "license": frontmatter.get("license", ""),
        "compatibility": frontmatter.get("compatibility", ""),
        "tags": frontmatter.get("tags", []),
        "allowed_tools": frontmatter.get("allowed-tools", ""),
        "body_preview": body[:2000],
        "body_length": len(body),
        "scripts": scripts,
        "references": references,
        "url": f"https://github.com/{owner}/{repo}/tree/main/{skill_name}",
    }


async def _list_skill_files(owner: str, repo: str, skill_name: str, subdir: str) -> list:
    import httpx
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{skill_name}/{subdir}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers={"Accept": "application/vnd.github.v3+json"})
            if resp.status_code == 200:
                return [item.get("name") for item in resp.json() if item.get("type") == "file"]
    except Exception:
        pass
    return []


def _parse_frontmatter(content: str) -> tuple:
    match = re.match(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
    if match:
        try:
            frontmatter = yaml.safe_load(match.group(1)) or {}
        except Exception:
            frontmatter = {}
        body = match.group(2).strip()
    else:
        frontmatter = {}
        body = content.strip()
    return frontmatter, body


async def test_skill_sandboxed(skill_id: str) -> dict:
    parts = skill_id.split("/", 2)
    if len(parts) != 3:
        return {"error": True, "message": "Invalid skill ID"}
    owner, repo, skill_name = parts

    with tempfile.TemporaryDirectory(prefix="agnetic-skill-test-") as tmpdir:
        tmp_path = Path(tmpdir)

        content = await preview_skill(skill_id)
        if content.get("error"):
            return content

        skill_dir = tmp_path / skill_name
        skill_dir.mkdir(parents=True)

        raw_url = f"{GITHUB_RAW}/{owner}/{repo}/main/{skill_name}/SKILL.md"
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(raw_url)
            if resp.status_code == 200:
                (skill_dir / "SKILL.md").write_text(resp.text)

        checks = {
            "valid_yaml": False,
            "has_name": False,
            "has_description": False,
            "name_valid": False,
            "description_length_ok": False,
            "body_size_ok": False,
            "no_dangerous_patterns": False,
            "allowed_tools_check": False,
            "network_access": False,
            "filesystem_access": False,
            "scripts_inspection": "none",
        }

        frontmatter, body = _parse_frontmatter(resp.text if resp.status_code == 200 else "")

        if frontmatter:
            checks["valid_yaml"] = True
            checks["has_name"] = bool(frontmatter.get("name"))
            checks["has_description"] = bool(frontmatter.get("description"))
            name = frontmatter.get("name", "")
            checks["name_valid"] = bool(re.match(r'^[a-z][a-z0-9-]*$', name)) and len(name) <= 64
            desc = frontmatter.get("description", "")
            checks["description_length_ok"] = len(desc) <= 1024

        checks["body_size_ok"] = len(body) <= 5000

        dangerous = ["rm -rf", "sudo", "chmod 777", ":(){", "mkfs", "dd if=", "shutdown", "reboot"]
        body_lower = body.lower()
        found_dangerous = [p for p in dangerous if p in body_lower]
        checks["no_dangerous_patterns"] = len(found_dangerous) == 0

        allowed = frontmatter.get("allowed-tools", "")
        checks["allowed_tools_check"] = bool(allowed)

        compat = (frontmatter.get("compatibility", "") or "").lower()
        checks["network_access"] = "network" in compat or "internet" in compat
        checks["filesystem_access"] = "filesystem" in compat or "write" in compat

        scripts = await _list_skill_files(owner, repo, skill_name, "scripts")
        if scripts:
            checks["scripts_inspection"] = f"{len(scripts)} scripts found: {', '.join(scripts)}"

        passed = sum(1 for v in checks.values() if v is True)
        total = sum(1 for v in checks.values() if isinstance(v, bool))
        score = round(passed / total * 100, 1) if total > 0 else 0

        if score >= 80:
            level = "safe"
        elif score >= 50:
            level = "warning"
        else:
            level = "dangerous"

        return {
            "skill_id": skill_id,
            "name": frontmatter.get("name", skill_name),
            "score": score,
            "level": level,
            "checks": checks,
            "dangerous_patterns_found": found_dangerous,
            "recommendation": "install" if level == "safe" else ("review" if level == "warning" else "block"),
        }


async def install_skill(skill_id: str, approved: bool = False) -> dict:
    if not approved:
        return {
            "error": True,
            "message": "Skill requires user approval before install. Run test first, then re-install with approved=true",
            "requires_approval": True,
        }

    parts = skill_id.split("/", 2)
    if len(parts) != 3:
        return {"error": True, "message": "Invalid skill ID"}
    owner, repo, skill_name = parts

    dest_dir = SKILLS_DIR / skill_name
    if dest_dir.exists():
        return {"error": True, "message": f"Skill '{skill_name}' already installed at {dest_dir}"}

    test_result = await test_skill_sandboxed(skill_id)
    if test_result.get("error"):
        return test_result

    import httpx
    raw_url = f"{GITHUB_RAW}/{owner}/{repo}/main/{skill_name}/SKILL.md"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(raw_url)
        if resp.status_code != 200:
            return {"error": True, "message": f"Failed to download SKILL.md from {raw_url}"}
        content = resp.text

    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / "SKILL.md").write_text(content)
    (dest_dir / "SOURCE.txt").write_text(f"source: {skill_id}\nurl: https://github.com/{owner}/{repo}/tree/main/{skill_name}\n")

    try:
        scripts = await _list_skill_files(owner, repo, skill_name, "scripts")
        if scripts:
            scripts_dir = dest_dir / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            for script_name in scripts:
                script_url = f"{GITHUB_RAW}/{owner}/{repo}/main/{skill_name}/scripts/{script_name}"
                resp = await client.get(script_url)
                if resp.status_code == 200:
                    (scripts_dir / script_name).write_text(resp.text)
    except Exception as e:
        log.warning("Failed to download scripts for %s: %s", skill_name, e)

    _record_installation(skill_id, skill_name, test_result.get("level", "unknown"))

    from services.event_hooks import emit_event
    try:
        await emit_event("skill.installed", {
            "skill_id": skill_id,
            "name": skill_name,
            "security_level": test_result.get("level", "unknown"),
        })
    except Exception:
        pass

    return {
        "status": "installed",
        "skill_id": skill_id,
        "name": skill_name,
        "path": str(dest_dir),
        "security_level": test_result.get("level", "safe"),
        "test_summary": test_result,
    }


def _get_installed_ids() -> set:
    installed = set()
    registry = {}
    if SKILLS_REGISTRY.exists():
        try:
            registry = json.loads(SKILLS_REGISTRY.read_text())
        except Exception:
            pass
    for sid in registry.get("installed", {}):
        installed.add(sid)
    for d in SKILLS_DIR.iterdir():
        if d.is_dir() and (d / "SKILL.md").exists() and (d / "SOURCE.txt").exists():
            try:
                src = (d / "SOURCE.txt").read_text()
                for line in src.splitlines():
                    if line.startswith("source:"):
                        sid = line.split(":", 1)[1].strip()
                        installed.add(sid)
            except Exception:
                pass
    return installed


def _record_installation(skill_id: str, name: str, security_level: str):
    registry = {"installed": {}}
    if SKILLS_REGISTRY.exists():
        try:
            registry = json.loads(SKILLS_REGISTRY.read_text())
        except Exception:
            pass
    registry.setdefault("installed", {})[skill_id] = {
        "name": name,
        "installed_at": __import__("datetime").datetime.now().isoformat(),
        "security_level": security_level,
    }
    SKILLS_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    SKILLS_REGISTRY.write_text(json.dumps(registry, indent=2))


def list_installed_skills() -> list:
    installed = []
    if SKILLS_REGISTRY.exists():
        try:
            registry = json.loads(SKILLS_REGISTRY.read_text())
            for sid, info in registry.get("installed", {}).items():
                installed.append({"id": sid, **info})
        except Exception:
            pass
    return installed
