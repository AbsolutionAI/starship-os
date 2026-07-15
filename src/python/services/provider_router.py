"""Provider Router — routes LLM queries to Ollama, OpenRouter, or custom OpenAI-compatible APIs."""

import os
import json
import yaml
import logging
from pathlib import Path

log = logging.getLogger("provider-router")

CONNECTIONS_PATH = Path(os.getenv("CONNECTIONS_FILE", "/opt/agnetic/lib/connections.yaml"))
CONFIG_PATH = Path(os.getenv("AGNETIC_ROOT", "/opt/agnetic/lib")) / "config.yaml"

_connections_cache = None
_providers_cache = None


def load_connections():
    global _connections_cache
    if _connections_cache is not None:
        return _connections_cache
    if CONNECTIONS_PATH.exists():
        try:
            with open(CONNECTIONS_PATH) as f:
                _connections_cache = yaml.safe_load(f) or {}
            return _connections_cache
        except Exception as e:
            log.warning("Failed to load connections: %s", e)
    _connections_cache = {"providers": {}}
    return _connections_cache


def load_providers_from_config():
    global _providers_cache
    if _providers_cache is not None:
        return _providers_cache
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                cfg = yaml.safe_load(f) or {}
            _providers_cache = cfg.get("providers", {})
            return _providers_cache
        except Exception as e:
            log.warning("Failed to load config providers: %s", e)
    _providers_cache = {}
    return _providers_cache


def get_provider(provider_name=None):
    connections = load_connections()
    config_providers = load_providers_from_config()

    prov = connections.get("providers", {}).get(provider_name, {}) if provider_name else {}
    if not prov and provider_name:
        prov = config_providers.get(provider_name, {})
    if not prov and not provider_name:
        for name, p in connections.get("providers", {}).items():
            if p.get("default"):
                prov = p
                break
        if not prov:
            for name, p in config_providers.items():
                if p.get("default"):
                    prov = p
                    break
    return prov


def get_agent_config(agent_name):
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                cfg = yaml.safe_load(f) or {}
            return cfg.get("agents", {}).get(agent_name, {})
        except Exception:
            pass
    return {}


def get_model_info(agent_name, model_name):
    """Get provider + model info for a given agent and model name."""
    connections = load_connections()
    agent_cfg = get_agent_config(agent_name)

    preferred_provider = agent_cfg.get("provider", "ollama")
    fallback_model = agent_cfg.get("fallback_model")
    fallback_provider = agent_cfg.get("fallback_provider")

    # Check if model is in any known provider's model list
    providers = connections.get("providers", {})
    for pname, pcfg in providers.items():
        models = pcfg.get("models", {})
        if model_name in models or any(model_name.startswith(k) for k in models):
            return {"provider": pname, "model": model_name, "config": pcfg}

    # Check if model name looks like a provider/model path (e.g. openai/gpt-4)
    if "/" in model_name:
        for pname, pcfg in providers.items():
            models = pcfg.get("models", {})
            for key in models:
                if model_name == key or model_name.endswith(key.split("/")[-1]):
                    return {"provider": pname, "model": model_name, "config": pcfg}

    # Default to the agent's preferred provider
    pcfg = providers.get(preferred_provider, {})
    if not pcfg:
        pcfg = {"type": "ollama", "url": os.getenv("OLLAMA_URL", "http://127.0.0.1:11435")}
    return {"provider": preferred_provider, "model": model_name, "config": pcfg}


def provider_supports_tools(provider_name):
    connections = load_connections()
    providers = connections.get("providers", {})
    p = providers.get(provider_name, {})
    ptype = p.get("type", "ollama")
    return ptype == "ollama"


async def query_provider(model_info, messages, system=None, tools=False, stream=False, nats=None):
    """Route a query to the right provider and return the response."""
    provider = model_info.get("provider", "ollama")
    model = model_info.get("model", "qwen2.5:3b")
    config = model_info.get("config", {})
    ptype = config.get("type", "ollama")
    url = config.get("url", os.getenv("OLLAMA_URL", "http://127.0.0.1:11435"))
    api_key = config.get("api_key", "")

    if ptype == "openai":
        return await _query_openai(url, api_key, model, messages, system, tools, stream)
    else:
        return await _query_ollama(url, model, messages, system, tools, stream)


async def _query_ollama(url, model, messages, system=None, tools=False, stream=False):
    import httpx

    if not tools:
        prompt = messages[-1]["content"] if messages else ""
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3},
        }
        if system:
            payload["system"] = system
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{url}/api/generate", json=payload)
            resp.raise_for_status()
            return resp.json().get("response", "")

    tool_defs = _get_tool_definitions("full")
    chat_messages = []
    if system:
        chat_messages.append({"role": "system", "content": system})
    chat_messages.extend(messages)

    payload = {
        "model": model,
        "messages": chat_messages,
        "stream": False,
        "tools": tool_defs,
        "options": {"temperature": 0.3},
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{url}/api/chat", json=payload)
        resp.raise_for_status()
        result = resp.json()
    msg = result.get("message", {})
    tool_calls = msg.get("tool_calls", [])
    if tool_calls:
        return {"tool_calls": tool_calls, "content": msg.get("content", "")}
    return msg.get("content", "")


async def _query_openai(url, api_key, model, messages, system=None, tools=False, stream=False):
    import httpx

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if "openrouter" in url:
        headers["HTTP-Referer"] = "https://github.com/anomalyco/opencode"
        headers["X-Title"] = "Starship OS"

    chat_messages = []
    if system:
        chat_messages.append({"role": "system", "content": system})
    chat_messages.extend(messages)

    payload = {
        "model": model,
        "messages": chat_messages,
        "stream": False,
        "max_tokens": 4096,
    }
    if tools:
        payload["tools"] = _get_openai_tool_definitions()

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{url}/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        result = resp.json()

    choice = result.get("choices", [{}])[0]
    msg = choice.get("message", {})
    tool_calls = msg.get("tool_calls", [])
    if tool_calls:
        return {"tool_calls": tool_calls, "content": msg.get("content", "")}
    return msg.get("content", "")


def _get_tool_definitions(style="full"):
    return [
        {
            "type": "function",
            "function": {
                "name": "shell",
                "description": "Execute a shell command and return output",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string", "description": "Shell command to run"}},
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file from disk",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "Absolute path to file"}},
                    "required": ["path"],
                },
            },
        },
    ]


def _get_openai_tool_definitions():
    return _get_tool_definitions()
