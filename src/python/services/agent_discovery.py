"""Real-time agent discovery via NATS — live agent status for the dashboard."""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("agnetic-discovery")

NATS_URL = os.getenv("NATS_URL", "nats://127.0.0.1:4222")

_agent_cache: dict[str, dict] = {}
_cache_timestamps: dict[str, float] = {}
_CACHE_TTL = 15


def _now():
    return time.time()


async def discover_agents() -> list[dict]:
    """Query NATS for all known agents and their status."""
    global _agent_cache, _cache_timestamps

    if _agent_cache and all(
        _now() - _cache_timestamps.get(name, 0) < _CACHE_TTL
        for name in _agent_cache
    ):
        return list(_agent_cache.values())

    try:
        from nats import connect as nats_connect

        nc = await nats_connect(NATS_URL)

        status_agents = {}
        subjects_map = {
            "agnetic.agent.agnetic-core.status": "agnetic-core",
            "agnetic.agent.agnetic-coder.status": "agnetic-coder",
            "agnetic.agent.agnetic-secops.status": "agnetic-secops",
            "agnetic.agent.agnetic-data.status": "agnetic-data",
        }

        for subject, name in subjects_map.items():
            try:
                msg = await nc.request(subject, b'{"command": "ping"}', timeout=2)
                data = json.loads(msg.data.decode())
                agent_info = {
                    "name": name,
                    "status": data.get("status", "unknown"),
                    "model": data.get("model", "unknown"),
                    "last_active": data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    "uptime": data.get("uptime", 0),
                    "capabilities": data.get("capabilities", []),
                    "version": data.get("version", "2.1.0"),
                    "skills": data.get("skills", []),
                    "config": data.get("config", {}),
                }
                status_agents[name] = agent_info
            except Exception:
                cached = _agent_cache.get(name)
                if cached and _now() - _cache_timestamps.get(name, 0) < 60:
                    status_agents[name] = {**cached, "status": "unknown"}
                else:
                    status_agents[name] = {
                        "name": name,
                        "status": "offline",
                        "model": "unknown",
                        "last_active": datetime.now(timezone.utc).isoformat(),
                        "uptime": 0,
                        "capabilities": [],
                        "version": "2.1.0",
                        "skills": [],
                        "config": {},
                    }

        await nc.close()

        _agent_cache = status_agents
        for name in status_agents:
            _cache_timestamps[name] = _now()

        return list(status_agents.values())

    except ImportError:
        log.warning("nats-py not available, using cache")
        return list(_agent_cache.values()) if _agent_cache else []
    except Exception as e:
        log.warning("NATS discovery failed: %s", e)
        return list(_agent_cache.values()) if _agent_cache else []


async def get_agent(name: str) -> Optional[dict]:
    agents = await discover_agents()
    for a in agents:
        if a["name"] == name:
            return a
    return None
