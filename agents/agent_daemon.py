#!/usr/bin/env python3
"""
Starship OS Agent Daemon

Subscribes to NATS command subjects for a given agent role,
processes commands via Ollama API, and publishes responses back.

Usage:
  python3 agent_daemon.py <agent_name> [--model MODEL] [--nats NATS_URL]

Agent config files are loaded from ./agents/<agent_name>.yaml
"""

import sys
import os
import json
import yaml
import asyncio
import logging
import signal
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("agent-daemon")

NATS_URL = os.getenv("NATS_URL", "nats://127.0.0.1:4222")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
AGENTS_DIR = Path(os.getenv("STARSHIP_ROOT", os.path.dirname(os.path.abspath(__file__)))) / "agents"


def load_agent_config(name):
    """Load agent YAML config."""
    config_path = AGENTS_DIR / f"{name}.yaml"
    if not config_path.exists():
        log.error("Agent config not found: %s", config_path)
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f)


async def query_ollama(model, prompt, system=None):
    """Send a prompt to Ollama and return the response."""
    import httpx
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3},
    }
    if system:
        payload["system"] = system
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
        resp.raise_for_status()
        result = resp.json()
        return result.get("response", "")


async def process_command(agent_name, config, subject, payload):
    """Process a single command and return the result."""
    model = config.get("model", "qwen2.5:7b")
    role = config.get("role", "assistant")
    capabilities = config.get("capabilities", [])
    skills = config.get("skills", [])
    
    command = payload.get("command", "")
    args = payload.get("args", {})
    
    system_prompt = (
        f"You are {agent_name}, the {role} in the Starship OS agent mesh.\n"
        f"Your capabilities: {', '.join(capabilities) if capabilities else 'general assistance'}.\n"
        f"You operate via the NATS agent bus. Respond concisely and accurately.\n"
        f"Current time: {datetime.now().isoformat()}"
    )
    
    user_prompt = f"Command: {command}\n"
    if args:
        user_prompt += f"Arguments: {json.dumps(args, indent=2)}\n"
    user_prompt += "\nProvide your response."
    
    log.info("Processing command '%s' for agent '%s'", command, agent_name)
    response = await query_ollama(model, user_prompt, system=system_prompt)
    log.info("Response received (%d chars) for '%s'", len(response), command)
    return response


async def run_agent(agent_name, model_override=None):
    """Main agent daemon loop."""
    config = load_agent_config(agent_name)
    model = model_override or config.get("model", "qwen2.5:7b")
    nats_config = config.get("nats", {})
    cmd_subject = nats_config.get("subjects", {}).get("command", f"starship.agent.{agent_name}.command.>")
    status_subject = nats_config.get("subjects", {}).get("status", f"starship.agent.{agent_name}.status")
    event_subject = nats_config.get("subjects", {}).get("event", f"starship.agent.{agent_name}.event.>")
    
    log.info("Starting agent '%s' (model=%s, nats=%s)", agent_name, model, NATS_URL)
    log.info("  Command subject: %s", cmd_subject)
    
    try:
        from nats import connect as nats_connect
        from nats.errors import TimeoutError
        
        nc = await nats_connect(NATS_URL)
        log.info("Connected to NATS: %s", NATS_URL)
        
        await nc.publish(status_subject, json.dumps({
            "agent": agent_name,
            "status": "online",
            "model": model,
            "timestamp": datetime.now().isoformat(),
        }).encode())
        
        sub = await nc.subscribe(cmd_subject)
        log.info("Subscribed to: %s", cmd_subject)
        
        async def handle_msg(msg):
            subject = msg.subject
            try:
                data = json.loads(msg.data.decode())
                log.info("Received command on %s", subject)
                
                reply_subject = f"starship.agent.{agent_name}.status"
                await nc.publish(reply_subject, json.dumps({
                    "agent": agent_name,
                    "status": "processing",
                    "command": data.get("command", ""),
                    "timestamp": datetime.now().isoformat(),
                }).encode())
                
                response = await process_command(agent_name, config, subject, data)
                
                # Publish response to status (for simple replies) or a reply subject
                reply_to = data.get("reply_to", status_subject)
                await nc.publish(reply_to, json.dumps({
                    "agent": agent_name,
                    "status": "complete",
                    "command": data.get("command", ""),
                    "response": response,
                    "timestamp": datetime.now().isoformat(),
                }).encode())
                
                # If the message had a reply subject (NATS request-reply), respond directly
                if msg.reply:
                    await nc.publish(msg.reply, json.dumps({
                        "agent": agent_name,
                        "response": response,
                    }).encode())
                    
            except json.JSONDecodeError:
                log.warning("Invalid JSON on %s: %s", subject, msg.data[:200])
                if msg.reply:
                    await nc.publish(msg.reply, json.dumps({"error": "invalid JSON"}).encode())
            except Exception as e:
                log.error("Error processing message: %s", e)
                if msg.reply:
                    await nc.publish(msg.reply, json.dumps({"error": str(e)}).encode())
        
        # Process messages
        await nc.flush()
        
        try:
            async for msg in sub.messages:
                await handle_msg(msg)
        except asyncio.CancelledError:
            pass
            
    except ImportError:
        log.error("nats-py not installed. Run: pip install nats-py")
        sys.exit(1)
    except KeyboardInterrupt:
        log.info("Shutting down...")
        if 'nc' in locals():
            await nc.publish(status_subject, json.dumps({
                "agent": agent_name,
                "status": "offline",
                "timestamp": datetime.now().isoformat(),
            }).encode())
            await nc.close()
    except Exception as e:
        log.error("Fatal error: %s", e)
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: agent_daemon.py <agent_name> [--model MODEL]")
        print("Examples: agent_daemon.py proxy")
        print("          agent_daemon.py romi --model qwen2.5:7b")
        print("          agent_daemon.py ergo")
        sys.exit(1)
    
    agent_name = sys.argv[1]
    model_override = None
    if "--model" in sys.argv:
        idx = sys.argv.index("--model")
        if idx + 1 < len(sys.argv):
            model_override = sys.argv[idx + 1]
    
    asyncio.run(run_agent(agent_name, model_override))


if __name__ == "__main__":
    main()
