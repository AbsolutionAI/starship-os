import json
import logging
import os
import re
import smtplib
import ssl
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional
import httpx

log = logging.getLogger("agnetic-email")

SMTP_DEFAULTS = {
    "host": os.environ.get("AGNETIC_EMAIL_SMTP_HOST", ""),
    "port": int(os.environ.get("AGNETIC_EMAIL_SMTP_PORT", "587")),
    "user": os.environ.get("AGNETIC_EMAIL_SMTP_USER", ""),
    "password": os.environ.get("AGNETIC_EMAIL_SMTP_PASSWORD", ""),
    "use_tls": os.environ.get("AGNETIC_EMAIL_SMTP_TLS", "true").lower() == "true",
}

MAILCHAIN_DEFAULTS = {
    "api_url": os.environ.get("AGNETIC_MAILCHAIN_API_URL", "https://api.mailchain.dev"),
    "wallet_address": os.environ.get("AGNETIC_MAILCHAIN_WALLET", ""),
    "private_key": os.environ.get("AGNETIC_MAILCHAIN_PRIVATE_KEY", ""),
    "protocol": os.environ.get("AGNETIC_MAILCHAIN_PROTOCOL", "ethereum"),
    "network": os.environ.get("AGNETIC_MAILCHAIN_NETWORK", "mainnet"),
}

AGENT_ADDRESSES_FILE = os.environ.get(
    "AGNETIC_EMAIL_ADDRESSES",
    "/var/lib/agnetic/agent_email_addresses.json",
)


@dataclass
class EmailMessage:
    id: str
    from_address: str
    to_address: str
    subject: str
    body_plain: str
    body_html: str = ""
    timestamp: str = ""
    status: str = "sent"
    error: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class AgentAddress:
    agent_name: str
    email_address: str
    smtp_enabled: bool = True
    mailchain_enabled: bool = False
    mailchain_protocol: str = "ethereum"
    aliases: list = field(default_factory=list)
    created: str = ""

    def to_dict(self):
        return asdict(self)


class AgentEmailService:
    """Dual-mode agent email service (SMTP direct + Mailchain Web3)."""

    def __init__(self):
        self._smtp_config = dict(SMTP_DEFAULTS)
        self._mailchain_config = dict(MAILCHAIN_DEFAULTS)
        self._addresses: dict[str, AgentAddress] = {}
        self._addresses_path = Path(AGENT_ADDRESSES_FILE)
        self._load_addresses()

    def _load_addresses(self):
        if not self._addresses_path.exists():
            return
        try:
            data = json.loads(self._addresses_path.read_text())
            for entry in data.get("addresses", []):
                addr = AgentAddress(**entry)
                self._addresses[addr.agent_name] = addr
            log.info("Loaded %d agent email addresses", len(self._addresses))
        except Exception as e:
            log.warning("Failed to load email addresses: %s", e)

    def _save_addresses(self):
        try:
            self._addresses_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "addresses": [a.to_dict() for a in self._addresses.values()],
                "updated": datetime.now(timezone.utc).isoformat(),
            }
            self._addresses_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.warning("Failed to save email addresses: %s", e)

    def register_agent_address(
        self,
        agent_name: str,
        email_address: str,
        smtp_enabled: bool = True,
        mailchain_enabled: bool = False,
        mailchain_protocol: str = "ethereum",
        aliases: list = None,
    ) -> AgentAddress:
        addr = AgentAddress(
            agent_name=agent_name,
            email_address=email_address,
            smtp_enabled=smtp_enabled,
            mailchain_enabled=mailchain_enabled,
            mailchain_protocol=mailchain_protocol,
            aliases=aliases or [],
            created=datetime.now(timezone.utc).isoformat(),
        )
        self._addresses[agent_name] = addr
        self._save_addresses()
        log.info("Registered email address '%s' for agent '%s'", email_address, agent_name)
        return addr

    def get_agent_address(self, agent_name: str) -> Optional[AgentAddress]:
        return self._addresses.get(agent_name)

    def list_addresses(self) -> list[AgentAddress]:
        return list(self._addresses.values())

    def remove_address(self, agent_name: str) -> bool:
        if agent_name in self._addresses:
            del self._addresses[agent_name]
            self._save_addresses()
            return True
        return False

    async def send_email(
        self,
        to_address: str,
        subject: str,
        body: str,
        from_address: str = "",
        html_body: str = "",
        mode: str = "smtp",
        cc: list = None,
        bcc: list = None,
    ) -> EmailMessage:
        msg = EmailMessage(
            id=str(uuid.uuid4()),
            from_address=from_address,
            to_address=to_address,
            subject=subject,
            body_plain=body,
            body_html=html_body,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        if mode == "mailchain" and self._mailchain_config.get("wallet_address"):
            result = await self._send_via_mailchain(msg, cc=cc, bcc=bcc)
        else:
            result = await self._send_via_smtp(msg, cc=cc, bcc=bcc)

        return result

    async def _send_via_smtp(
        self, msg: EmailMessage, cc: list = None, bcc: list = None
    ) -> EmailMessage:
        cfg = self._smtp_config
        if not cfg.get("host"):
            msg.status = "failed"
            msg.error = "SMTP not configured (set AGNETIC_EMAIL_SMTP_HOST)"
            log.warning(msg.error)
            return msg

        try:
            mime = MIMEMultipart("alternative")
            mime["Subject"] = msg.subject
            mime["From"] = msg.from_address or cfg.get("user", "agent@agnetic.local")
            mime["To"] = msg.to_address
            if cc:
                mime["Cc"] = ", ".join(cc)
            if bcc:
                mime["Bcc"] = ", ".join(bcc)

            mime.attach(MIMEText(msg.body_plain, "plain"))
            if msg.body_html:
                mime.attach(MIMEText(msg.body_html, "html"))

            ctx = ssl.create_default_context()
            all_recipients = [msg.to_address] + (cc or []) + (bcc or [])

            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as server:
                if cfg.get("use_tls", True):
                    server.starttls(context=ctx)
                if cfg.get("user") and cfg.get("password"):
                    server.login(cfg["user"], cfg["password"])
                server.sendmail(
                    cfg.get("user", "agent@agnetic.local"),
                    all_recipients,
                    mime.as_string(),
                )

            msg.status = "sent"
            log.info("Email sent via SMTP: %s -> %s", msg.from_address, msg.to_address)
        except smtplib.SMTPException as e:
            msg.status = "failed"
            msg.error = f"SMTP error: {e}"
            log.warning("SMTP send failed: %s", e)
        except Exception as e:
            msg.status = "failed"
            msg.error = f"Send error: {e}"
            log.warning("Email send failed: %s", e)

        return msg

    async def _send_via_mailchain(
        self, msg: EmailMessage, cc: list = None, bcc: list = None
    ) -> EmailMessage:
        cfg = self._mailchain_config
        if not cfg.get("wallet_address"):
            msg.status = "failed"
            msg.error = "Mailchain not configured (set AGNETIC_MAILCHAIN_WALLET)"
            return msg

        try:
            payload = {
                "from": msg.from_address or cfg["wallet_address"],
                "to": [msg.to_address],
                "subject": msg.subject,
                "body": msg.body_plain,
                "protocol": cfg.get("protocol", "ethereum"),
                "network": cfg.get("network", "mainnet"),
            }
            if cc:
                payload["cc"] = cc
            if bcc:
                payload["bcc"] = bcc

            headers = {"Content-Type": "application/json"}
            if cfg.get("private_key"):
                headers["Authorization"] = f"Bearer {cfg['private_key']}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{cfg['api_url']}/messages",
                    json=payload,
                    headers=headers,
                )

            if resp.status_code in (200, 201):
                msg.status = "sent"
                log.info("Email sent via Mailchain: %s -> %s", msg.from_address, msg.to_address)
            else:
                msg.status = "failed"
                msg.error = f"Mailchain API error: {resp.status_code} {resp.text[:200]}"
                log.warning("Mailchain send failed: %s %s", resp.status_code, resp.text[:200])

        except httpx.RequestError as e:
            msg.status = "failed"
            msg.error = f"Mailchain network error: {e}"
            log.warning("Mailchain request failed: %s", e)
        except Exception as e:
            msg.status = "failed"
            msg.error = f"Mailchain error: {e}"
            log.warning("Mailchain send error: %s", e)

        return msg

    async def list_inbox(
        self, address: str = "", limit: int = 50, mode: str = "mailchain"
    ) -> list[EmailMessage]:
        if mode == "mailchain" and self._mailchain_config.get("wallet_address"):
            return await self._mailchain_inbox(address or self._mailchain_config["wallet_address"], limit)
        return []

    async def _mailchain_inbox(self, address: str, limit: int = 50) -> list[EmailMessage]:
        cfg = self._mailchain_config
        messages = []
        try:
            headers = {"Content-Type": "application/json"}
            if cfg.get("private_key"):
                headers["Authorization"] = f"Bearer {cfg['private_key']}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{cfg['api_url']}/inbox/{address}",
                    params={"limit": limit, "protocol": cfg.get("protocol", "ethereum")},
                    headers=headers,
                )

            if resp.status_code == 200:
                data = resp.json()
                for entry in data.get("messages", []):
                    messages.append(EmailMessage(
                        id=entry.get("id", str(uuid.uuid4())),
                        from_address=entry.get("from", ""),
                        to_address=entry.get("to", ""),
                        subject=entry.get("subject", "(no subject)"),
                        body_plain=entry.get("body", entry.get("body_plain", "")),
                        body_html=entry.get("body_html", ""),
                        timestamp=entry.get("timestamp", datetime.now(timezone.utc).isoformat()),
                        status="received",
                    ))
                log.info("Fetched %d messages from Mailchain inbox", len(messages))
            else:
                log.warning("Mailchain inbox fetch failed: %s %s", resp.status_code, resp.text[:200])

        except Exception as e:
            log.warning("Mailchain inbox error: %s", e)

        return messages


_email_service = AgentEmailService()


def get_email_service() -> AgentEmailService:
    return _email_service
