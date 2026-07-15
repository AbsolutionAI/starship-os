import enum
import glob as glob_mod
import json
import logging
import os
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("agnetic-hooks")


class HookEvent(enum.Enum):
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    PRE_COMPACT = "pre_compact"
    NOTIFICATION = "notification"
    STOP = "stop"
    SUBAGENT_STOP = "subagent_stop"


@dataclass
class HookResult:
    allowed: bool = True
    modified_input: dict | None = None
    system_message: str | None = None
    additional_context: str | None = None


@dataclass
class Hook:
    event: HookEvent
    matcher: str
    command: str
    timeout: int = 30


class HookManager:
    def __init__(self) -> None:
        self._hooks: list[Hook] = []
        self._lock = threading.Lock()
        self._load_default_files()

    def register_hook(
        self, event: HookEvent, matcher: str, command: str, timeout: int = 30
    ) -> None:
        hook = Hook(event=event, matcher=matcher, command=command, timeout=timeout)
        with self._lock:
            self._hooks.append(hook)

    def load_hooks_file(self, path: str | Path) -> None:
        p = Path(path)
        if not p.exists():
            log.warning("Hooks file not found: %s", p)
            return
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Failed to load hooks file %s: %s", p, e)
            return
        for entry in data.get("hooks", []):
            try:
                event = HookEvent(entry["event"])
            except (ValueError, KeyError):
                log.warning("Invalid event in %s: %s", p, entry.get("event"))
                continue
            matcher = entry.get("matcher", "*")
            command = entry.get("command", "")
            timeout = entry.get("timeout", 30)
            if not command:
                continue
            self.register_hook(event, matcher, command, timeout)

    def resolve_hooks(
        self, event: HookEvent, tool_name: str | None = None
    ) -> list[Hook]:
        matched: list[Hook] = []
        with self._lock:
            for hook in self._hooks:
                if hook.event != event:
                    continue
                if tool_name is not None and hook.matcher != "*":
                    if not glob_mod.fnmatch.fnmatch(tool_name, hook.matcher):
                        continue
                matched.append(hook)
        return matched

    def execute_hooks(
        self,
        event: HookEvent,
        tool_name: str | None = None,
        input_data: dict | None = None,
    ) -> list[HookResult]:
        hooks = self.resolve_hooks(event, tool_name)
        results: list[HookResult] = []
        input_data = input_data or {}

        for hook in hooks:
            payload = {
                "event": event.value,
                "tool_name": tool_name or "",
                "input": input_data,
                "session_id": input_data.get("session_id", ""),
                "cwd": input_data.get("cwd", os.getcwd()),
                "permission_mode": input_data.get("permission_mode", ""),
            }
            result = self._run_hook_command(hook, payload)
            results.append(result)
            if not result.allowed:
                break

        return results

    def _run_hook_command(self, hook: Hook, payload: dict) -> HookResult:
        try:
            proc = subprocess.run(
                hook.command,
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=hook.timeout,
                shell=True,
            )
        except subprocess.TimeoutExpired:
            log.warning("Hook timed out after %ds: %s", hook.timeout, hook.command)
            return HookResult(allowed=False, system_message="Hook timed out")
        except OSError as e:
            log.warning("Hook execution failed: %s — %s", hook.command, e)
            return HookResult(allowed=False, system_message=f"Hook error: {e}")

        if proc.returncode == 0:
            if not proc.stdout.strip():
                return HookResult(allowed=True)
            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError:
                return HookResult(allowed=True)
            return HookResult(
                allowed=data.get("allowed", True),
                modified_input=data.get("modified_input"),
                system_message=data.get("system_message"),
                additional_context=data.get("additional_context"),
            )

        if proc.returncode == 2:
            try:
                data = json.loads(proc.stdout) if proc.stdout.strip() else {}
            except json.JSONDecodeError:
                data = {}
            return HookResult(
                allowed=False,
                system_message=data.get(
                    "system_message", proc.stderr.strip() or "Hook blocked"
                ),
            )

        log.warning(
            "Hook returned code %d: %s", proc.returncode, hook.command
        )
        return HookResult(
            allowed=False,
            system_message=proc.stderr.strip() or f"Hook failed (code {proc.returncode})",
        )

    def should_block(
        self,
        event: HookEvent,
        tool_name: str | None = None,
        input_data: dict | None = None,
    ) -> bool:
        results = self.execute_hooks(event, tool_name, input_data)
        return any(not r.allowed for r in results)

    def _load_default_files(self) -> None:
        paths = [
            Path("/etc/agnetic/hooks.json"),
            Path("/opt/agnetic/hooks.json"),
            Path.home() / ".config/agnetic/hooks.json",
        ]
        for path in paths:
            self.load_hooks_file(path)


_hook_manager = HookManager()


def get_hook_manager() -> HookManager:
    return _hook_manager


def run_hooks(
    event: HookEvent,
    tool_name: str | None = None,
    input_data: dict | None = None,
) -> list[HookResult]:
    return _hook_manager.execute_hooks(event, tool_name, input_data)


def should_block(
    event: HookEvent,
    tool_name: str | None = None,
    input_data: dict | None = None,
) -> bool:
    return _hook_manager.should_block(event, tool_name, input_data)
