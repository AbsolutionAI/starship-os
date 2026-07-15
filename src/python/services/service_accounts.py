import json
import hashlib
import logging
import os
import secrets
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("agnetic-service-accounts")

DEFAULT_DB_PATH = "/var/lib/agnetic/service_accounts.json"


@dataclass
class ServiceAccount:
    id: str
    name: str
    description: str
    roles: list[str] = field(default_factory=list)
    api_key_hash: str = ""
    api_key_prefix: str = ""
    created_at: str = ""
    expires_at: Optional[str] = None
    is_active: bool = True
    allowed_agents: list[str] = field(default_factory=list)
    allowed_toolsets: list[str] = field(default_factory=list)


DEFAULT_ACCOUNTS = [
    ServiceAccount(
        id="",
        name="system-agent",
        description="Full system access for system-level agents",
        roles=["system:*"],
        allowed_agents=["*"],
        allowed_toolsets=["*"],
    ),
    ServiceAccount(
        id="",
        name="security-scanner",
        description="Read-only access and security scanning capabilities",
        roles=["system:read", "security:scan"],
        allowed_agents=["scanner", "auditor"],
        allowed_toolsets=["network", "filesystem"],
    ),
    ServiceAccount(
        id="",
        name="monitoring-agent",
        description="Read-only monitoring and observability access",
        roles=["system:read", "observability:read"],
        allowed_agents=["monitor"],
        allowed_toolsets=["observability"],
    ),
    ServiceAccount(
        id="",
        name="ci-automation",
        description="CI/CD automation with project write and system read access",
        roles=["project:write", "system:read"],
        allowed_agents=["ci-runner"],
        allowed_toolsets=["project", "system"],
    ),
]


class ServiceAccountManager:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._accounts: dict[str, ServiceAccount] = {}
        self._load_or_init()

    def _load_or_init(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r") as f:
                    data = json.load(f)
                for item in data:
                    acct = ServiceAccount(**item)
                    self._accounts[acct.id] = acct
            except (json.JSONDecodeError, IOError) as e:
                logger.error("Failed to load service accounts: %s", e)
                self._accounts = {}
        else:
            logger.info("No service accounts DB found, creating defaults")
            self._init_defaults()

    def _init_defaults(self):
        for acct in DEFAULT_ACCOUNTS:
            raw_key = self._generate_key()
            now = datetime.now(timezone.utc).isoformat()
            acct.id = secrets.token_hex(16)
            acct.api_key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
            acct.api_key_prefix = raw_key[:8]
            acct.created_at = now
            acct.is_active = True
            self._accounts[acct.id] = acct
            logger.info(
                "Created default service account '%s' (id=%s, key_prefix=%s)",
                acct.name, acct.id, acct.api_key_prefix,
            )
        self._persist()

    def _persist(self):
        data = [asdict(acct) for acct in self._accounts.values()]
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with open(self.db_path, "w") as f:
            json.dump(data, f, indent=2)

    def _generate_key(self) -> str:
        return "ag_sa_" + secrets.token_hex(32)

    def create(
        self,
        name: str,
        description: str,
        roles: list[str],
        expires_at: Optional[str] = None,
        allowed_agents: Optional[list[str]] = None,
        allowed_toolsets: Optional[list[str]] = None,
    ) -> tuple[ServiceAccount, str]:
        raw_key = self._generate_key()
        now = datetime.now(timezone.utc).isoformat()
        acct = ServiceAccount(
            id=secrets.token_hex(16),
            name=name,
            description=description,
            roles=roles,
            api_key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
            api_key_prefix=raw_key[:8],
            created_at=now,
            expires_at=expires_at,
            is_active=True,
            allowed_agents=allowed_agents or [],
            allowed_toolsets=allowed_toolsets or [],
        )
        self._accounts[acct.id] = acct
        self._persist()
        logger.info(
            "Created service account '%s' (id=%s, key_prefix=%s)",
            name, acct.id, acct.api_key_prefix,
        )
        return acct, raw_key

    def authenticate(self, api_key: str) -> Optional[ServiceAccount]:
        if not api_key or not api_key.startswith("ag_sa_"):
            logger.warning("Authentication failed: invalid key format")
            return None
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        for acct in self._accounts.values():
            if acct.api_key_hash == key_hash:
                if not acct.is_active:
                    logger.warning(
                        "Authentication failed for '%s' (id=%s): account deactivated",
                        acct.name, acct.id,
                    )
                    return None
                if acct.expires_at:
                    try:
                        exp = datetime.fromisoformat(acct.expires_at)
                        if exp.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                            logger.warning(
                                "Authentication failed for '%s' (id=%s): key expired",
                                acct.name, acct.id,
                            )
                            return None
                    except (ValueError, TypeError):
                        pass
                logger.info(
                    "Authentication succeeded for '%s' (id=%s, key_prefix=%s)",
                    acct.name, acct.id, acct.api_key_prefix,
                )
                return acct
        logger.warning("Authentication failed: unknown key (prefix=%s)", api_key[:12])
        return None

    def get(self, account_id: str) -> Optional[ServiceAccount]:
        return self._accounts.get(account_id)

    def get_by_name(self, name: str) -> Optional[ServiceAccount]:
        for acct in self._accounts.values():
            if acct.name == name:
                return acct
        return None

    def list(self, active_only: bool = True) -> list[ServiceAccount]:
        if active_only:
            return [acct for acct in self._accounts.values() if acct.is_active]
        return list(self._accounts.values())

    def revoke(self, account_id: str) -> bool:
        acct = self._accounts.get(account_id)
        if acct is None:
            logger.warning("Revoke failed: account '%s' not found", account_id)
            return False
        if not acct.is_active:
            logger.info("Account '%s' is already deactivated", account_id)
            return True
        acct.is_active = False
        self._persist()
        logger.info("Revoked service account '%s' (id=%s)", acct.name, acct.id)
        return True

    def rotate_key(self, account_id: str) -> Optional[tuple[ServiceAccount, str]]:
        acct = self._accounts.get(account_id)
        if acct is None:
            logger.warning("Key rotation failed: account '%s' not found", account_id)
            return None
        raw_key = self._generate_key()
        acct.api_key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        acct.api_key_prefix = raw_key[:8]
        self._persist()
        logger.info("Rotated key for service account '%s' (id=%s)", acct.name, acct.id)
        return acct, raw_key

    def delete(self, account_id: str) -> bool:
        acct = self._accounts.pop(account_id, None)
        if acct is None:
            logger.warning("Delete failed: account '%s' not found", account_id)
            return False
        self._persist()
        logger.info("Deleted service account '%s' (id=%s)", acct.name, acct.id)
        return True

    def check_permission(self, account_id: str, action: str, resource: str) -> bool:
        acct = self._accounts.get(account_id)
        if acct is None:
            logger.warning("Permission check failed: account '%s' not found", account_id)
            return False
        if not acct.is_active:
            return False
        required = f"{resource}:{action}"
        for role in acct.roles:
            if role == "*:*" or role == f"{resource}:*" or role == f"*:{action}" or role == required:
                return True
        return False


_manager: Optional[ServiceAccountManager] = None


def get_service_account_manager() -> ServiceAccountManager:
    global _manager
    if _manager is None:
        _manager = ServiceAccountManager()
    return _manager


def authenticate(key: str) -> Optional[ServiceAccount]:
    return get_service_account_manager().authenticate(key)


def create_account(
    name: str,
    description: str,
    roles: list[str],
    expires_at: Optional[str] = None,
    allowed_agents: Optional[list[str]] = None,
    allowed_toolsets: Optional[list[str]] = None,
) -> tuple[ServiceAccount, str]:
    return get_service_account_manager().create(
        name=name,
        description=description,
        roles=roles,
        expires_at=expires_at,
        allowed_agents=allowed_agents,
        allowed_toolsets=allowed_toolsets,
    )
