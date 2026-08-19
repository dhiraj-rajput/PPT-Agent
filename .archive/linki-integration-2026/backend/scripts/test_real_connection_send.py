"""
test_real_connection_send.py
------------------------------
Script to dispatch an automated Playwright connection request with a custom note
to a target profile URL using a real authenticated LinkedIn account.

Usage:
  uv run python scripts/test_real_connection_send.py --account-id 6 --target-url "https://www.linkedin.com/in/dhiraj-rajput-/" --note "Hi Dhiraj, happy to connect!"
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select, update
from utils.db_client import get_db_session
from models.sql_models import LinkedInAccount, LinkedInTarget, LinkedInMessageLog, Person
from app.core.linkedin_worker import process_approved_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_real_connection_send")


async def main(account_id: int, target_url: str, note_text: str):
    print("=" * 70)
    print(f"[DISPATCH] Real LinkedIn Connection Send Script")
    print(f"   Account ID: {account_id}")
    print(f"   Target URL: {target_url}")
    print(f"   Note Text:  '{note_text}'")
    print("=" * 70)

    async for db in get_db_session():
        # 1. Verify Account
        acc = (await db.execute(select(LinkedInAccount).where(LinkedInAccount.id == account_id))).scalar_one_or_none()
        if not acc:
            print(f"❌ Account ID={account_id} not found in database!")
            return

        print(f"[OK] Found Account: '{acc.label}' (status: {acc.status}, timezone: {acc.timezone})")

        # Ensure account is active and in working window
        acc.status = "active"
        acc.working_hours_start = 0
        acc.working_hours_end = 24
        acc.working_days = "1,2,3,4,5,6,7"

        # 2. Setup Target Person
        stmt_p = select(Person).where(Person.linkedin_url == target_url)
        person = (await db.execute(stmt_p)).scalar_one_or_none()
        if not person:
            person = Person(
                full_name="Target Lead",
                linkedin_url=target_url,
                created_at=datetime.utcnow()
            )
            db.add(person)
            await db.flush()

        # 3. Setup Target
        stmt_t = select(LinkedInTarget).where(LinkedInTarget.person_id == person.id)
        target = (await db.execute(stmt_t)).scalar_one_or_none()
        if not target:
            target = LinkedInTarget(
                campaign_id=1,
                person_id=person.id,
                assigned_account_id=acc.id,
                scrape_status="scraped",
                connection_status="not_sent",
                created_at=datetime.utcnow()
            )
            db.add(target)
            await db.flush()

        # 4. Create Message Log
        msg = LinkedInMessageLog(
            campaign_id=target.campaign_id or 1,
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
        print(f"[OK] Staging approved LinkedInMessageLog (ID={msg.id})")

        # 5. Dispatch via process_approved_message
        print("\n[DISPATCH] Executing process_approved_message...")
        success = await process_approved_message(db, msg)
        await db.commit()

        await db.refresh(msg)
        print("=" * 70)
        print(f"Dispatch Result: {success}")
        print(f"Final Message Status: '{msg.status}'")
        print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real LinkedIn Connection Send Script")
    parser.add_argument("--account-id", type=int, default=6, help="LinkedInAccount ID")
    parser.add_argument("--target-url", type=str, default="https://www.linkedin.com/in/dhiraj-rajput-/", help="LinkedIn profile URL")
    parser.add_argument("--note", type=str, default="Hi Dhiraj, building AI B2B lead gen platforms. Would love to connect!", help="Connection note text")
    args = parser.parse_args()

    asyncio.run(main(args.account_id, args.target_url, args.note))
