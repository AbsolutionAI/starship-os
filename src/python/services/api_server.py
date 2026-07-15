import os
import json
import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

log = logging.getLogger("agnetic-api")

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8080"))
API_KEY = os.getenv("API_KEY", "")


class ApiServer:
    def __init__(self, nats=None):
        self.nats = nats
        self._app = None
        self._server = None

    async def start(self):
        try:
            from aiohttp import web
        except ImportError:
            log.warning("aiohttp not installed. Install: pip install aiohttp")
            return False

        app = web.Application()
        app.router.add_post("/v1/chat/completions", self._handle_chat)
        app.router.add_post("/v1/completions", self._handle_completion)
        app.router.add_get("/v1/models", self._handle_models)
        app.router.add_get("/health", self._handle_health)

        runner = web.AppRunner(app)
        await runner.setup()
        self._server = web.TCPSite(runner, API_HOST, API_PORT)
        await self._server.start()
        log.info("API server listening on %s:%s (key=%s)", API_HOST, API_PORT, bool(API_KEY))
        return True

    async def _check_auth(self, request):
        if not API_KEY:
            return True
        auth = request.headers.get("Authorization", "")
        return auth == f"Bearer {API_KEY}"

    async def _handle_chat(self, request):
        if not await self._check_auth(request):
            return self._json_response({"error": "Unauthorized"}, 401)

        try:
            body = await request.json()
        except Exception:
            return self._json_response({"error": "Invalid JSON"}, 400)

        model = body.get("model", "qwen2.5:7b")
        messages = body.get("messages", [])
        stream = body.get("stream", False)
        tools = body.get("tools", [])

        if not messages:
            return self._json_response({"error": "No messages"}, 400)

        user_msg = messages[-1].get("content", "")
        agent = body.get("agent", "romi")

        if self.nats:
            reply_sub = f"agnetic.api.reply.{uuid.uuid4().hex}"
            sub = await self.nats.subscribe(reply_sub, max_msgs=1)
            await self.nats.publish(
                f"agnetic.agent.{agent}.command.{user_msg.replace(' ', '.')[:100]}",
                json.dumps({
                    "command": user_msg,
                    "model": model,
                    "reply_to": reply_sub,
                }).encode(),
            )
            try:
                msg = await sub.next_msg(timeout=120)
                result = json.loads(msg.data.decode())
                response_text = result.get("response", str(result))
            except asyncio.TimeoutError:
                response_text = f"Agent '{agent}' did not respond in time"
        else:
            response_text = f"[Echo] {user_msg} (no NATS)"

        if stream:
            return self._json_response({
                "id": f"chatcmpl-{uuid.uuid4().hex}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": response_text},
                    "finish_reason": "stop",
                }],
            })

        return self._json_response({
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text,
                },
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": len(user_msg) // 4,
                "completion_tokens": len(response_text) // 4,
                "total_tokens": (len(user_msg) + len(response_text)) // 4,
            },
        })

    async def _handle_completion(self, request):
        if not await self._check_auth(request):
            return self._json_response({"error": "Unauthorized"}, 401)

        try:
            body = await request.json()
        except Exception:
            return self._json_response({"error": "Invalid JSON"}, 400)

        prompt = body.get("prompt", "")
        model = body.get("model", "qwen2.5:7b")

        return self._json_response({
            "id": f"cmpl-{uuid.uuid4().hex}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "text": f"[Echo] {prompt}",
                "index": 0,
                "finish_reason": "stop",
            }],
        })

    async def _handle_models(self, request):
        models = [
            {"id": "qwen2.5:7b", "object": "model", "created": int(time.time()), "owned_by": "ollama"},
            {"id": "qwen2.5:3b", "object": "model", "created": int(time.time()), "owned_by": "ollama"},
            {"id": "agnetic-romi", "object": "model", "created": int(time.time()), "owned_by": "agnetic"},
            {"id": "agnetic-proxy", "object": "model", "created": int(time.time()), "owned_by": "agnetic"},
            {"id": "agnetic-ergo", "object": "model", "created": int(time.time()), "owned_by": "agnetic"},
        ]
        return self._json_response({"object": "list", "data": models})

    async def _handle_health(self, request):
        return self._json_response({"status": "ok", "service": "agnetic-os-api"})

    def _json_response(self, data, status=200):
        from aiohttp import web
        return web.json_response(data, status=status)

    async def stop(self):
        if self._server:
            await self._server.stop()
            log.info("API server stopped")
