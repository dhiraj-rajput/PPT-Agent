"""
update_account_cookie_and_send.py
----------------------------------
Updates Account 6 with the user's real LinkedIn li_at cookie and immediately
dispatches an automated connection request with note to https://www.linkedin.com/in/dhiraj-rajput-/
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select, update, delete
from utils.db_client import get_db_session
from utils.encryption import encrypt_data
from models.sql_models import LinkedInAccount, LinkedInTarget, LinkedInMessageLog, Person
from app.core.linkedin_worker import process_approved_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("update_cookie_and_send")

LI_AT_COOKIE = "AQEDAWrVNbsAgETwAAABn8c1Cz0AAAGf60GPPVYAn28wJNWqzOKqbXn6kaiW6i-8u603SyLV8KeokwpFroTXQox4SqERwP3BDHUc34Nyfn-ejB9YtoW43XIIRCdTPA1VR4Gp3zRAJwynxHvBamRC24bd"


async def main():
    print("=" * 70)
    print("[DISPATCH] Updating Account 6 with Real Session Cookie & Dispatching Send...")
    print("=" * 70)

    # Build encrypted cookie jar
    cookie_jar = {
        "cookies": [
            {
                "name": "li_at",
                "value": LI_AT_COOKIE,
                "domain": ".linkedin.com",
                "path": "/",
                "secure": True,
                "sameSite": "None",
            }
        ]
    }
    encrypted_cookies = encrypt_data(json.dumps(cookie_jar))

    async for db in get_db_session():
        # 1. Update Account 6
        stmt_acc = select(LinkedInAccount).where(LinkedInAccount.id == 6)
        acc = (await db.execute(stmt_acc)).scalar_one_or_none()
        if not acc:
            print("[ERROR] Account 6 not found!")
            return

        acc.session_cookie_encrypted = encrypted_cookies
        acc.status = "active"
        acc.label = "Akbar Patil"
        acc.timezone = "Asia/Kolkata"
        acc.working_hours_start = 0
        acc.working_hours_end = 24
        acc.working_days = "1,2,3,4,5,6,7"
        acc.connects_sent_today = 0
        acc.messages_sent_today = 0
        acc.last_error = None
        await db.commit()
        print(f"[OK] Account 6 updated in database with real session cookies!")

        # 2. Update Target Person
        target_url = "https://www.linkedin.com/in/dhiraj-rajput-/"
        stmt_p = select(Person).where(Person.linkedin_url == target_url)
        person = (await db.execute(stmt_p)).scalar_one_or_none()
        if not person:
            person = Person(
                full_name="Dhiraj Rajput",
                linkedin_url=target_url,
                created_at=datetime.utcnow()
            )
            db.add(person)
            await db.flush()
        else:
            person.full_name = "Dhiraj Rajput"

        # 3. Target
        stmt_t = select(LinkedInTarget).where(LinkedInTarget.person_id == person.id)
        target = (await db.execute(stmt_t)).scalar_one_or_none()
        if not target:
            target = LinkedInTarget(
                campaign_id=7,
                person_id=person.id,
                assigned_account_id=acc.id,
                scrape_status="scraped",
                connection_status="not_sent",
                created_at=datetime.utcnow()
            )
            db.add(target)
            await db.flush()
        else:
            target.assigned_account_id = acc.id
            target.connection_status = "not_sent"

        # Clear old failed message logs for clean send
        await db.execute(delete(LinkedInMessageLog).where(LinkedInMessageLog.target_id == target.id))

        note_text = "Hi Dhiraj, building AI B2B lead gen platforms with PPT-Agent. Would love to connect!"
        msg = LinkedInMessageLog(
            campaign_id=target.campaign_id or 7,
            target_id=target.id,
            account_id_used=acc.id,
            direction="out",
            content=note_text,
            generated_by="manual",
            status="approved",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(msg)
        await db.commit()
        print(f"[OK] Staged approved LinkedInMessageLog (ID={msg.id}) with note: '{note_text}'")

        # 4. Dispatch via Playwright
        print("\n[PLAYWRIGHT] Launching Playwright browser with real session cookies...")
        success = await process_approved_message(db, msg)
        await db.commit()

        await db.refresh(msg)
        await db.refresh(acc)

        print("=" * 70)
        print(f"Playwright Dispatch Result: {success}")
        print(f"Final Message Log Status: '{msg.status}'")
        print(f"Account Connects Sent Today: {acc.connects_sent_today}")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
