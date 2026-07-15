#!/usr/bin/env python3
"""OpenTelemetry-native telemetry export system inspired by Factory AI's OTEL integration."""

import os
import json
import time
import enum
import logging
import threading
import dataclasses
from datetime import datetime, timezone
from pathlib import Path

import httpx

log = logging.getLogger("agnetic-telemetry")

_TELEMETRY_JSONL = Path("/var/log/agnetic/telemetry.jsonl")
_MAX_JSONL_BYTES = 100 * 1024 * 1024

_ENV_TYPE = os.getenv("AGNETIC_ENV", "production")


class TelemetryEvent(str, enum.Enum):
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    TOOL_INVOCATION = "tool_invocation"
    FILE_MODIFIED = "file_modified"
    COMMAND_EXECUTED = "command_executed"
    AGENT_SPAWNED = "agent_spawned"
    AGENT_STOPPED = "agent_stopped"
    ERROR = "error"
    POLICY_VIOLATION = "policy_violation"
    SECURITY_EVENT = "security_event"


@dataclasses.dataclass
class TelemetryPoint:
    event_type: str
    timestamp: str
    agent_id: str
    session_id: str
    user_id: str
    attributes: dict
    duration_ms: float | None


class _ContentMessage:
    __slots__ = ("session_id", "role", "content", "timestamp")

    def __init__(self, session_id, role, content, timestamp):
        self.session_id = session_id
        self.role = role
        self.content = content
        self.timestamp = timestamp


class TelemetryExporter:
    def __init__(self):
        self._buffer: list[TelemetryPoint] = []
        self._content_buffer: list[_ContentMessage] = []
        self._counter: dict[str, int] = {}
        self._lock = threading.Lock()
        self._export_lock = threading.Lock()
        self._periodic_thread: threading.Thread | None = None
        self._periodic_event = threading.Event()
        self._periodic_running = False

        self._customer_endpoint = (
            os.getenv("OTEL_TELEMETRY_ENDPOINT", "").rstrip("/")
            or None
        )
        self._customer_headers: dict[str, str] = {}
        self._agnetic_endpoint: str | None = None
        self._agnetic_headers: dict[str, str] = {}
        self._content_logging = False
        self._enabled = True
        self._flush_interval = 60
        self._mode = "disabled"

        self._load_policy_config()
        self._load_customer_headers()

        if self._customer_endpoint:
            self._mode = "otlp"
            log.info(
                "OTEL telemetry enabled, customer endpoint: %s",
                self._customer_endpoint,
            )
        elif _TELEMETRY_JSONL.parent.exists():
            self._mode = "file"
            log.info("No OTEL endpoint configured; fallback to JSONL log")
        else:
            self._mode = "disabled"
            log.info("Telemetry disabled (no endpoint or log path)")

    def _load_policy_config(self):
        try:
            from .policy import get_policy_manager

            pm = get_policy_manager()
            cfg = pm.get("telemetry", {})
        except Exception:
            cfg = {}
        if not isinstance(cfg, dict):
            return
        self._enabled = bool(cfg.get("enabled", True))
        if not self._customer_endpoint:
            self._customer_endpoint = (
                str(cfg.get("customer_endpoint") or "").rstrip("/") or None
            )
        customer_h = cfg.get("customer_headers")
        if isinstance(customer_h, dict):
            self._customer_headers.update(customer_h)
        agn_endpoint = cfg.get("agnetic_endpoint")
        if agn_endpoint:
            self._agnetic_endpoint = str(agn_endpoint).rstrip("/")
        agn_h = cfg.get("agnetic_headers")
        if isinstance(agn_h, dict):
            self._agnetic_headers.update(agn_h)
        self._content_logging = bool(cfg.get("content_logging", False))
        fi = cfg.get("flush_interval_seconds")
        if isinstance(fi, (int, float)) and fi > 0:
            self._flush_interval = int(fi)

    def _load_customer_headers(self):
        raw = os.getenv("OTEL_TELEMETRY_HEADERS", "")
        if raw:
            for part in raw.split(","):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    self._customer_headers[k.strip()] = v.strip()

    def record_event(
        self,
        event_type,
        agent_id="",
        session_id="",
        user_id="",
        attributes=None,
        duration_ms=None,
    ):
        if isinstance(event_type, TelemetryEvent):
            event_type = event_type.value
        if not self._enabled:
            return
        point = TelemetryPoint(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent_id=agent_id,
            session_id=session_id,
            user_id=user_id,
            attributes=attributes or {},
            duration_ms=duration_ms,
        )
        with self._lock:
            self._buffer.append(point)
            self._counter[event_type] = self._counter.get(event_type, 0) + 1

    def record_message_content(self, session_id, role, content):
        if not self._content_logging:
            return
        if not self._customer_endpoint:
            return
        msg = _ContentMessage(
            session_id=session_id,
            role=role,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._content_buffer.append(msg)

    def export(self):
        with self._export_lock:
            points, messages = self._drain_buffers()
        if not points:
            return

        fallback = not self._customer_endpoint and not self._agnetic_endpoint

        if self._customer_endpoint:
            self._send_metrics(points, self._customer_endpoint, self._customer_headers)
            self._send_traces_from_points(
                points, self._customer_endpoint, self._customer_headers
            )
        if self._agnetic_endpoint:
            self._send_metrics(points, self._agnetic_endpoint, self._agnetic_headers)

        if messages and self._customer_endpoint:
            self._export_content_batch(messages)

        if fallback:
            self._write_jsonl(points)

    def _drain_buffers(self):
        with self._lock:
            points = list(self._buffer)
            messages = list(self._content_buffer)
            self._buffer.clear()
            self._content_buffer.clear()
        return points, messages

    def _send_metrics(self, points, endpoint, headers):
        timestamp_ns = int(time.time() * 1_000_000_000)
        resource_metrics = []
        for event_type in set(p.event_type for p in points):
            attrs = [
                {"key": "agent.id", "value": {"stringValue": p.agent_id}}
                for p in points
                if p.event_type == event_type
            ]
            data_points = []
            for p in points:
                if p.event_type != event_type:
                    continue
                dp_attrs = [
                    {"key": "agent.id", "value": {"stringValue": p.agent_id}},
                    {"key": "session.id", "value": {"stringValue": p.session_id}},
                    {"key": "user.id", "value": {"stringValue": p.user_id}},
                    {
                        "key": "environment.type",
                        "value": {"stringValue": _ENV_TYPE},
                    },
                ]
                for ak, av in p.attributes.items():
                    dp_attrs.append(
                        {
                            "key": str(ak),
                            "value": {"stringValue": str(av)},
                        }
                    )
                data_point = {
                    "attributes": dp_attrs,
                    "startTimeUnixNano": str(timestamp_ns),
                    "timeUnixNano": str(timestamp_ns),
                    "asDouble": 1.0,
                }
                if p.duration_ms is not None:
                    data_point["asDouble"] = float(p.duration_ms)
                data_points.append(data_point)
            scope_metrics = [
                {
                    "scope": {},
                    "metrics": [
                        {
                            "name": f"agnetic.{event_type}",
                            "unit": "1",
                            "sum": {
                                "dataPoints": data_points,
                                "aggregationTemporality": 2,
                                "isMonotonic": True,
                            },
                        }
                    ],
                }
            ]
            resource_metrics.append(
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "service.name",
                                "value": {"stringValue": "agnetic"},
                            }
                        ]
                    },
                    "scopeMetrics": scope_metrics,
                }
            )
        payload = {"resourceMetrics": resource_metrics}
        url = f"{endpoint}/v1/metrics"
        self._do_post(url, payload, headers)

    def _send_traces_from_points(self, points, endpoint, headers):
        timestamp_ns = int(time.time() * 1_000_000_000)
        spans = []
        for p in points:
            span_attrs = [
                {"key": "agent.id", "value": {"stringValue": p.agent_id}},
                {"key": "session.id", "value": {"stringValue": p.session_id}},
                {"key": "user.id", "value": {"stringValue": p.user_id}},
                {"key": "environment.type", "value": {"stringValue": _ENV_TYPE}},
                {
                    "key": "event.type",
                    "value": {"stringValue": p.event_type},
                },
            ]
            for ak, av in p.attributes.items():
                span_attrs.append(
                    {
                        "key": str(ak),
                        "value": {"stringValue": str(av)},
                    }
                )
            span = {
                "traceId": p.session_id.replace("-", "")[:32].ljust(32, "0"),
                "spanId": p.agent_id.replace("-", "")[:16].ljust(16, "0") or "0" * 16,
                "name": p.event_type,
                "startTimeUnixNano": str(timestamp_ns),
                "endTimeUnixNano": str(timestamp_ns),
                "attributes": span_attrs,
            }
            if p.duration_ms is not None:
                span["endTimeUnixNano"] = str(
                    timestamp_ns + int(p.duration_ms * 1_000_000)
                )
            spans.append(span)
        payload = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "service.name",
                                "value": {"stringValue": "agnetic"},
                            }
                        ]
                    },
                    "scopeSpans": [{"scope": {}, "spans": spans}],
                }
            ]
        }
        url = f"{endpoint}/v1/traces"
        self._do_post(url, payload, headers)

    def _export_content_batch(self, messages):
        timestamp_ns = int(time.time() * 1_000_000_000)
        spans = []
        for msg in messages:
            content_span = {
                "traceId": msg.session_id.replace("-", "")[:32].ljust(32, "0"),
                "spanId": "0" * 16,
                "name": f"agnetic.content.{msg.role}",
                "startTimeUnixNano": str(timestamp_ns),
                "endTimeUnixNano": str(timestamp_ns),
                "attributes": [
                    {
                        "key": "session.id",
                        "value": {"stringValue": msg.session_id},
                    },
                    {"key": "role", "value": {"stringValue": msg.role}},
                ],
            }
            spans.append(content_span)
        payload = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "service.name",
                                "value": {"stringValue": "agnetic"},
                            }
                        ]
                    },
                    "scopeSpans": [{"scope": {}, "spans": spans}],
                }
            ]
        }
        url = f"{self._customer_endpoint}/v1/traces"
        self._do_post(url, payload, self._customer_headers)

    def _do_post(self, url, payload, headers):
        try:
            resp = httpx.post(
                url,
                json=payload,
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code >= 300:
                log.warning(
                    "OTEL POST %s returned %s: %s",
                    url,
                    resp.status_code,
                    resp.text[:200],
                )
        except Exception as exc:
            log.warning("OTEL POST %s failed: %s", url, exc)

    def _write_jsonl(self, points):
        try:
            _TELEMETRY_JSONL.parent.mkdir(parents=True, exist_ok=True)
            if _TELEMETRY_JSONL.exists() and _TELEMETRY_JSONL.stat().st_size > _MAX_JSONL_BYTES:
                rotated = _TELEMETRY_JSONL.with_suffix(".jsonl.old")
                _TELEMETRY_JSONL.rename(rotated)
            with _TELEMETRY_JSONL.open("a") as f:
                for p in points:
                    f.write(
                        json.dumps(
                            {
                                "event_type": p.event_type,
                                "timestamp": p.timestamp,
                                "agent_id": p.agent_id,
                                "session_id": p.session_id,
                                "user_id": p.user_id,
                                "attributes": p.attributes,
                                "duration_ms": p.duration_ms,
                            }
                        )
                        + "\n"
                    )
        except OSError as exc:
            log.warning("Failed writing JSONL telemetry: %s", exc)

    def start_periodic_export(self, interval_seconds=60):
        if self._periodic_running:
            return
        self._periodic_running = True
        self._flush_interval = interval_seconds
        self._periodic_event.clear()
        self._periodic_thread = threading.Thread(
            target=self._periodic_loop, daemon=True
        )
        self._periodic_thread.start()
        log.info("Periodic telemetry export started (every %ss)", interval_seconds)

    def _periodic_loop(self):
        while not self._periodic_event.is_set():
            self._periodic_event.wait(timeout=self._flush_interval)
            if self._periodic_event.is_set():
                break
            try:
                self.export()
            except Exception as exc:
                log.warning("Periodic export error: %s", exc)

    def stop_periodic_export(self):
        self._periodic_running = False
        self._periodic_event.set()
        if self._periodic_thread and self._periodic_thread.is_alive():
            self._periodic_thread.join(timeout=5)
        log.info("Periodic telemetry export stopped")

    def get_stats(self):
        with self._lock:
            return dict(self._counter)

    def get_recent(self, limit=100):
        with self._lock:
            return self._buffer[-limit:]

    def export_content(self):
        if not self._customer_endpoint:
            return
        with self._lock:
            messages = list(self._content_buffer)
            self._content_buffer.clear()
        if messages:
            self._export_content_batch(messages)


_exporter_instance: TelemetryExporter | None = None
_exporter_lock = threading.Lock()


def get_telemetry() -> TelemetryExporter:
    global _exporter_instance
    if _exporter_instance is None:
        with _exporter_lock:
            if _exporter_instance is None:
                _exporter_instance = TelemetryExporter()
    return _exporter_instance


def record(event, agent_id="", session_id="", user_id="", attributes=None, duration_ms=None):
    get_telemetry().record_event(event, agent_id, session_id, user_id, attributes, duration_ms)


def export_now():
    get_telemetry().export()
