"""Notifications: console, email (SMTP), Discord/Slack webhooks.

All payloads pass through secret redaction. Notifications never include API
secrets or detailed account identifiers.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Protocol, runtime_checkable

import httpx

from app.config import Settings
from app.logging import get_logger, log_event
from app.utils.redaction import redact

logger = get_logger("notifications")


@runtime_checkable
class NotificationChannel(Protocol):
    name: str

    async def send(self, subject: str, body: str) -> None: ...


class ConsoleChannel:
    name = "console"

    async def send(self, subject: str, body: str) -> None:
        log_event(logger, "notification", f"[NOTIFY] {subject}: {body}")


class EmailChannel:
    name = "email"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, subject: str, body: str) -> None:
        s = self.settings

        def _send() -> None:
            message = EmailMessage()
            message["Subject"] = f"[AegisInvest] {subject}"
            message["From"] = s.smtp_username or "aegis@localhost"
            message["To"] = s.notify_email_to
            message.set_content(body)
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
                smtp.starttls()
                if s.smtp_username:
                    smtp.login(s.smtp_username, s.smtp_password.get_secret_value())
                smtp.send_message(message)

        await asyncio.to_thread(_send)


class WebhookChannel:
    def __init__(self, name: str, url: str, payload_key: str) -> None:
        self.name = name
        self._url = url
        self._payload_key = payload_key  # "content" (Discord) or "text" (Slack)

    async def send(self, subject: str, body: str) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(self._url, json={self._payload_key: f"**{subject}**\n{body}"})


class NotificationService:
    def __init__(self, channels: list[NotificationChannel]) -> None:
        self.channels = channels

    async def send(self, subject: str, body: str) -> None:
        subject = str(redact(subject))
        body = str(redact(body))
        for channel in self.channels:
            try:
                await channel.send(subject, body)
            except Exception:
                logger.warning(
                    "notification channel failed",
                    extra={"channel": channel.name},
                    exc_info=True,
                )


def build_notification_service(settings: Settings) -> NotificationService:
    channels: list[NotificationChannel] = []
    if settings.notify_console:
        channels.append(ConsoleChannel())
    if settings.notify_email_enabled and settings.smtp_host and settings.notify_email_to:
        channels.append(EmailChannel(settings))
    discord_url = settings.discord_webhook_url.get_secret_value()
    if discord_url:
        channels.append(WebhookChannel("discord", discord_url, "content"))
    slack_url = settings.slack_webhook_url.get_secret_value()
    if slack_url:
        channels.append(WebhookChannel("slack", slack_url, "text"))
    if not channels:
        channels.append(ConsoleChannel())
    return NotificationService(channels)
