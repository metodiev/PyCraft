"""Outbound email.

Two backends: ``console`` (development default) logs the message instead of
sending it, and ``smtp`` delivers real mail. Keeping the console backend as the
default means password reset is fully testable locally with no mail server, and
a fresh checkout can never accidentally email a real address.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage

from app.core.config import Settings

logger = logging.getLogger(__name__)


class EmailSender:
    """Sends transactional email according to the configured backend."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send_password_reset(self, *, to: str, display_name: str, reset_url: str) -> None:
        minutes = self._settings.password_reset_ttl_minutes
        text = (
            f"Hi {display_name},\n\n"
            "Someone requested a password reset for your PyCraft account.\n\n"
            f"Reset your password (link valid for {minutes} minutes):\n{reset_url}\n\n"
            "If this wasn't you, you can safely ignore this email — your password "
            "will not change.\n\n"
            "— PyCraft"
        )
        await self._send(
            to=to,
            subject="Reset your PyCraft password",
            text=text,
        )

    async def _send(self, *, to: str, subject: str, text: str) -> None:
        if self._settings.email_backend == "smtp":
            await self._send_smtp(to=to, subject=subject, text=text)
        else:
            # Logged at WARNING so it is visible with default logging config.
            logger.warning(
                "\n"
                "─────────────── PyCraft email (console backend) ───────────────\n"
                "To:      %s\n"
                "Subject: %s\n\n"
                "%s\n"
                "───────────────────────────────────────────────────────────────\n"
                "Set PYCRAFT_EMAIL_BACKEND=smtp to deliver real mail.",
                to,
                subject,
                text,
            )

    async def _send_smtp(self, *, to: str, subject: str, text: str) -> None:
        import aiosmtplib

        message = EmailMessage()
        message["From"] = self._settings.smtp_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)

        try:
            await aiosmtplib.send(
                message,
                hostname=self._settings.smtp_host,
                port=self._settings.smtp_port,
                username=self._settings.smtp_username or None,
                password=self._settings.smtp_password or None,
                start_tls=self._settings.smtp_starttls,
                timeout=15,
            )
        except Exception:
            # The caller has already decided to report success so that account
            # existence is not disclosed; log loudly for operators instead.
            logger.exception("Failed to send email to %s", to)
