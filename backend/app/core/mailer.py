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
import html as _html
import logging

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
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        import aiosmtplib

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
        logger.error("Failed to deliver security OTP email to %s: %s", to_email, exc)


# ---------------------------------------------------------------------------
# Invite
# ---------------------------------------------------------------------------

async def send_invite_email(
    to_email: str,
    invitee_name: str,
    role: str,
    inviter_name: str | None,
    temp_password: str,
) -> None:
    login_link = f"{settings.CLIENT_URL}/login"
    # HTML-escape all user-controlled inputs to prevent XSS in email clients
    safe_name = _html.escape(invitee_name or "")
    safe_inviter = _html.escape(inviter_name or "A teammate")
    safe_role = _html.escape(role or "")
    safe_email = _html.escape(to_email or "")
    html = _shell(
        "You've been invited to OrbitAvanya",
        f"""
      <p style="color:#374151; font-size: 14px;">
        Hi {safe_name}, {safe_inviter} has invited you to join the
        OrbitAvanya workspace as <strong>{safe_role}</strong>.
      </p>
      <p style="color:#374151; font-size: 14px;">Your temporary sign-in details:</p>
      <p style="font-size: 14px; color:#111827; background:#f3f4f6; padding: 12px 16px; border-radius: 8px;">
        Email: <strong>{safe_email}</strong><br/>
        Temporary password: <strong>{_html.escape(temp_password)}</strong>
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
    due: str | None,
    priority: str,
    assigner_name: str | None,
) -> None:
    tasks_link = f"{settings.CLIENT_URL}/tasks"
    # HTML-escape all user-controlled inputs
    safe_assignee = _html.escape(assignee_name or "")
    safe_assigner = _html.escape(assigner_name or "a teammate")
    safe_title = _html.escape(task_title or "")
    safe_due = _html.escape(due or "Not set")
    safe_priority = _html.escape(priority or "Medium")
    html = _shell(
        "New task assigned to you",
        f"""
      <p style="color:#374151; font-size: 14px;">
        Hi {safe_assignee}, {safe_assigner} assigned you a new task in OrbitAvanya.
      </p>
      <p style="font-size: 14px; color:#111827; background:#f3f4f6; padding: 12px 16px; border-radius: 8px;">
        <strong>{safe_title}</strong><br/>
        Due: {safe_due} &middot; Priority: {safe_priority}
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
    meeting_link: str | None,
    location: str | None,
    organizer_name: str | None,
) -> None:
    meetings_link = f"{settings.CLIENT_URL}/meetings"
    # HTML-escape user-controlled values
    safe_title = _html.escape(title or "")
    safe_date = _html.escape(date or "")
    safe_time = _html.escape(time or "")
    safe_organizer = _html.escape(organizer_name or "A teammate")
    safe_location = _html.escape(location or "To be confirmed")
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
        join_block = f'<p style="color:#374151; font-size: 14px;">Location: {safe_location}</p>'

    html = _shell(
        "Meeting invitation",
        f"""
      <p style="color:#374151; font-size: 14px;">
        {safe_organizer} scheduled a meeting with you on OrbitAvanya.
      </p>
      <p style="font-size: 14px; color:#111827; background:#f3f4f6; padding: 12px 16px; border-radius: 8px;">
        <strong>{safe_title}</strong><br/>
        {safe_date} at {safe_time}
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
    organizer_name: str | None,
) -> None:
    safe_org = _html.escape(organizer_name or "A teammate")
    safe_title = _html.escape(title or "Meeting")
    safe_date = _html.escape(date or "")
    safe_time = _html.escape(time or "")
    html = _shell(
        "Meeting cancelled",
        f"""
      <p style="color:#374151; font-size: 14px;">
        {safe_org} has cancelled the following meeting on OrbitAvanya:
      </p>
      <p style="font-size: 14px; color:#111827; background:#f3f4f6; padding: 12px 16px; border-radius: 8px;">
        <strong>{safe_title}</strong><br/>
        Was scheduled for {safe_date} at {safe_time}
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
    attachments: list[dict[str, str]] | None = None,
) -> None:
    """Sends a transactional email with optional file attachments (e.g. proposals, reports)."""
    if not settings.SMTP_HOST or not settings.SMTP_USER:
        logger.info(f"[Mailer:MOCK] send_company_email_with_attachments to={to_email} subject='{subject}'")
        return

    try:
        from email.mime.application import MIMEApplication
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from pathlib import Path

        import aiosmtplib

        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
        msg["To"] = to_email

        # Attach text/html part
        msg.attach(MIMEText(body_html, "html"))

        if attachments:
            project_root = Path(__file__).resolve().parent.parent.parent
            for attach in attachments:
                raw_path = attach.get("path")
                filename = attach.get("filename")
                if raw_path:
                    p = Path(raw_path).resolve()
                    # Security check: must exist and be within the project directory
                    if p.exists() and (p.is_relative_to(project_root) or p.is_relative_to(Path(settings.UPLOAD_DIR).resolve())):
                        content = await asyncio.to_thread(_read_file_sync, str(p))
                        part = MIMEApplication(content, Name=filename or p.name)
                        part['Content-Disposition'] = f'attachment; filename="{filename or p.name}"'
                        msg.attach(part)
                    else:
                        logger.warning(f"[Mailer] Unauthorized or missing attachment file path: {raw_path}")

        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASS,
            use_tls=(settings.SMTP_PORT == 465),
            start_tls=(settings.SMTP_PORT == 587),
            timeout=30,
        )
        logger.info(f"[Mailer] Sent '{subject}' to {to_email} with attachments")
    except Exception as exc:
        logger.error(f"[Mailer] Failed to send email to {to_email}: {exc}")
        raise exc
