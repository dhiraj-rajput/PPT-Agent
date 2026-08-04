"""
pipeline/linkedin/outreach/session_loader.py
-----------------------------------------------
Fixes the "ERR_TOO_MANY_REDIRECTS" bug: linkedin_worker.py was opening a
brand new browser context with a HARD-CODED user-agent/timezone and no
proxy, then replaying only the li_at cookie into it. LinkedIn issues a
session to a specific fingerprint+IP combination during login; replaying
just one cookie from a different browser identity and no proxy is exactly
what LinkedIn's device/fraud-detection layer treats as a hijacked session —
it force-redirects between the profile page and an auth/checkpoint wall
until Chrome gives up with ERR_TOO_MANY_REDIRECTS.

This module is the SINGLE place that opens an authenticated LinkedIn
browser session for outreach actions. Anything that needs to act as a
connected LinkedInAccount (send_connection_request, send_message, the
Phase 2 reply poller, profile_scraper, etc.) should go through
open_authenticated_context() rather than hand-rolling browser/context
creation — that's what let the mismatch bug happen in the first place.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from utils.encryption import decrypt_data
from utils.db_client import get_db_session
from models.sql_models import LinkedInAccount, FingerprintProfile, Proxy
from sqlalchemy import select

logger = logging.getLogger("session_loader")


class SessionExpiredError(Exception):
    """Raised when the stored cookies no longer authenticate — i.e. LinkedIn
    is redirecting to /login or /checkpoint, or Chrome gave up with
    ERR_TOO_MANY_REDIRECTS. Callers should mark the account 'expired' and
    prompt a reconnect rather than treat this as a one-off transient error."""


def _parse_viewport(viewport_str: Optional[str]) -> dict:
    try:
        w, h = (viewport_str or "1280x800").lower().split("x")
        return {"width": int(w), "height": int(h)}
    except Exception:
        return {"width": 1280, "height": 800}


async def _load_account_identity(account_id: int):
    """Fetches the account's stored fingerprint + proxy rows (the SAME ones
    used at guided-login time), plus the decrypted full cookie list."""
    async for db in get_db_session():
        account = (
            await db.execute(select(LinkedInAccount).where(LinkedInAccount.id == account_id))
        ).scalar_one_or_none()
        if not account:
            raise ValueError(f"LinkedInAccount {account_id} not found")

        fingerprint = None
        if account.fingerprint_profile_id:
            fingerprint = (
                await db.execute(
                    select(FingerprintProfile).where(FingerprintProfile.id == account.fingerprint_profile_id)
                )
            ).scalar_one_or_none()

        proxy = None
        if account.proxy_id:
            proxy = (
                await db.execute(select(Proxy).where(Proxy.id == account.proxy_id))
            ).scalar_one_or_none()

        return account, fingerprint, proxy


def _cookie_list_from_encrypted(session_cookie_encrypted: str) -> list[dict]:
    """Supports both the new full-cookie-jar format ({"cookies": [...]}) and,
    defensively, the old {"li_at": ..., "JSESSIONID": ...} format from
    before this fix, so accounts connected before this patch don't just
    hard-fail — they'll still be thin (missing bcookie etc.) and should be
    reconnected via the guided-login flow when convenient, but this avoids
    an immediate crash."""
    raw = decrypt_data(session_cookie_encrypted or "")
    if not raw:
        return []
    data = json.loads(raw)

    if "cookies" in data:
        return data["cookies"]

    # Legacy shape fallback.
    legacy = []
    if data.get("li_at"):
        legacy.append({"name": "li_at", "value": data["li_at"], "domain": ".linkedin.com", "path": "/", "secure": True, "sameSite": "None"})
    if data.get("JSESSIONID"):
        legacy.append({"name": "JSESSIONID", "value": data["JSESSIONID"], "domain": ".linkedin.com", "path": "/", "secure": True, "sameSite": "None"})
    return legacy


async def open_authenticated_context(account_id: int):
    """
    Returns (playwright_ctx, browser, context, page) — a browser session
    that matches the fingerprint the account logged in with, routed through
    its assigned proxy if it has one, with the FULL captured cookie jar
    replayed. Caller is responsible for closing (see close_authenticated_context).
    """
    account, fingerprint, proxy = await _load_account_identity(account_id)

    cookie_list = _cookie_list_from_encrypted(account.session_cookie_encrypted)
    if not any(c["name"] == "li_at" for c in cookie_list):
        raise SessionExpiredError(f"No li_at cookie stored for account {account_id} — reconnect required.")

    launch_args: dict = {
        "headless": True,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ],
    }
    if proxy and proxy.endpoint and not proxy.endpoint.startswith("mock://"):
        proxy_cfg = {"server": proxy.endpoint}
        if proxy.credentials_encrypted:
            creds = decrypt_data(proxy.credentials_encrypted)
            username, _, password = creds.partition(":")
            if username:
                proxy_cfg["username"] = username
                proxy_cfg["password"] = password
        launch_args["proxy"] = proxy_cfg
    elif proxy and proxy.endpoint.startswith("mock://"):
        logger.warning(
            f"[session_loader] account {account_id} has a placeholder mock:// proxy — "
            f"ignoring it and connecting without a proxy. Reconnect this account once a "
            f"real region-matched proxy is provisioned for consistent IP identity."
        )

    playwright_ctx = await async_playwright().start()
    browser = await playwright_ctx.chromium.launch(**launch_args)

    context_kwargs: dict = {"viewport": _parse_viewport(fingerprint.viewport if fingerprint else None)}
    if fingerprint:
        context_kwargs["user_agent"] = fingerprint.user_agent
        context_kwargs["locale"] = fingerprint.locale
        context_kwargs["timezone_id"] = fingerprint.timezone
    context = await browser.new_context(**context_kwargs)

    await context.add_cookies(cookie_list)

    # Real logged-in browsers render this page with full interactive
    # buttons; our headless automation was getting zero buttons back at
    # all, which points at LinkedIn's client-side bot detection serving a
    # stripped/limited page rather than an auth or selector problem.
    # Headless Chromium exposes several tells a real browser doesn't
    # (navigator.webdriver=true, no window.chrome, empty plugins/languages).
    # Mask the most common ones before any page loads in this context.
    await context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = window.chrome || { runtime: {} };
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
        if (originalQuery) {
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters)
            );
        }
        """
    )

    page = await context.new_page()
    return playwright_ctx, browser, context, page


async def close_authenticated_context(playwright_ctx, browser, context) -> None:
    try:
        if context:
            await context.close()
        if browser:
            await browser.close()
        if playwright_ctx:
            await playwright_ctx.stop()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[session_loader] error tearing down browser session: {exc}")


def is_redirect_loop_error(exc: Exception) -> bool:
    """Detects the specific Playwright navigation error this bug produces,
    so callers can distinguish 'session is dead, stop and reconnect' from a
    generic transient network blip."""
    msg = str(exc)
    return "ERR_TOO_MANY_REDIRECTS" in msg or "ERR_CONNECTION_RESET" in msg
