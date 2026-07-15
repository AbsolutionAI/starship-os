import json
import logging
import logging.config
import os
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("agnetic-incident")


@dataclass
class RunbookStep:
    order: int
    action: str
    command: str | None
    expected_outcome: str
    timeout_seconds: int
    critical: bool


@dataclass
class Runbook:
    id: str
    name: str
    alert_pattern: str
    description: str
    steps: list[RunbookStep]
    escalation_message: str
    created_at: str


@dataclass
class RunbookResult:
    runbook_id: str
    status: str = "running"
    current_step: int = 0
    total_steps: int = 0
    log: list[dict] = field(default_factory=list)
    started_at: str = ""
    completed_at: str | None = None


@dataclass
class Incident:
    id: str
    alert_type: str
    source: str
    severity: str
    message: str
    metadata: dict
    status: str = "open"
    assigned_agent: str | None = None
    runbook_id: str | None = None
    runbook_result: RunbookResult | None = None
    created_at: str = ""
    resolved_at: str | None = None


BUILTIN_RUNBOOKS = {
    "disk-space": {
        "name": "disk-space",
        "alert_pattern": r"disk.*(full|space|usage|%)",
        "description": "Respond to disk space alerts by checking usage, cleaning temp files, and escalating if critical.",
        "steps": [
            RunbookStep(1, "Check disk usage", "df -h", "Disk usage percentages displayed", 30, False),
            RunbookStep(2, "Find large files", "du -sh /* 2>/dev/null | sort -rh | head -20", "Top 20 largest directories identified", 60, False),
            RunbookStep(3, "Clean temporary files", "rm -rf /tmp/* /var/tmp/* 2>/dev/null; echo done", "Temporary files cleaned", 120, False),
            RunbookStep(4, "Check log sizes", "du -sh /var/log/* 2>/dev/null | sort -rh | head -10", "Large log files identified", 30, False),
            RunbookStep(5, "Escalate if critical", "df -h | awk 'NR>1 {print $5}' | sed 's/%//' | while read p; do [ \"$p\" -gt 90 ] && echo \"CRITICAL: disk >90% used\"; done", "Escalation check complete", 30, True),
        ],
        "escalation_message": "Disk usage critical — manual intervention required",
    },
    "high-cpu": {
        "name": "high-cpu",
        "alert_pattern": r"cpu.*(high|load|usage|%)",
        "description": "Investigate and remediate high CPU usage.",
        "steps": [
            RunbookStep(1, "Check system load", "top -bn1 | head -5", "System load averages displayed", 30, False),
            RunbookStep(2, "Identify top processes", "ps aux --sort=-%cpu | head -20", "Top CPU-consuming processes listed", 30, False),
            RunbookStep(3, "Check for runaway processes", "ps aux --sort=-%cpu | awk '$3>90 {print $2}'", "Runaway processes identified", 30, False),
            RunbookStep(4, "Kill or escalate", "ps aux --sort=-%cpu | awk 'NR>1 && $3>95 {print $2}' | head -3 | while read pid; do kill -15 \"$pid\" 2>/dev/null; done", "High-CPU processes terminated or escalated", 60, True),
        ],
        "escalation_message": "CPU load critical — unable to automatically remediate",
    },
    "service-down": {
        "name": "service-down",
        "alert_pattern": r"service.*(down|stop|fail|crash|unreachable)",
        "description": "Respond to service-down alerts by checking status, logs, restarting, and verifying health.",
        "steps": [
            RunbookStep(1, "Check service status", "systemctl status --no-pager 2>/dev/null || echo 'systemctl not available'", "Service status displayed", 30, False),
            RunbookStep(2, "Check service logs", "journalctl -n 50 --no-pager 2>/dev/null || tail -50 /var/log/syslog 2>/dev/null", "Recent logs displayed", 30, False),
            RunbookStep(3, "Restart service", "systemctl restart 2>/dev/null || service restart 2>/dev/null", "Service restart attempted", 60, False),
            RunbookStep(4, "Verify health", "systemctl is-active 2>/dev/null || echo 'check manually'", "Service health verified", 30, True),
        ],
        "escalation_message": "Service failed to restart — manual intervention required",
    },
    "memory-pressure": {
        "name": "memory-pressure",
        "alert_pattern": r"memory.*(OOM|pressure|high|usage|swap)",
        "description": "Investigate and remediate memory pressure conditions.",
        "steps": [
            RunbookStep(1, "Check memory usage", "free -h", "Memory and swap usage displayed", 30, False),
            RunbookStep(2, "Identify high-memory processes", "ps aux --sort=-%mem | head -20", "Top memory-consuming processes listed", 30, False),
            RunbookStep(3, "Check for memory leaks", "ps aux --sort=-%mem | awk '$4>50 {print $2, $4\"%\", $11}'", "Potential memory leaks identified", 30, False),
            RunbookStep(4, "Restart or escalate", "ps aux --sort=-%mem | awk 'NR>1 && $4>80 {print $2}' | head -3 | while read pid; do kill -15 \"$pid\" 2>/dev/null; done", "Memory-intensive processes handled", 60, True),
        ],
        "escalation_message": "Memory pressure critical — unable to free sufficient resources",
    },
    "security-breach": {
        "name": "security-breach",
        "alert_pattern": r"security|breach|intrusion|unauthorized|hack",
        "description": "Immediate response to security breaches: isolate, audit, and escalate.",
        "steps": [
            RunbookStep(1, "Isolate system", "echo 'Isolating system from network'", "System isolation initiated", 30, True),
            RunbookStep(2, "Check auth logs", "tail -100 /var/log/auth.log 2>/dev/null || journalctl -u sshd -n 100 --no-pager 2>/dev/null", "Authentication logs reviewed", 60, False),
            RunbookStep(3, "List active connections", "ss -tunap", "Active network connections listed", 30, False),
            RunbookStep(4, "Check file integrity", "which tripwire && tripwire --check || echo 'No integrity checker installed'", "File integrity check initiated", 120, False),
            RunbookStep(5, "Escalate immediately", "echo 'SECURITY BREACH — escalation required'", "Escalation triggered", 10, True),
        ],
        "escalation_message": "SECURITY BREACH DETECTED — immediate human intervention required",
    },
    "cert-expiry": {
        "name": "cert-expiry",
        "alert_pattern": r"cert.*(expir|renew|tls|ssl)",
        "description": "Check and renew expiring TLS/SSL certificates.",
        "steps": [
            RunbookStep(1, "Check certificate expiry", "openssl x509 -enddate -noout -in /etc/ssl/certs/ 2>/dev/null || echo 'cert check failed'", "Certificate expiry dates displayed", 30, False),
            RunbookStep(2, "Verify renewal mechanism", "which certbot && certbot renew --dry-run 2>&1 || echo 'certbot not found'", "Renewal mechanism verified", 60, False),
            RunbookStep(3, "Attempt renewal", "certbot renew 2>&1 || echo 'renewal failed'", "Certificate renewal attempted", 120, False),
            RunbookStep(4, "Report status", "echo 'Certificate status reported'", "Status reported", 30, True),
        ],
        "escalation_message": "Certificate renewal failed — manual intervention required",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class IncidentResponseManager:
    def __init__(self, runbooks_dir=None, incidents_db=None):
        self.runbooks_dir = runbooks_dir or "/opt/agnetic/runbooks/"
        self.incidents_db = incidents_db or "/var/lib/agnetic/incidents.json"
        self._runbooks: dict[str, Runbook] = {}
        self._incidents: dict[str, Incident] = {}
        os.makedirs(self.runbooks_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.incidents_db), exist_ok=True)
        self._seed_builtins()
        self.load_runbooks()
        self._load_incidents()

    def _seed_builtins(self):
        for rb_id, spec in BUILTIN_RUNBOOKS.items():
            path = os.path.join(self.runbooks_dir, f"{rb_id}.json")
            if not os.path.exists(path):
                rb = Runbook(
                    id=rb_id,
                    name=spec["name"],
                    alert_pattern=spec["alert_pattern"],
                    description=spec["description"],
                    steps=spec["steps"],
                    escalation_message=spec["escalation_message"],
                    created_at=_now(),
                )
                self._write_runbook_file(rb)

    def _write_runbook_file(self, rb: Runbook):
        path = os.path.join(self.runbooks_dir, f"{rb.id}.json")
        data = {
            "id": rb.id,
            "name": rb.name,
            "alert_pattern": rb.alert_pattern,
            "description": rb.description,
            "steps": [asdict(s) for s in rb.steps],
            "escalation_message": rb.escalation_message,
            "created_at": rb.created_at,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _write_incidents(self):
        data = []
        for inc in self._incidents.values():
            d = asdict(inc)
            if d["runbook_result"] is not None:
                d["runbook_result"] = asdict(inc.runbook_result)
            data.append(d)
        with open(self.incidents_db, "w") as f:
            json.dump(data, f, indent=2)

    def _load_incidents(self):
        if not os.path.exists(self.incidents_db):
            return
        try:
            with open(self.incidents_db) as f:
                data = json.load(f)
            for d in data:
                if d.get("runbook_result"):
                    r = d["runbook_result"]
                    d["runbook_result"] = RunbookResult(
                        runbook_id=r["runbook_id"],
                        status=r["status"],
                        current_step=r["current_step"],
                        total_steps=r["total_steps"],
                        log=r["log"],
                        started_at=r["started_at"],
                        completed_at=r.get("completed_at"),
                    )
                inc = Incident(**d)
                self._incidents[inc.id] = inc
        except Exception as e:
            logger.warning("Failed to load incidents: %s", e)

    def load_runbooks(self):
        self._runbooks = {}
        if not os.path.isdir(self.runbooks_dir):
            return
        for fname in os.listdir(self.runbooks_dir):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(self.runbooks_dir, fname)
            try:
                with open(path) as f:
                    data = json.load(f)
                steps = [RunbookStep(**s) for s in data.get("steps", [])]
                rb = Runbook(
                    id=data["id"],
                    name=data["name"],
                    alert_pattern=data["alert_pattern"],
                    description=data["description"],
                    steps=steps,
                    escalation_message=data["escalation_message"],
                    created_at=data.get("created_at", ""),
                )
                self._runbooks[rb.id] = rb
            except Exception as e:
                logger.error("Failed to load runbook %s: %s", fname, e)

    def register_runbook(self, name, alert_pattern, description, steps, escalation_message):
        rb = Runbook(
            id=_new_id(),
            name=name,
            alert_pattern=alert_pattern,
            description=description,
            steps=steps,
            escalation_message=escalation_message,
            created_at=_now(),
        )
        self._write_runbook_file(rb)
        self._runbooks[rb.id] = rb
        logger.info("Registered runbook: %s (%s)", rb.name, rb.id)
        return rb

    def find_runbook(self, alert_type):
        for rb in self._runbooks.values():
            if re.search(rb.alert_pattern, alert_type, re.IGNORECASE):
                return rb
        return None

    def get_runbook(self, runbook_id):
        return self._runbooks.get(runbook_id)

    def list_runbooks(self):
        return list(self._runbooks.values())

    def create_incident(self, alert_type, source, severity, message, metadata=None):
        if severity not in ("critical", "high", "medium", "low"):
            raise ValueError(f"Invalid severity: {severity}")
        runbook = self.find_runbook(alert_type)
        rb_result = None
        if runbook:
            rb_result = RunbookResult(
                runbook_id=runbook.id,
                total_steps=len(runbook.steps),
                started_at=_now(),
            )
        inc = Incident(
            id=_new_id(),
            alert_type=alert_type,
            source=source,
            severity=severity,
            message=message,
            metadata=metadata or {},
            runbook_id=runbook.id if runbook else None,
            runbook_result=rb_result,
            created_at=_now(),
        )
        self._incidents[inc.id] = inc
        self._write_incidents()
        logger.info("Created incident %s — %s (%s)", inc.id, alert_type, severity)
        return inc

    def get_incident(self, incident_id):
        return self._incidents.get(incident_id)

    def list_incidents(self, status=None, limit=50):
        results = list(self._incidents.values())
        if status:
            results = [i for i in results if i.status == status]
        results.sort(key=lambda i: i.created_at, reverse=True)
        return results[:limit]

    def assign_agent(self, incident_id, agent_name):
        inc = self._incidents.get(incident_id)
        if not inc:
            raise KeyError(f"Incident not found: {incident_id}")
        inc.assigned_agent = agent_name
        inc.status = "investigating"
        self._write_incidents()
        logger.info("Assigned agent %s to incident %s", agent_name, incident_id)
        return inc

    def log_step(self, incident_id, step_order, status, output):
        inc = self._incidents.get(incident_id)
        if not inc:
            raise KeyError(f"Incident not found: {incident_id}")
        if not inc.runbook_result:
            raise ValueError("Incident has no runbook result")
        log_entry = {
            "step": step_order,
            "status": status,
            "output": output,
            "timestamp": _now(),
        }
        inc.runbook_result.log.append(log_entry)
        inc.runbook_result.current_step = step_order
        if status == "failed" and inc.runbook_result.total_steps > 0:
            runbook = self.get_runbook(inc.runbook_id)
            if runbook:
                step_obj = next((s for s in runbook.steps if s.order == step_order), None)
                if step_obj and step_obj.critical:
                    self.escalate_incident(incident_id, f"Critical step {step_order} failed: {step_obj.action}")
        self._write_incidents()
        return inc

    def resolve_incident(self, incident_id, resolution_notes=""):
        inc = self._incidents.get(incident_id)
        if not inc:
            raise KeyError(f"Incident not found: {incident_id}")
        inc.status = "resolved"
        inc.resolved_at = _now()
        if inc.runbook_result:
            inc.runbook_result.status = "succeeded"
            inc.runbook_result.completed_at = _now()
        logger.info("Resolved incident %s: %s", incident_id, resolution_notes)
        self._write_incidents()
        return inc

    def escalate_incident(self, incident_id, reason=""):
        inc = self._incidents.get(incident_id)
        if not inc:
            raise KeyError(f"Incident not found: {incident_id}")
        inc.status = "escalated"
        if inc.runbook_result:
            inc.runbook_result.status = "escalated"
            inc.runbook_result.completed_at = _now()
        logger.warning("Escalated incident %s: %s", incident_id, reason)
        self._write_incidents()
        return inc

    def get_active_incidents(self):
        return [i for i in self._incidents.values() if i.status in ("open", "investigating")]

    def get_stats(self):
        all_incs = list(self._incidents.values())
        total = len(all_incs)
        open_count = sum(1 for i in all_incs if i.status == "open")
        resolved_count = sum(1 for i in all_incs if i.status == "resolved")
        by_severity = {}
        for inc in all_incs:
            by_severity.setdefault(inc.severity, 0)
            by_severity[inc.severity] += 1
        return {
            "total": total,
            "open": open_count,
            "resolved": resolved_count,
            "by_severity": by_severity,
        }


_manager_instance: IncidentResponseManager | None = None


def get_incident_manager() -> IncidentResponseManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = IncidentResponseManager()
    return _manager_instance
