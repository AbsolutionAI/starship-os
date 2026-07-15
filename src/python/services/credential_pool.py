import os
import json
import asyncio
import logging
import random
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("agnetic-credentials")

CREDENTIALS_PATH = Path(os.getenv("CREDENTIALS_FILE", "/opt/agnetic/lib/credentials.json"))
POOL_REFRESH_INTERVAL = int(os.getenv("CREDENTIAL_POOL_REFRESH", "300"))


class CredentialPool:
    def __init__(self, provider: str):
        self.provider = provider
        self.keys: list[dict] = []
        self._index = 0
        self._lock = asyncio.Lock()

    def add_key(self, api_key: str, priority: int = 0, max_usage: int = 0, metadata: dict = None):
        self.keys.append({
            "key": api_key,
            "priority": priority,
            "max_usage": max_usage,
            "usage_count": 0,
            "errors": 0,
            "last_error": None,
            "cooldown_until": 0,
            "metadata": metadata or {},
        })
        self.keys.sort(key=lambda k: k["priority"])

    async def get_key(self) -> Optional[str]:
        async with self._lock:
            now = time.time()
            candidates = [k for k in self.keys
                          if k["cooldown_until"] < now
                          and (k["max_usage"] == 0 or k["usage_count"] < k["max_usage"])]

            if not candidates:
                candidates = [k for k in self.keys
                              if k["cooldown_until"] < now]
                if not candidates:
                    log.warning("No available keys for provider '%s'", self.provider)
                    return None

            candidates.sort(key=lambda k: (k["errors"], k["priority"]))
            key = candidates[self._index % len(candidates)]
            self._index += 1
            key["usage_count"] += 1
            return key["key"]

    async def report_error(self, api_key: str):
        async with self._lock:
            for k in self.keys:
                if k["key"] == api_key:
                    k["errors"] += 1
                    k["last_error"] = time.time()
                    k["cooldown_until"] = time.time() + min(60 * k["errors"], 3600)
                    log.info("Key for '%s' cooled down for %ds (errors: %d)",
                             self.provider, k["errors"] * 60, k["errors"])
                    break

    async def report_success(self, api_key: str):
        async with self._lock:
            for k in self.keys:
                if k["key"] == api_key and k["errors"] > 0:
                    k["errors"] = max(0, k["errors"] - 1)

    def get_status(self) -> dict:
        return {
            "provider": self.provider,
            "total_keys": len(self.keys),
            "available_keys": sum(1 for k in self.keys if k["cooldown_until"] < time.time()),
            "total_usage": sum(k["usage_count"] for k in self.keys),
            "total_errors": sum(k["errors"] for k in self.keys),
        }


class CredentialPoolManager:
    def __init__(self):
        self.pools: dict[str, CredentialPool] = {}
        self._loaded = False

    def load(self):
        if self._loaded:
            return
        if not CREDENTIALS_PATH.exists():
            log.info("No credentials file at %s", CREDENTIALS_PATH)
            return

        try:
            data = json.loads(CREDENTIALS_PATH.read_text())
            for provider, keys_data in data.get("pools", {}).items():
                pool = CredentialPool(provider)
                for entry in keys_data.get("keys", []):
                    pool.add_key(
                        api_key=entry.get("key", ""),
                        priority=entry.get("priority", 0),
                        max_usage=entry.get("max_usage", 0),
                        metadata=entry.get("metadata", {}),
                    )
                self.pools[provider] = pool
                log.info("Loaded %d keys for provider '%s'", len(pool.keys), provider)
            self._loaded = True
        except Exception as e:
            log.warning("Failed to load credentials: %s", e)

    def get_pool(self, provider: str) -> Optional[CredentialPool]:
        return self.pools.get(provider)

    async def get_key(self, provider: str) -> Optional[str]:
        pool = self.get_pool(provider)
        if not pool:
            return None
        return await pool.get_key()

    async def report_error(self, provider: str, key: str):
        pool = self.get_pool(provider)
        if pool:
            await pool.report_error(key)

    async def report_success(self, provider: str, key: str):
        pool = self.get_pool(provider)
        if pool:
            await pool.report_success(key)

    def get_status(self) -> dict:
        return {name: pool.get_status() for name, pool in self.pools.items()}


_credential_manager = CredentialPoolManager()


def get_credential_manager() -> CredentialPoolManager:
    return _credential_manager
