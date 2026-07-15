import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("agnetic-shield")


@dataclass
class SecretPattern:
    name: str
    pattern: str
    severity: str = "medium"
    description: str = ""


@dataclass
class ScanResult:
    detected: bool = False
    findings: list[dict] = field(default_factory=list)
    risk_score: float = 0.0


BUILTIN_PATTERNS = [
    SecretPattern(
        name="aws_access_key_id",
        pattern=r"AKIA[0-9A-Z]{16}",
        severity="high",
        description="AWS Access Key ID",
    ),
    SecretPattern(
        name="aws_secret_access_key",
        pattern=r"(?i)(aws_secret_access_key|aws secret access key)[^a-zA-Z0-9=]*[a-zA-Z0-9\/+]{40}",
        severity="high",
        description="AWS Secret Access Key",
    ),
    SecretPattern(
        name="gcp_service_account_key",
        pattern=r"\"type\":\s*\"service_account\"",
        severity="high",
        description="GCP service account key",
    ),
    SecretPattern(
        name="github_pat",
        pattern=r"(?:ghp_|github_pat_)[a-zA-Z0-9_]{36,}",
        severity="high",
        description="GitHub personal access token",
    ),
    SecretPattern(
        name="ssh_private_key_openssh",
        pattern=r"-----BEGIN OPENSSH PRIVATE KEY-----",
        severity="high",
        description="OpenSSH private key",
    ),
    SecretPattern(
        name="ssh_private_key_rsa",
        pattern=r"-----BEGIN RSA PRIVATE KEY-----",
        severity="high",
        description="RSA private key",
    ),
    SecretPattern(
        name="jwt_token",
        pattern=r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}",
        severity="medium",
        description="JWT token",
    ),
    SecretPattern(
        name="slack_token",
        pattern=r"(xox[baprs]-[0-9a-zA-Z]{10,48})",
        severity="high",
        description="Slack API token",
    ),
    SecretPattern(
        name="api_key_generic",
        pattern=r"(?i)(api[_-]?key|apikey|api_secret|api[_-]?token)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-\.]{16,}['\"]?",
        severity="medium",
        description="Generic API key",
    ),
    SecretPattern(
        name="shadow_hash",
        pattern=r"^\w+:\$[0-9a-z]+\$[a-zA-Z0-9\.\/]+\$[a-zA-Z0-9\.\/]{16,}",
        severity="high",
        description="Password hash (shadow file)",
    ),
    SecretPattern(
        name="password_config",
        pattern=r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?[^'\"\s]{6,}['\"]?",
        severity="medium",
        description="Possible password in config",
    ),
]


class DroidShield:
    def __init__(self, policy_path: Optional[str] = None):
        self.patterns: list[SecretPattern] = list(BUILTIN_PATTERNS)
        self._scan_count = 0
        self._finding_count = 0
        if policy_path is None:
            policy_path = "/etc/agnetic/policy.json"
        self._load_policy(policy_path)

    def _load_policy(self, path: str):
        try:
            with open(path) as f:
                cfg = json.load(f).get("droid_shield", {})
        except (FileNotFoundError, json.JSONDecodeError):
            cfg = {}
        self.enabled = cfg.get("enabled", True)
        self.block_on_commit = cfg.get("block_on_commit", True)
        for cp in cfg.get("custom_patterns", []):
            self.patterns.append(
                SecretPattern(
                    name=cp["name"],
                    pattern=cp["pattern"],
                    severity=cp.get("severity", "medium"),
                    description=cp.get("description", ""),
                )
            )

    def _score(self, severity: str) -> float:
        return {"high": 1.0, "medium": 0.6, "low": 0.3}.get(severity, 0.3)

    def scan_text(self, text: str, filename: str = "") -> ScanResult:
        result = ScanResult()
        if not self.enabled:
            return result
        self._scan_count += 1
        for pat in self.patterns:
            for match in re.finditer(pat.pattern, text, re.MULTILINE):
                result.detected = True
                finding = {
                    "pattern": pat.name,
                    "severity": pat.severity,
                    "description": pat.description,
                    "filename": filename,
                    "match": match.group()[:40],
                    "position": match.start(),
                }
                result.findings.append(finding)
                self._finding_count += 1
        if result.findings:
            result.risk_score = sum(
                self._score(f["severity"]) for f in result.findings
            ) / len(result.findings)
        return result

    def scan_file(self, path: str) -> ScanResult:
        try:
            with open(path, errors="replace") as f:
                content = f.read()
        except Exception as exc:
            logger.error("Failed to read %s: %s", path, exc)
            return ScanResult()
        return self.scan_text(content, filename=path)

    def scan_git_diff(self, diff_text: str) -> ScanResult:
        added = []
        for line in diff_text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added.append(line[1:])
        return self.scan_text("\n".join(added), filename="<diff>")

    def check_git_commit(self, repo_path: str) -> ScanResult:
        try:
            diff = subprocess.run(
                ["git", "-C", repo_path, "diff", "--cached"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        except subprocess.CalledProcessError as exc:
            logger.error("Git diff failed: %s", exc)
            return ScanResult()
        result = self.scan_git_diff(diff)
        if result.detected and self.block_on_commit:
            logger.warning(
                "Blocking commit — %d secret(s) detected in staged changes",
                len(result.findings),
            )
        return result

    def add_custom_pattern(
        self, name: str, regex: str, severity: str = "medium", description: str = ""
    ):
        self.patterns.append(SecretPattern(name, regex, severity, description))

    def load_custom_patterns(self, path: str):
        try:
            with open(path) as f:
                patterns = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            logger.error("Failed to load custom patterns: %s", exc)
            return
        for p in patterns:
            self.add_custom_pattern(
                p["name"],
                p["pattern"],
                p.get("severity", "medium"),
                p.get("description", ""),
            )

    def redact(self, text: str) -> str:
        for pat in self.patterns:
            text = re.sub(pat.pattern, "[REDACTED]", text)
        return text

    def get_stats(self) -> dict:
        return {
            "scans": self._scan_count,
            "findings": self._finding_count,
            "patterns_loaded": len(self.patterns),
            "enabled": self.enabled,
            "block_on_commit": self.block_on_commit,
        }


_shield: Optional[DroidShield] = None


def get_shield() -> DroidShield:
    global _shield
    if _shield is None:
        _shield = DroidShield()
    return _shield


def scan(text: str, filename: str = "") -> ScanResult:
    return get_shield().scan_text(text, filename)


def redact(text: str) -> str:
    return get_shield().redact(text)


def check_git_precommit(path: str = ".") -> ScanResult:
    return get_shield().check_git_commit(path)
