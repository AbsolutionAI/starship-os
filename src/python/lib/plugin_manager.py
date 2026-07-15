import os
import sys
import json
import asyncio
import logging
import importlib.util
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

log = logging.getLogger("agnetic-plugins")

PLUGINS_DIR = Path(os.getenv("PLUGINS_DIR", "/opt/agnetic/plugins"))
PLUGIN_REGISTRY = Path(os.getenv("PLUGIN_REGISTRY", "/opt/agnetic/lib/plugins.json"))

@dataclass
class Plugin:
    name: str
    version: str
    description: str = ""
    module: Any = None
    enabled: bool = True
    config: dict = field(default_factory=dict)
    tools: list = field(default_factory=list)
    hooks: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    @property
    def tool_definitions(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": f"plugin_{self.name}_{t['name']}",
                    "description": f"[Plugin:{self.name}] {t.get('description', '')}",
                    "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                },
            }
            for t in self.tools
        ]


class PluginManager:
    def __init__(self):
        self.plugins: dict[str, Plugin] = {}
        self._loaded = False

    def discover(self):
        if not PLUGINS_DIR.exists():
            PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
            return

        for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
            if not plugin_dir.is_dir() or plugin_dir.name.startswith("_"):
                continue

            manifest_path = plugin_dir / "plugin.json"
            if not manifest_path.exists():
                continue

            try:
                manifest = json.loads(manifest_path.read_text())
                plugin = Plugin(
                    name=manifest.get("name", plugin_dir.name),
                    version=manifest.get("version", "0.1.0"),
                    description=manifest.get("description", ""),
                    enabled=manifest.get("enabled", True),
                    config=manifest.get("config", {}),
                    metadata=manifest,
                )
                self._load_plugin_module(plugin, plugin_dir)
                self._load_plugin_tools(plugin, plugin_dir)
                self.plugins[plugin.name] = plugin
                log.info("Discovered plugin: %s v%s", plugin.name, plugin.version)
            except Exception as e:
                log.warning("Failed to load plugin '%s': %s", plugin_dir.name, e)

        self._load_registry()
        self._loaded = True

    def _load_plugin_module(self, plugin: Plugin, plugin_dir: Path):
        main_py = plugin_dir / "main.py"
        if not main_py.exists():
            return
        try:
            mod_name = f"agnetic_plugin_{plugin.name}"
            spec = importlib.util.spec_from_file_location(mod_name, main_py)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
                plugin.module = mod
                log.info("Loaded plugin module: %s", plugin.name)
        except Exception as e:
            log.warning("Failed to load plugin module '%s': %s", plugin.name, e)

    def _load_plugin_tools(self, plugin: Plugin, plugin_dir: Path):
        tools_path = plugin_dir / "tools.json"
        if tools_path.exists():
            try:
                tools_data = json.loads(tools_path.read_text())
                plugin.tools = tools_data
            except Exception as e:
                log.warning("Failed to load plugin tools '%s': %s", plugin.name, e)

    def _load_registry(self):
        if not PLUGIN_REGISTRY.exists():
            return
        try:
            registry = json.loads(PLUGIN_REGISTRY.read_text())
            for name, cfg in registry.get("plugins", {}).items():
                if name in self.plugins:
                    self.plugins[name].enabled = cfg.get("enabled", True)
                    if "config" in cfg:
                        self.plugins[name].config.update(cfg["config"])
        except Exception as e:
            log.warning("Failed to load plugin registry: %s", e)

    def get_tool_definitions(self) -> list:
        defs = []
        for plugin in self.plugins.values():
            if plugin.enabled:
                defs.extend(plugin.tool_definitions)
        return defs

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        for plugin in self.plugins.values():
            if not plugin.enabled:
                continue
            prefix = f"plugin_{plugin.name}_"
            if tool_name.startswith(prefix):
                inner_name = tool_name[len(prefix):]
                if plugin.module and hasattr(plugin.module, "handle_tool"):
                    try:
                        result = await plugin.module.handle_tool(inner_name, arguments, plugin.config)
                        return result
                    except Exception as e:
                        return {"error": True, "message": f"Plugin '{plugin.name}' tool error: {e}"}
                return {"error": True, "message": f"Plugin '{plugin.name}' has no handle_tool function"}
        return {"error": True, "message": f"Unknown plugin tool: {tool_name}"}

    def get_status(self) -> list:
        return [
            {
                "name": p.name,
                "version": p.version,
                "description": p.description,
                "enabled": p.enabled,
                "tools": len(p.tools),
                "has_module": p.module is not None,
            }
            for p in self.plugins.values()
        ]

    def enable(self, name: str) -> dict:
        if name not in self.plugins:
            return {"error": True, "message": f"Plugin '{name}' not found"}
        self.plugins[name].enabled = True
        self._save_registry()
        return {"status": "enabled", "plugin": name}

    def disable(self, name: str) -> dict:
        if name not in self.plugins:
            return {"error": True, "message": f"Plugin '{name}' not found"}
        self.plugins[name].enabled = False
        self._save_registry()
        return {"status": "disabled", "plugin": name}

    def _save_registry(self):
        try:
            registry = {"plugins": {}}
            for name, plugin in self.plugins.items():
                registry["plugins"][name] = {
                    "enabled": plugin.enabled,
                    "config": plugin.config,
                }
            PLUGIN_REGISTRY.write_text(json.dumps(registry, indent=2))
        except Exception as e:
            log.warning("Failed to save plugin registry: %s", e)


_plugin_manager = PluginManager()


def get_plugin_manager() -> PluginManager:
    return _plugin_manager
