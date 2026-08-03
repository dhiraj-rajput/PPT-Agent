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

        await db.execute(
            delete(LinkedInAccount).where(LinkedInAccount.id == account_id)
        )
        await db.commit()
        return {"status": "success", "message": "Account disconnected successfully."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete account {account_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class LinkedInAccountCreate(BaseModel):
    label: str = Field(..., min_length=1)
    region: str = "other"
    li_at: str = Field(..., min_length=1)
    jsessionid: str = Field("", min_length=0)

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
        
        # 3. Encrypt cookie data
        cookie_data = {
            "li_at": form_data.li_at,
            "JSESSIONID": form_data.jsessionid
        }
        encrypted_cookies = encrypt_data(json.dumps(cookie_data))
        
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
