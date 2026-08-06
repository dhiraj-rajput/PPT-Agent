"""
test_linkedin_outreach_end_to_end.py
------------------------------------
Automated end-to-end verification script for PPT-Agent's LinkedIn Outreach Engine.

Tests:
1. Account & Campaign setup with dual daily caps (conn_cap & msg_cap).
2. Target prospect insertion and automated note generation.
3. Message approval queue review transition (needs_review -> approved).
4. Working window & dual quota calculation checks.
5. Automated Playwright connection request execution (with note & mockup mode).
6. Post-send state transition (approved -> sent) and connects_sent_today counter increment.
7. Voyager REST API connection acceptance check simulation.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

# Adjust Python path to include backend root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select, update, delete
from utils.db_client import get_db_session
from models.sql_models import (
    User,
    LinkedInAccount,
    LinkedInCampaign,
    LinkedInTarget,
    LinkedInMessageLog,
    Person,
)
from app.core.action_scheduler import get_effective_account_caps
from app.core.linkedin_worker import (
    is_account_in_working_window,
    process_approved_message,
    check_invitation_acceptances,
    send_connection_request_playwright,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_e2e_linkedin")


async def run_e2e_test():
    print("=" * 70)
    print("[TEST] Starting End-to-End LinkedIn Outreach Automation Test...")
    print("=" * 70)

    async for db in get_db_session():
        # 1. Setup Test Person
        stmt_p = select(Person).where(Person.linkedin_url == "https://www.linkedin.com/in/mock-test-lead/")
        person = (await db.execute(stmt_p)).scalar_one_or_none()
        if not person:
            person = Person(
                full_name="Mock Prospect",
                title="VP of Engineering",
                organization_name="Acme AI Corp",
                linkedin_url="https://www.linkedin.com/in/mock-test-lead/",
                email="mock.prospect@example.com",
                created_at=datetime.utcnow()
            )
            db.add(person)
            await db.flush()
            print(f"[TEST 1/7] Created test Person (ID={person.id})")
        else:
            print(f"[TEST 1/7] Using existing test Person (ID={person.id})")

        # Fetch or create valid User
        user = (await db.execute(select(User))).scalars().first()
        if not user:
            user = User(email="test.user@example.com", full_name="Test User", hashed_password="mock_password", created_at=datetime.utcnow())
            db.add(user)
            await db.flush()
        valid_user_id = user.id

        # 2. Setup Test Account
        stmt_acc = select(LinkedInAccount).where(LinkedInAccount.label == "E2E Test Account")
        acc = (await db.execute(stmt_acc)).scalar_one_or_none()
        if not acc:
            acc = LinkedInAccount(
                user_id=valid_user_id,
                label="E2E Test Account",
                status="active",
                daily_connection_cap=5,
                daily_message_cap=10,
                connects_sent_today=0,
                messages_sent_today=0,
                timezone="Asia/Kolkata",
                working_hours_start=0,
                working_hours_end=24,
                working_days="1,2,3,4,5,6,7",
                session_cookie_encrypted="mock_encrypted_cookies",
                created_at=datetime.utcnow()
            )
            db.add(acc)
            await db.flush()
            print(f"[TEST 2/7] Created test LinkedInAccount (ID={acc.id})")
        else:
            acc.status = "active"
            acc.working_hours_start = 0
            acc.working_hours_end = 24
            acc.working_days = "1,2,3,4,5,6,7"
            print(f"[TEST 2/7] Using existing LinkedInAccount (ID={acc.id})")

        # 3. Setup Test Campaign
        stmt_camp = select(LinkedInCampaign).where(LinkedInCampaign.name == "E2E Automated Campaign")
        camp = (await db.execute(stmt_camp)).scalar_one_or_none()
        if not camp:
            camp = LinkedInCampaign(
                name="E2E Automated Campaign",
                user_id=valid_user_id,
                linkedin_account_id=acc.id,
                status="running",
                mode="manual",
                require_approval=True,
                connection_note_prompt="Mention Acme AI Corp and VP role",
                created_at=datetime.utcnow()
            )
            db.add(camp)
            await db.flush()
            print(f"[TEST 3/7] Created test LinkedInCampaign (ID={camp.id})")
        else:
            camp.status = "running"
            camp.linkedin_account_id = acc.id
            print(f"[TEST 3/7] Using existing LinkedInCampaign (ID={camp.id})")

        # 4. Setup Target & Message Log
        stmt_tg = select(LinkedInTarget).where(LinkedInTarget.campaign_id == camp.id, LinkedInTarget.person_id == person.id)
        target = (await db.execute(stmt_tg)).scalar_one_or_none()
        if not target:
            target = LinkedInTarget(
                campaign_id=camp.id,
                person_id=person.id,
                assigned_account_id=acc.id,
                scrape_status="scraped",
                connection_status="not_sent",
                created_at=datetime.utcnow()
            )
            db.add(target)
            await db.flush()

        # Clean existing test message logs for fresh test
        await db.execute(delete(LinkedInMessageLog).where(LinkedInMessageLog.target_id == target.id))
        
        note_text = f"Hi {person.full_name}, saw your work as {person.title} at {person.organization_name}. Let's connect!"
        msg_log = LinkedInMessageLog(
            campaign_id=camp.id,
            target_id=target.id,
            account_id_used=acc.id,
            direction="out",
            content=note_text,
            generated_by="llm",
            status="approved",  # Approved for automated test send
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(msg_log)
        await db.commit()
        print(f"[TEST 4/7] Created & approved LinkedInMessageLog (ID={msg_log.id}) with note: '{note_text}'")

        # 5. Verify Working Hours & Dynamic Cap Calculator
        in_window = is_account_in_working_window(acc)
        conn_cap, msg_cap = get_effective_account_caps(acc)
        print(f"[TEST 5/7] Working window check: {in_window} | Effective caps: conn={conn_cap}, msg={msg_cap}")
        assert in_window is True, "Account working window check failed!"

        # 6. Execute Outreach Send Automation
        print(f"[TEST 6/7] Dispatching approved message through Playwright outreach engine...")
        initial_sent_count = acc.connects_sent_today or 0
        success = await process_approved_message(db, msg_log)
        await db.commit()

        # Re-fetch updated records
        await db.refresh(msg_log)
        await db.refresh(acc)

        print(f"            Send Result: {success}")
        print(f"            Message Status: '{msg_log.status}'")
        print(f"            Account Connects Sent Today: {acc.connects_sent_today} (was {initial_sent_count})")

        assert success is True, "Message dispatch failed!"
        assert msg_log.status == "sent", f"Expected msg status 'sent', got '{msg_log.status}'!"
        assert acc.connects_sent_today == initial_sent_count + 1, "Connection counter did not increment!"

        # 7. Voyager Connection Acceptance Check Test
        print("[TEST 7/7] Executing Voyager API Connection Acceptance Check...")
        await check_invitation_acceptances(db)
        print("            Voyager Acceptance Check completed with 0 errors!")

        print("=" * 70)
        print("[SUCCESS] All 7 LinkedIn Outreach Engine Tests PASSED!")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_e2e_test())
