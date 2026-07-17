#!/usr/bin/env python3
"""
Starship OS Agent Health Checker — persistent service.

Checks every agent's:
  - Process liveness (pgrep)
  - Ollama model availability (via Ollama API)
  - OpenRouter fallback reachability (if configured)

Auto-recovery:
  - Restarts down agents
  - Pulls missing models from Ollama
  - Logs all incidents to syslog + status file

Install:
  scripts/install-systemd.sh  # registers starship-health-checker.service
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "30"))
STATUS_FILE = Path(os.getenv("HEALTH_STATUS_FILE", "/tmp/starship-health.json"))
AGENTS_DIR = PROJECT_DIR / "agents"
START_AGENTS_SCRIPT = PROJECT_DIR / "scripts" / "start-agents.sh"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s agent-health-checker %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("agent-health")


def load_agent_configs():
    configs = {}
    try:
        import yaml
    except ImportError:
        log.warning("PyYAML not installed")
        return configs

    if not AGENTS_DIR.is_dir():
        log.warning("Agents dir %s not found", AGENTS_DIR)
        return configs

    for yaml_file in sorted(AGENTS_DIR.glob("*.yaml")):
        if yaml_file.name in ("config.yaml", "fleet.yaml", "profile.yaml", "profiles.yaml"):
            continue
        try:
            data = yaml.safe_load(yaml_file.read_text()) or {}
            if "agent" in data and isinstance(data["agent"], dict):
                meta = data["agent"]
                name = meta.get("name", yaml_file.stem)
            else:
                meta = data
                name = data.get("name", yaml_file.stem)
            if not name or name in configs:
                continue
            configs[name] = {
                "name": name,
                "model": meta.get("model", "unknown"),
                "provider": meta.get("provider", "ollama"),
                "role": meta.get("role", ""),
                "file": yaml_file.name,
            }
            # Extract nested model info
            models_block = meta.get("models", meta.get("model", {}))
            if isinstance(models_block, dict):
                configs[name]["models_default"] = models_block.get("default", meta.get("model", ""))
                configs[name]["models_available"] = models_block.get("available", [])
                configs[name]["openrouter_models"] = list(
                    models_block.get("providers", {}).get("openrouter", [])
                )
            else:
                configs[name]["models_default"] = meta.get("model", "")
                configs[name]["models_available"] = [meta.get("model", "")]
                configs[name]["openrouter_models"] = []
        except Exception as e:
            log.warning("Failed to load %s: %s", yaml_file, e)
    return configs


async def check_ollama_alive():
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{OLLAMA_URL}/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    return True, models
    except Exception as e:
        log.warning("Ollama unreachable: %s", e)
    return False, []


def check_agent_process(name):
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"agent_daemon.py {name}"],
            capture_output=True, timeout=2,
        )
        return result.returncode == 0
    except Exception:
        return False


async def check_openrouter_connectivity():
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{OPENROUTER_URL.rstrip('/chat/completions')}/models",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                return resp.status == 200
    except Exception:
        return False


async def try_restart_agent(name):
    log.warning("Attempting restart of agent: %s", name)
    try:
        subprocess.run(
            ["pkill", "-f", f"agent_daemon.py {name}"],
            capture_output=True, timeout=3,
        )
    except Exception:
        pass
    await asyncio.sleep(1)
    try:
        subprocess.run(
            ["nohup", "python3", str(PROJECT_DIR / "agents" / "agent_daemon.py"), name, "&"],
            capture_output=True, timeout=3,
        )
    except Exception as e:
        log.error("Failed to restart agent %s: %s", name, e)
        return False
    await asyncio.sleep(2)
    still_down = not check_agent_process(name)
    if still_down:
        log.error("Agent %s failed to start after restart attempt", name)
        return False
    log.info("Agent %s restarted successfully", name)
    return True


async def try_pull_model(model_name):
    log.warning("Attempting to pull missing model: %s", model_name)
    try:
        proc = await asyncio.create_subprocess_exec(
            "ollama", "pull", model_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=120)
        if proc.returncode == 0:
            log.info("Successfully pulled model: %s", model_name)
            return True
        log.error("ollama pull %s failed with code %d", model_name, proc.returncode)
    except asyncio.TimeoutError:
        log.error("Timeout pulling model: %s", model_name)
        try:
            proc.terminate()
        except Exception:
            pass
    except Exception as e:
        log.error("Failed to pull model %s: %s", model_name, e)
    return False


async def check_once():
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ollama_alive": False,
        "ollama_models": [],
        "agents": {},
        "incidents": [],
        "auto_recovery": {"restarts": 0, "pulls": 0},
    }

    # 1. Ollama status
    ollama_ok, ollama_models = await check_ollama_alive()
    results["ollama_alive"] = ollama_ok
    results["ollama_models"] = ollama_models

    if not ollama_ok:
        results["incidents"].append({
            "id": "ollama-down",
            "severity": "critical",
            "title": "Ollama service unreachable",
            "summary": "Cannot connect to Ollama LLM server for model queries",
            "source": "model",
        })
        # Can't check models if Ollama is down
        results["agents"] = {name: {"status": "unknown", "model_available": False, "error": "ollama_unreachable"}
                             for name in load_agent_configs()}
        return results

    configs = load_agent_configs()
    if not configs:
        results["agents"]["_error"] = {"status": "no_agent_configs"}
        return results

    openrouter_ok = await check_openrouter_connectivity()

    for name, cfg in configs.items():
        agent_info = {"status": "ok", "model_available": True, "incidents": []}
        agent_info["provider"] = cfg.get("provider", "ollama")

        # Process check
        running = check_agent_process(name)
        agent_info["running"] = running
        if not running:
            agent_info["status"] = "down"
            agent_info["incidents"].append({
                "id": f"agent-down-{name}",
                "severity": "high",
                "title": f"Agent offline: {name}",
                "summary": f"{cfg.get('role', name)} agent is not running",
                "source": "agent",
            })
            # Auto-recovery: try to restart
            restarted = await try_restart_agent(name)
            if restarted:
                results["auto_recovery"]["restarts"] += 1
                agent_info["status"] = "recovered"
                agent_info["running"] = True

        # Model check
        primary_model = cfg.get("models_default", cfg.get("model", ""))
        available_models = cfg.get("models_available", [])
        if not available_models:
            available_models = [primary_model] if primary_model else []

        for model in [primary_model] + available_models:
            if not model or model == "unknown":
                continue
            # Normalize model name for comparison
            model_in_list = any(
                model == m or model.split(":")[0] == m.split(":")[0]
                for m in ollama_models
            )
            if not model_in_list:
                agent_info["model_available"] = False
                agent_info["incidents"].append({
                    "id": f"model-missing-{name}-{model.replace('/', '-')}",
                    "severity": "high",
                    "title": f"Model missing for {name}: {model}",
                    "summary": f"Agent {name} requires model '{model}' but it is not in Ollama",
                    "source": "model",
                })
                # Auto-recovery: try to pull
                pulled = await try_pull_model(model)
                if pulled:
                    results["auto_recovery"]["pulls"] += 1
                    agent_info["model_available"] = True
                break  # One missing model is enough per agent

        # OpenRouter check
        openrouter_models = cfg.get("openrouter_models", [])
        if openrouter_models:
            agent_info["openrouter_reachable"] = openrouter_ok
            if not openrouter_ok:
                agent_info["incidents"].append({
                    "id": f"openrouter-down-{name}",
                    "severity": "warn",
                    "title": f"OpenRouter fallback unreachable for {name}",
                    "summary": f"Agent {name} has OpenRouter models configured but the API is unreachable",
                    "source": "model",
                })

        results["agents"][name] = agent_info
        for inc in agent_info["incidents"]:
            results["incidents"].append(inc)

    results["total_agents"] = len(configs)
    results["agents_running"] = sum(1 for a in results["agents"].values() if isinstance(a, dict) and a.get("running"))
    results["total_incidents"] = len(results["incidents"])

    return results


async def main_loop():
    log.info("Agent Health Checker started (interval=%ds)", CHECK_INTERVAL)
    while True:
        try:
            results = await check_once()
            STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATUS_FILE.write_text(json.dumps(results, indent=2))

            # Log summary
            n_incidents = results["total_incidents"]
            n_agents = results["total_agents"]
            n_running = results["agents_running"]
            auto_recovery = results["auto_recovery"]
            log.info(
                "Health: %d/%d agents running, %d incidents, %d restarts, %d model pulls",
                n_running, n_agents, n_incidents,
                auto_recovery["restarts"], auto_recovery["pulls"],
            )
            if n_incidents > 0:
                for inc in results["incidents"]:
                    log.warning("INCIDENT [%s] %s: %s", inc["severity"], inc["title"], inc["summary"])

        except Exception as e:
            log.error("Health check error: %s", e, exc_info=True)

        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    if "--once" in sys.argv:
        asyncio.run(check_once())
    else:
        asyncio.run(main_loop())
