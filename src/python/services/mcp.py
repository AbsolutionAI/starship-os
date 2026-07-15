import os
import json
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

log = logging.getLogger("agnetic-mcp")

MCP_CONFIG_PATH = Path(os.getenv("MCP_CONFIG", "/opt/agnetic/lib/mcp_servers.json"))

@dataclass
class MCPServer:
    name: str
    command: str
    args: list = field(default_factory=list)
    env: dict = field(default_factory=dict)
    transport: str = "stdio"
    url: str = ""
    headers: dict = field(default_factory=dict)
    enabled: bool = True
    tools: list = field(default_factory=list)
    _proc: Any = None
    _connected: bool = False


class MCPManager:
    def __init__(self):
        self.servers: dict[str, MCPServer] = {}
        self._tools_cache: list = []
        self._loaded = False

    def load_config(self):
        if not MCP_CONFIG_PATH.exists():
            log.info("No MCP config at %s", MCP_CONFIG_PATH)
            return
        try:
            data = json.loads(MCP_CONFIG_PATH.read_text())
            for name, cfg in data.get("servers", {}).items():
                server = MCPServer(
                    name=name,
                    command=cfg.get("command", ""),
                    args=cfg.get("args", []),
                    env={**os.environ, **cfg.get("env", {})},
                    transport=cfg.get("transport", "stdio"),
                    url=cfg.get("url", ""),
                    headers=cfg.get("headers", {}),
                    enabled=cfg.get("enabled", True),
                )
                self.servers[name] = server
            log.info("Loaded %d MCP servers", len(self.servers))
        except Exception as e:
            log.warning("Failed to load MCP config: %s", e)

    async def _connect_stdio(self, server: MCPServer):
        try:
            proc = await asyncio.create_subprocess_exec(
                server.command, *server.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=server.env if server.env else None,
            )
            server._proc = proc
            server._connected = True

            init_msg = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "0.1.0", "capabilities": {}
            }}) + "\n"

            proc.stdin.write(init_msg.encode())
            await proc.stdin.drain()

            resp = await asyncio.wait_for(proc.stdout.readline(), timeout=10)
            result = json.loads(resp.decode())

            tools_list = result.get("result", {}).get("capabilities", {}).get("tools", [])
            server.tools = tools_list

            log.info("MCP server '%s' connected with %d tools", server.name, len(server.tools))
            return True
        except Exception as e:
            log.warning("Failed to connect MCP server '%s': %s", server.name, e)
            server._connected = False
            return False

    async def initialize(self):
        if self._loaded:
            return
        self.load_config()
        tasks = []
        for name, server in self.servers.items():
            if server.enabled and server.transport == "stdio" and server.command:
                tasks.append(self._connect_stdio(server))
        if tasks:
            await asyncio.gather(*tasks)
        self._rebuild_tools_cache()
        self._loaded = True

    def _rebuild_tools_cache(self):
        tools = []
        for name, server in self.servers.items():
            if server._connected:
                for t in server.tools:
                    t["mcp_server"] = name
                    tools.append(t)
        self._tools_cache = tools

    def get_tool_definitions(self):
        if not self._loaded:
            return []
        return [
            {
                "type": "function",
                "function": {
                    "name": f"mcp_{t['name']}",
                    "description": f"[MCP:{t.get('mcp_server','?')}] {t.get('description','')}",
                    "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
                },
            }
            for t in self._tools_cache
        ]

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        mcp_server_name = None
        inner_tool_name = tool_name
        if tool_name.startswith("mcp_"):
            inner_tool_name = tool_name[4:]

        for name, server in self.servers.items():
            if not server._connected:
                continue
            for t in server.tools:
                if t.get("name") == inner_tool_name:
                    mcp_server_name = name
                    break
            if mcp_server_name:
                break

        if not mcp_server_name:
            return {"error": True, "message": f"MCP tool '{tool_name}' not found on any connected server"}

        server = self.servers[mcp_server_name]
        call_msg = json.dumps({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": inner_tool_name, "arguments": arguments},
        }) + "\n"

        try:
            server._proc.stdin.write(call_msg.encode())
            await server._proc.stdin.drain()
            resp = await asyncio.wait_for(server._proc.stdout.readline(), timeout=30)
            result = json.loads(resp.decode())
            content = result.get("result", {}).get("content", [])
            is_error = result.get("result", {}).get("isError", False)

            text_parts = []
            for c in content:
                if c.get("type") == "text":
                    text_parts.append(c.get("text", ""))
                elif c.get("type") == "resource":
                    text_parts.append(json.dumps(c.get("resource", {})))

            return {
                "output": "\n".join(text_parts),
                "error": is_error,
                "mcp_server": mcp_server_name,
                "tool": inner_tool_name,
            }
        except asyncio.TimeoutError:
            return {"error": True, "message": f"MCP tool '{tool_name}' timed out after 30s"}
        except Exception as e:
            return {"error": True, "message": f"MCP call failed: {e}"}

    async def disconnect_all(self):
        for name, server in self.servers.items():
            if server._proc:
                try:
                    server._proc.terminate()
                    await asyncio.wait_for(server._proc.wait(), timeout=5)
                except Exception:
                    try:
                        server._proc.kill()
                    except Exception:
                        pass
            server._connected = False
        self._tools_cache = []


_mcp_manager = MCPManager()


async def init_mcp():
    await _mcp_manager.initialize()


def get_mcp_tool_definitions() -> list:
    return _mcp_manager.get_tool_definitions()


async def call_mcp_tool(name: str, arguments: dict) -> dict:
    return await _mcp_manager.call_tool(name, arguments)
