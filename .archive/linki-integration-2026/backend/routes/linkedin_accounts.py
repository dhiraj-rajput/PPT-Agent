import logging
from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

import json
from pydantic import BaseModel, Field
from utils.db_client import get_db_session, _mysql_available
from app.core.auth import get_current_user, decode_and_get_user_async
from models.sql_models import LinkedInAccount, FingerprintProfile, Proxy
from utils.encryption import encrypt_data
from pipeline.linkedin.outreach.login_capture import run_guided_login_websocket

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/linkedin/accounts", tags=["LinkedIn Accounts"])

@router.get("")
async def list_linkedin_accounts(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    List all LinkedIn accounts connected by the current user.
    """
    try:
        user_id = int(current_user["id"])
        stmt = select(LinkedInAccount).where(LinkedInAccount.user_id == user_id)
        res = await db.execute(stmt)
        accounts = res.scalars().all()

        return [
            {
                "id": acc.id,
                "label": acc.label,
                "region": acc.region,
                "auth_method": acc.auth_method,
                "status": acc.status,
                "daily_connection_cap": acc.daily_connection_cap,
                "daily_message_cap": acc.daily_message_cap,
                "warmup_stage": acc.warmup_stage,
                "health_score": acc.health_score,
                "consecutive_flags": acc.consecutive_flags,
                "last_action_at": acc.last_action_at.isoformat() if acc.last_action_at else None,
                "created_at": acc.created_at.isoformat() if acc.created_at else None,
            }
            for acc in accounts
        ]
    except Exception as e:
        logger.error(f"Failed to list LinkedIn accounts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{account_id}/pause")
async def pause_account(
    account_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Pause a LinkedIn account by setting its status to cooldown.
    """
    try:
        user_id = int(current_user["id"])
        # Verify ownership
        stmt = select(LinkedInAccount).where(
            LinkedInAccount.id == account_id,
            LinkedInAccount.user_id == user_id
        )
        res = await db.execute(stmt)
        acc = res.scalar_one_or_none()
        if not acc:
            raise HTTPException(status_code=404, detail="Account not found.")

        await db.execute(
            update(LinkedInAccount)
            .where(LinkedInAccount.id == account_id)
            .values(status="cooldown", updated_at=datetime.utcnow())
        )
        await db.commit()
        return {"status": "success", "message": "Account paused successfully."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to pause account {account_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{account_id}/resume")
async def resume_account(
    account_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Resume a paused LinkedIn account (restoring its active or warming_up status).
    """
    try:
        user_id = int(current_user["id"])
        stmt = select(LinkedInAccount).where(
            LinkedInAccount.id == account_id,
            LinkedInAccount.user_id == user_id
        )
        res = await db.execute(stmt)
        acc = res.scalar_one_or_none()
        if not acc:
            raise HTTPException(status_code=404, detail="Account not found.")

        # IMPORTANT: 'resume' must never be allowed to revive an account
        # whose session is actually known-bad. This previously just flipped
        # status back to active/warming_up unconditionally, which let an
        # account with a dead li_at cookie get put back to work — it then
        # failed on the very next send/health-check pass anyway, just more
        # confusingly (chrome-error://chromewebdata/ navigation failures,
        # ERR_TOO_MANY_REDIRECTS) instead of clearly asking for a reconnect.
        # 'paused'/'cooldown' are fine to resume (those don't imply a dead
        # session) — 'expired'/'banned'/'flagged' are not.
        if acc.status in ("expired", "banned", "flagged"):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"This account's status is '{acc.status}', which means its LinkedIn session "
                    f"is known to be invalid — resuming it would just fail again. Use 'Reconnect' "
                    f"to log in again and get a fresh session instead."
                ),
            )

        # If warmup_stage is 0 or low, return to warming_up, else active
        new_status = "warming_up" if acc.warmup_stage == 0 else "active"

        await db.execute(
            update(LinkedInAccount)
            .where(LinkedInAccount.id == account_id)
            .values(status=new_status, updated_at=datetime.utcnow())
        )
        await db.commit()
        return {"status": "success", "message": f"Account resumed to {new_status}."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume account {account_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{account_id}")
async def delete_account(
    account_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Delete / disconnect a LinkedIn account.
    """
    try:
        user_id = int(current_user["id"])
        stmt = select(LinkedInAccount).where(
            LinkedInAccount.id == account_id,
            LinkedInAccount.user_id == user_id
        )
        res = await db.execute(stmt)
        acc = res.scalar_one_or_none()
        if not acc:
            raise HTTPException(status_code=404, detail="Account not found.")

        # Pause (don't just leave dangling) any running campaigns still
        # pointed at this account. Without this, a campaign silently keeps
        # its linkedin_account_id referencing a now-deleted row — the worker
        # loop is defensive against that now (see linkedin_worker.py), but
        # surfacing it as a paused campaign in the UI is much clearer than a
        # campaign that looks 'running' but can never actually send.
        from models.sql_models import LinkedInCampaign
        await db.execute(
            update(LinkedInCampaign)
            .where(LinkedInCampaign.linkedin_account_id == account_id, LinkedInCampaign.status == "running")
            .values(status="paused")
        )

        await db.execute(
            delete(LinkedInAccount).where(LinkedInAccount.id == account_id)
        )
        await db.commit()
        return {"status": "success", "message": "Account disconnected successfully. Any campaigns using it were paused."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete account {account_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class LinkedInAccountCreate(BaseModel):
    label: str = Field(..., min_length=1)
    region: str = "other"
    # Required
    li_at: str = Field(..., min_length=1)
    # Recommended — helps LinkedIn validate session state
    jsessionid: str = Field("", min_length=0)
    # Optional but important for session longevity:
    # These are the device/browser fingerprint cookies LinkedIn issues at login.
    # Without them the session is "thin" and gets invalidated faster because
    # LinkedIn can't verify device identity on subsequent requests.
    # Paste from your browser's DevTools > Application > Cookies > linkedin.com
    bcookie: str = Field("", min_length=0)   # Browser identifier, ~1yr, critical for anti-fraud
    bscookie: str = Field("", min_length=0)  # Secure browser cookie, ~1yr
    lidc: str = Field("", min_length=0)      # Data center routing, refreshes daily

@router.post("")
async def create_linkedin_account(
    form_data: LinkedInAccountCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Connect a LinkedIn account manually by providing the active session cookies (li_at and JSESSIONID).
    """
    try:
        user_id = int(current_user["id"])
        
        # 1. Create a default FingerprintProfile
        fp = FingerprintProfile(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport="1440x900",
            timezone="America/New_York",
            locale="en-US",
            webgl_seed="default"
        )
        db.add(fp)
        await db.flush()
        
        # 2. Create a default Proxy
        pr = Proxy(
            region=form_data.region,
            endpoint="mock://127.0.0.1:8080",
            credentials_encrypted=""
        )
        db.add(pr)
        await db.flush()
        
        # 3. Build cookie list in the new full-jar format so session_loader
        # replays ALL provided cookies — not just li_at+JSESSIONID.
        # This matches what guided-login now captures and prevents the
        # "thin session" (only 2 cookies) that expires much faster.
        cookie_list = []
        def _add(name: str, value: str):
            if value:
                cookie_list.append({
                    "name": name,
                    "value": value,
                    "domain": ".linkedin.com",
                    "path": "/",
                    "secure": True,
                    "sameSite": "None",
                })
        _add("li_at",     form_data.li_at)
        _add("JSESSIONID", form_data.jsessionid)
        _add("bcookie",   form_data.bcookie)
        _add("bscookie",  form_data.bscookie)
        _add("lidc",      form_data.lidc)

        encrypted_cookies = encrypt_data(json.dumps({"cookies": cookie_list}))
        
        # 4. Create LinkedInAccount
        acc = LinkedInAccount(
            user_id=user_id,
            label=form_data.label,
            region=form_data.region,
            auth_method="guided_login",
            session_cookie_encrypted=encrypted_cookies,
            fingerprint_profile_id=fp.id,
            proxy_id=pr.id,
            status="active",
            daily_connection_cap=8,
            daily_message_cap=15,
            warmup_stage=1,
            health_score=100
        )
        db.add(acc)
        await db.flush()
        
        # Link back
        fp.linkedin_account_id = acc.id
        pr.assigned_account_id = acc.id
        
        await db.commit()
        
        return {
            "status": "success",
            "message": "LinkedIn account connected successfully.",
            "account_id": acc.id
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create LinkedIn account manually: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/connect/ws")
async def websocket_connect(
    websocket: WebSocket,
    region: str = "other",
    label: str = "LinkedIn Account",
    token: str = Query(None)
):
    """
    WebSocket endpoint for streaming browser screens during guided login connection.
    """
    if not token:
        logger.warning("WS connection rejected: Token query parameter is missing.")
        await websocket.close(code=4003)
        return

    # Verify WebSocket user authentication using action/access token
    user = await decode_and_get_user_async(token)
    if not user:
        logger.warning("WS connection rejected: Invalid or expired auth token.")
        await websocket.close(code=4003)
        return

    user_id = int(user["id"])
    try:
        await run_guided_login_websocket(websocket, region, label, user_id)
    except Exception as e:
        logger.error(f"WebSocket session crash: {e}", exc_info=True)


@router.get("/{account_id}/stats")
async def get_account_stats(
    account_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Returns connections count, pending sent invitations count, and profile views count for an account.
    """
    user_id = int(current_user["id"])
    stmt = select(LinkedInAccount).where(LinkedInAccount.id == account_id, LinkedInAccount.user_id == user_id)
    res = await db.execute(stmt)
    acc = res.scalar_one_or_none()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found.")

    from app.core.linkedin_worker import scrape_linkedin_stats_playwright
    stats = await scrape_linkedin_stats_playwright(account_id)
    return {"status": "success", "account_id": account_id, "stats": stats}


@router.post("/{account_id}/sync-accepted")
async def sync_account_accepted(
    account_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Triggers an immediate Voyager REST API connection sync for accepted invitations.
    """
    user_id = int(current_user["id"])
    stmt = select(LinkedInAccount).where(LinkedInAccount.id == account_id, LinkedInAccount.user_id == user_id)
    res = await db.execute(stmt)
    acc = res.scalar_one_or_none()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found.")

    from app.core.linkedin_worker import check_invitation_acceptances
    await check_invitation_acceptances(db)
    return {"status": "success", "message": "Connection acceptance sync triggered successfully."}

