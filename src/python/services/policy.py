import os
import re
import json
import glob as globmod
import logging
import shutil
import fnmatch
from enum import IntEnum
from copy import deepcopy
from pathlib import Path

log = logging.getLogger("agnetic-policy")


class PolicyLevel(IntEnum):
    SYSTEM = 0
    SERVICE = 1
    USER = 2


class PolicyViolation(Exception):
    pass


class CommandBlocklist:
    def __init__(self):
        self._blocklist = []
        self._denylist = []
        self._allowlist = []

    def add_blocklist(self, patterns):
        if isinstance(patterns, str):
            patterns = [patterns]
        self._blocklist.extend(patterns)

    def add_denylist(self, patterns):
        if isinstance(patterns, str):
            patterns = [patterns]
        self._denylist.extend(patterns)

    def add_allowlist(self, patterns):
        if isinstance(patterns, str):
            patterns = [patterns]
        self._allowlist.extend(patterns)

    def _match_pattern(self, pattern, resolved_path, basename):
        if pattern == resolved_path:
            return True
        if basename == pattern:
            return True
        if fnmatch.fnmatch(resolved_path, pattern):
            return True
        if fnmatch.fnmatch(basename, pattern):
            return True
        return False

    def check_command(self, command_string):
        command_string = command_string.strip()
        cleaned = self._clean_command(command_string)
        if not cleaned:
            return False, "empty command after cleaning", None
        parts = cleaned.split()
        program = parts[0]
        resolved = shutil.which(program)
        if resolved is None:
            resolved = program
        basename = os.path.basename(resolved)
        for pattern in self._allowlist:
            if self._match_pattern(pattern, resolved, basename):
                return True, "command allowed by allowlist", resolved
        for pattern in self._blocklist:
            if self._match_pattern(pattern, resolved, basename):
                return False, "command is blocked", resolved
        for pattern in self._denylist:
            if self._match_pattern(pattern, resolved, basename):
                return False, "command requires approval", resolved
        return True, "command not restricted", resolved

    @staticmethod
    def _clean_command(cmd):
        cmd = re.sub(r'[\'"]', '', cmd)
        cmd = re.sub(r'\$\([^)]*\)', '', cmd)
        cmd = re.sub(r'`[^`]*`', '', cmd)
        cmd = re.sub(r'\$\{[^}]*\}', '', cmd)
        cmd = re.sub(r'\$(\w+)', '', cmd)
        cmd = re.sub(r'\s*\|\s*', ' ', cmd)
        cmd = re.sub(r'[;]', ' ', cmd)
        cmd = re.sub(r'\s{2,}', ' ', cmd).strip()
        return cmd


class PolicyManager:
    _SYSTEM_PATH = "/etc/agnetic/policy.json"
    _SERVICE_PATH = "/opt/agnetic/policy.json"
    _USER_PATH = str(Path.home() / ".config" / "agnetic" / "policy.json")

    def __init__(self, paths=None):
        self._policies = {}
        self._levels = {}
        self._command_blocklist = CommandBlocklist()
        if paths is not None:
            for path in paths:
                self._load_file(path)
        else:
            self.load_system_policy()
            self.load_service_policy()
            self.load_user_policy()

    def _load_file(self, path, level=None):
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            log.warning("could not load policy %s: %s", path, e)
            return
        level_enum = PolicyLevel[level] if level else None
        self._merge(level_enum, data)
        blocklist_data = data.get("command_blocklist", [])
        if isinstance(blocklist_data, list):
            self._command_blocklist.add_blocklist(blocklist_data)
        denylist_data = data.get("command_denylist", [])
        if isinstance(denylist_data, list):
            self._command_blocklist.add_denylist(denylist_data)
        allowlist_data = data.get("command_allowlist", [])
        if isinstance(allowlist_data, list):
            self._command_blocklist.add_allowlist(allowlist_data)

    def load_system_policy(self):
        self._load_file(self._SYSTEM_PATH, level="SYSTEM")

    def load_service_policy(self):
        self._load_file(self._SERVICE_PATH, level="SERVICE")

    def load_user_policy(self):
        self._load_file(self._USER_PATH, level="USER")

    def _merge(self, level, data):
        if level is None:
            self._deep_merge(self._policies, data, locked_keys=set())
        else:
            existing_level = self._levels.get(level, {})
            locked = set()
            for k in existing_level:
                locked.add(k)
            if level in self._levels:
                existing_data = self._levels[level]
                for k, v in data.items():
                    if k not in existing_data:
                        existing_data[k] = deepcopy(v)
                    else:
                        existing_data[k] = self._merge_value(
                            existing_data[k], v, locked
                        )
            else:
                self._levels[level] = deepcopy(data)
            self._rebuild_merged()

    def _rebuild_merged(self):
        merged = {}
        locked = set()
        for level in sorted(PolicyLevel):
            data = self._levels.get(level, {})
            if not data:
                continue
            self._deep_merge(merged, deepcopy(data), locked)
            for k in data:
                locked.add(k)
        self._policies = merged

    def _deep_merge(self, base, overlay, locked_keys):
        for k, v in overlay.items():
            if k in locked_keys:
                continue
            if k in base:
                base[k] = self._merge_value(base[k], v, locked_keys)
            else:
                base[k] = v

    def _merge_value(self, existing, incoming, locked_keys):
        if isinstance(existing, dict) and isinstance(incoming, dict):
            result = deepcopy(existing)
            sub_locked = set(locked_keys)
            for sk in existing:
                sub_locked.add(sk)
            for k, v in incoming.items():
                if k in sub_locked:
                    continue
                if k in result:
                    result[k] = self._merge_value(result[k], v, sub_locked)
                else:
                    result[k] = deepcopy(v)
            return result
        if isinstance(existing, list) and isinstance(incoming, list):
            seen = set()
            union = []
            for item in existing:
                key = json.dumps(item, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    union.append(deepcopy(item))
            for item in incoming:
                key = json.dumps(item, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    union.append(deepcopy(item))
            return union
        return deepcopy(existing)

    def get(self, key, default=None):
        parts = key.split(".")
        current = self._policies
        try:
            for part in parts:
                current = current[part]
        except (KeyError, TypeError):
            return default
        return current

    def get_all(self):
        return deepcopy(self._policies)

    def check_action(self, action_type, target):
        action_key = f"actions.{action_type}"
        policy = self.get(action_key)
        if policy is None:
            return True, f"no policy for action '{action_type}'"
        if isinstance(policy, dict):
            allowed_targets = policy.get("allow", [])
            denied_targets = policy.get("deny", [])
            if isinstance(denied_targets, list):
                for rule in denied_targets:
                    if fnmatch.fnmatch(target, rule):
                        return False, f"action '{action_type}' denied on '{target}'"
            if isinstance(allowed_targets, list):
                if allowed_targets:
                    for rule in allowed_targets:
                        if fnmatch.fnmatch(target, rule):
                            return True, f"action '{action_type}' allowed on '{target}'"
                    return False, f"action '{action_type}' not allowed on '{target}'"
        if policy is False:
            return False, f"action '{action_type}' is disabled"
        return True, f"action '{action_type}' allowed"


_policy_manager_instance = None


def get_policy_manager():
    global _policy_manager_instance
    if _policy_manager_instance is None:
        _policy_manager_instance = PolicyManager()
    return _policy_manager_instance
