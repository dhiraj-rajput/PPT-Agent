"""
app/core/mailer.py
--------------------
Async email utilities — equivalent of the Node.js server/utils/mailer.js
but running inside the FastAPI backend via aiosmtplib.

Falls back gracefully (logs a warning) when SMTP is not configured so the
rest of the application still works without email.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from config.settings import settings

logger = logging.getLogger(__name__)


def _is_smtp_configured() -> bool:
    return bool(settings.SMTP_USER and settings.SMTP_PASS)


async def _send(to_email: str, subject: str, html: str) -> None:
    """Send an email. Tries configured port first, then falls back to alternate SMTP port if blocked/timed out."""
    if not _is_smtp_configured():
        logger.warning(
            f"[Mailer] SMTP not configured — skipping email to {to_email}: {subject}"
        )
        return
    try:
        import aiosmtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
        msg["To"] = to_email
        msg.attach(MIMEText(html, "html"))

        env_name = str(getattr(settings, "ENVIRONMENT", "dev")).lower()
        timeout_secs = 5.0 if env_name in ("dev", "development", "local") else 10.0

        primary_port = settings.SMTP_PORT or 465
        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.SMTP_HOST,
                port=primary_port,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASS,
                use_tls=(primary_port == 465),
                start_tls=(primary_port == 587),
                timeout=timeout_secs,
            )
            logger.info(f"[Mailer] Sent '{subject}' to {to_email} (port {primary_port})")
            return
        except Exception as primary_err:
            fallback_port = 587 if primary_port == 465 else 465
            logger.warning(
                f"[Mailer] Primary SMTP attempt failed ({settings.SMTP_HOST}:{primary_port}): {primary_err}. "
                f"Attempting fallback to port {fallback_port}..."
            )
            await aiosmtplib.send(
                msg,
                hostname=settings.SMTP_HOST,
                port=fallback_port,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASS,
                use_tls=(fallback_port == 465),
                start_tls=(fallback_port == 587),
                timeout=timeout_secs,
            )
            logger.info(f"[Mailer] Sent '{subject}' to {to_email} via fallback port {fallback_port}")
    except Exception as exc:
        logger.error(f"[Mailer] Failed to send email to {to_email}: {exc}")


def _shell(heading: str, body_html: str) -> str:
    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto;">
      <h2 style="color:#111827;">{heading}</h2>
      {body_html}
      <p style="color:#9ca3af; font-size: 12px; margin-top: 24px;">
        This is an automated message from OrbitAvanya.
      </p>
    </div>
    """


# ---------------------------------------------------------------------------
# OTP email
# ---------------------------------------------------------------------------

_PURPOSE_COPY = {
    "register": {
        "subject": "Verify your OrbitAvanya account",
        "heading": "Confirm your email",
        "body": "verify your email and finish creating your account",
    },
    "login": {
        "subject": "Your OrbitAvanya sign-in code",
        "heading": "Two-factor verification code",
        "body": "complete your sign-in",
    },
    "reset-password": {
        "subject": "Reset your OrbitAvanya password",
        "heading": "Reset your password",
        "body": "verify it's you before choosing a new password",
    },
    "change-password": {
        "subject": "Confirm your OrbitAvanya password change",
        "heading": "Confirm password change",
        "body": "confirm you want to change your account password",
    },
}


async def send_otp_email(to_email: str, otp: str, purpose: str) -> None:
    copy = _PURPOSE_COPY.get(purpose, _PURPOSE_COPY["login"])
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto;">
      <h2 style="color:#111827;">{copy['heading']}</h2>
      <p style="color:#374151; font-size: 14px;">
        Use the code below to {copy['body']}.
        This code expires in {settings.OTP_TTL_MINUTES} minutes.
      </p>
      <p style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color:#4f46e5; margin: 24px 0;">
        {otp}
      </p>
      <p style="color:#9ca3af; font-size: 12px;">
        If you didn't request this, you can safely ignore this email.
      </p>
    </div>
    """
    try:
        await _send(to_email, copy["subject"], html)
    except Exception as exc:
        logger.warning("🔑 [FALLBACK OTP] Delivery to %s failed: %s. Use OTP code: %s", to_email, exc, otp)


# ---------------------------------------------------------------------------
# Invite
# ---------------------------------------------------------------------------

async def send_invite_email(
    to_email: str,
    invitee_name: str,
    role: str,
    inviter_name: Optional[str],
    temp_password: str,
) -> None:
    login_link = f"{settings.CLIENT_URL}/login"
    html = _shell(
        "You've been invited to OrbitAvanya",
        f"""
      <p style="color:#374151; font-size: 14px;">
        Hi {invitee_name or ''}, {inviter_name or 'A teammate'} has invited you to join the
        OrbitAvanya workspace as <strong>{role}</strong>.
      </p>
      <p style="color:#374151; font-size: 14px;">Your temporary sign-in details:</p>
      <p style="font-size: 14px; color:#111827; background:#f3f4f6; padding: 12px 16px; border-radius: 8px;">
        Email: <strong>{to_email}</strong><br/>
        Temporary password: <strong>{temp_password}</strong>
      </p>
      <p style="color:#374151; font-size: 14px;">
        Please sign in and change your password from Settings as soon as possible.
      </p>
      <p style="margin: 24px 0;">
        <a href="{login_link}" style="background:#4f46e5; color:#fff; padding: 10px 20px; border-radius: 8px; text-decoration:none; font-size: 14px; font-weight: bold;">
          Sign in to OrbitAvanya
        </a>
      </p>
      <p style="color:#9ca3af; font-size: 12px;">Or copy this link: {login_link}</p>
        """,
    )
    await _send(to_email, "You've been invited to join OrbitAvanya", html)


# ---------------------------------------------------------------------------
# Task assignment
# ---------------------------------------------------------------------------

async def send_task_assigned_email(
    to_email: str,
    assignee_name: str,
    task_title: str,
    due: Optional[str],
    priority: str,
    assigner_name: Optional[str],
) -> None:
    tasks_link = f"{settings.CLIENT_URL}/tasks"
    html = _shell(
        "New task assigned to you",
        f"""
      <p style="color:#374151; font-size: 14px;">
        Hi {assignee_name or ''}, {assigner_name or 'a teammate'} assigned you a new task in OrbitAvanya.
      </p>
      <p style="font-size: 14px; color:#111827; background:#f3f4f6; padding: 12px 16px; border-radius: 8px;">
        <strong>{task_title}</strong><br/>
        Due: {due or 'Not set'} &middot; Priority: {priority or 'Medium'}
      </p>
      <p style="margin: 24px 0;">
        <a href="{tasks_link}" style="background:#4f46e5; color:#fff; padding: 10px 20px; border-radius: 8px; text-decoration:none; font-size: 14px; font-weight: bold;">
          View task in OrbitAvanya
        </a>
      </p>
        """,
    )
    await _send(to_email, f"New task assigned: {task_title}", html)


# ---------------------------------------------------------------------------
# Meeting invite
# ---------------------------------------------------------------------------

async def send_meeting_invite_email(
    to_email: str,
    title: str,
    date: str,
    time: str,
    meeting_type: str,
    meeting_link: Optional[str],
    location: Optional[str],
    organizer_name: Optional[str],
) -> None:
    meetings_link = f"{settings.CLIENT_URL}/meetings"
    if meeting_type == "Video Call" and meeting_link:
        join_block = f"""
        <p style="margin: 16px 0;">
          <a href="{meeting_link}" style="background:#4f46e5; color:#fff; padding: 10px 20px; border-radius: 8px; text-decoration:none; font-size: 14px; font-weight: bold;">
            Join Video Call
          </a>
        </p>
        <p style="color:#9ca3af; font-size: 12px;">Or copy this link: {meeting_link}</p>
        """
    else:
        join_block = f'<p style="color:#374151; font-size: 14px;">Location: {location or "To be confirmed"}</p>'

    html = _shell(
        "Meeting invitation",
        f"""
      <p style="color:#374151; font-size: 14px;">
        {organizer_name or 'A teammate'} scheduled a meeting with you on OrbitAvanya.
      </p>
      <p style="font-size: 14px; color:#111827; background:#f3f4f6; padding: 12px 16px; border-radius: 8px;">
        <strong>{title}</strong><br/>
        {date} at {time}
      </p>
      {join_block}
      <p style="color:#9ca3af; font-size: 12px;">Full details: {meetings_link}</p>
        """,
    )
    await _send(to_email, f"Meeting invite: {title} — {date} {time}", html)


# ---------------------------------------------------------------------------
# Meeting cancellation
# ---------------------------------------------------------------------------

async def send_meeting_cancelled_email(
    to_email: str,
    title: str,
    date: str,
    time: str,
    organizer_name: Optional[str],
) -> None:
    html = _shell(
        "Meeting cancelled",
        f"""
      <p style="color:#374151; font-size: 14px;">
        {organizer_name or 'A teammate'} has cancelled the following meeting on OrbitAvanya:
      </p>
      <p style="font-size: 14px; color:#111827; background:#f3f4f6; padding: 12px 16px; border-radius: 8px;">
        <strong>{title}</strong><br/>
        Was scheduled for {date} at {time}
      </p>
      <p style="color:#374151; font-size: 14px;">No action is needed on your end.</p>
        """,
    )
    await _send(to_email, f"Meeting cancelled: {title} — {date} {time}", html)


# ---------------------------------------------------------------------------
# Company custom email with attachments
# ---------------------------------------------------------------------------

def _read_file_sync(file_path: str) -> bytes:
    with open(file_path, "rb") as f:
        return f.read()


async def send_company_email_with_attachments(
    to_email: str,
    subject: str,
    body_html: str,
    attachments: Optional[list[dict]] = None
) -> None:
    """Send a custom email to a company with optional attachments (non-blocking file reads)."""
    if attachments is None:
        attachments = []
    if not _is_smtp_configured():
        logger.warning(
            f"[Mailer] SMTP not configured — skipping email to {to_email}: {subject}"
        )
        return
    try:
        import aiosmtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.application import MIMEApplication

        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
        msg["To"] = to_email

        # Attach text/html part
        msg.attach(MIMEText(body_html, "html"))

        if attachments:
            for attach in attachments:
                path = attach.get("path")
                filename = attach.get("filename")
                if path and os.path.exists(path):
                    content = await asyncio.to_thread(_read_file_sync, path)
                    part = MIMEApplication(content, Name=filename)
                    part['Content-Disposition'] = f'attachment; filename="{filename}"'
                    msg.attach(part)
                else:
                    logger.warning(f"[Mailer] Attachment file not found: {path}")

        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASS,
            use_tls=(settings.SMTP_PORT == 465),
            start_tls=(settings.SMTP_PORT == 587),
        )
        logger.info(f"[Mailer] Sent '{subject}' to {to_email} with attachments")
    except Exception as exc:
        logger.error(f"[Mailer] Failed to send email to {to_email}: {exc}")
        raise exc
