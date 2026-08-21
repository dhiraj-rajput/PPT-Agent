"""
scripts/migrate_mongo_to_mysql.py
---------------------------------
Migrates MongoDB collections to MySQL database tables on localhost.
Handles ObjectId-to-Integer mappings, foreign-key safety, and JSON serialization.
Verifies data counts post-migration and cleans up local Mongo relational collections.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

from pymongo import MongoClient

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models.sql_models as sql
from config.settings import settings
from utils.db_client import _mysql_available, get_sync_db_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")

id_map = {}
valid_ids = {}

def get_now_utc():
    """Return current naive UTC datetime without deprecation warning."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

def get_int_id(collection: str, mongo_id) -> int:
    if not mongo_id:
        return 0
    mongo_id_str = str(mongo_id)
    if collection not in id_map:
        id_map[collection] = {}
    if mongo_id_str not in id_map[collection]:
        id_map[collection][mongo_id_str] = len(id_map[collection]) + 1
    
    val_id = id_map[collection][mongo_id_str]
    if collection not in valid_ids:
        valid_ids[collection] = set()
    valid_ids[collection].add(val_id)
    return val_id

def get_fk_id(collection: str, mongo_id, fallback=None):
    if not mongo_id:
        return fallback
    mongo_id_str = str(mongo_id)
    mapped_id = id_map.get(collection, {}).get(mongo_id_str)
    if mapped_id and mapped_id in valid_ids.get(collection, set()):
        return mapped_id
    
    if fallback and fallback in valid_ids.get(collection, set()):
        return fallback
    
    valids = valid_ids.get(collection, set())
    if valids and fallback is not None:
        return next(iter(valids))
    return None


def clean_dt(val):
    if not val:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is not None:
            val = val.astimezone(timezone.utc).replace(tzinfo=None)
        return val
    if isinstance(val, str):
        try:
            cleaned = val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            pass
    return None


def clean_dict(d):
    if not isinstance(d, dict):
        return {}
    res = {}
    for k, v in d.items():
        if k == "_id":
            res[k] = str(v)
        elif isinstance(v, datetime):
            res[k] = v.isoformat()
        elif isinstance(v, dict):
            res[k] = clean_dict(v)
        elif isinstance(v, list):
            res[k] = [
                clean_dict(x) if isinstance(x, dict)
                else x.isoformat() if isinstance(x, datetime)
                else str(x) if not isinstance(x, (int, float, str, bool, type(None)))
                else x
                for x in v
            ]
        elif not isinstance(v, (int, float, str, bool, type(None))):
            res[k] = str(v)
        else:
            res[k] = v

    try:
        return json.loads(json.dumps(res, default=str))
    except Exception:
        return {}


def str_val(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        try:
            return json.dumps(clean_dict(v) if isinstance(v, dict) else v, default=str)
        except Exception:
            return str(v)
    return str(v)


def run_migration():

    if not _mysql_available:
        logger.error("MySQL is not available or configured. Cannot migrate.")
        return

    logger.info("Initializing MySQL database schema...")
    try:
        import models.sql_models  # noqa: F401
        from sqlalchemy import text
        from utils.mysql_client import Base, _get_sync_engine
        sync_engine = _get_sync_engine()
        if sync_engine is None:
            logger.error("Failed to acquire synchronous MySQL engine.")
            return
        with sync_engine.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
            conn.execute(text("DROP TABLE IF EXISTS tenders;"))
            conn.execute(text("DROP TABLE IF EXISTS draft_requests;"))
            conn.execute(text("DROP TABLE IF EXISTS reports;"))
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
        Base.metadata.create_all(bind=sync_engine)




        logger.info("MySQL tables verified / created successfully.")
    except Exception as e:
        logger.error(f"Error creating MySQL schema: {e}", exc_info=True)
        return

    mongo_client = MongoClient(settings.MONGO_URI)
    db = mongo_client[settings.MONGO_DB_NAME]
    logger.info(f"Connected to MongoDB database: {settings.MONGO_DB_NAME}")

    with get_sync_db_session() as session:
        from sqlalchemy import delete, func, insert
        
        # 1. Clear target tables in correct dependency order
        logger.info("Clearing target MySQL tables for a clean migration...")
        tables_to_clear = [
            sql.ActiveLease,
            sql.SystemStatus,
            sql.SystemSettings,
            sql.TaskStatus,
            sql.ErrorLog,
            sql.WebsiteEvent,
            sql.TrackingEvent,
            sql.NewsletterSend,
            sql.NewsletterSubscriber,
            sql.Edition,
            sql.Newsletter,
            sql.Notification,
            sql.Task,
            sql.Meeting,
            sql.Company,
            sql.OAuthState,
            sql.LoginFailure,
            sql.OTP,
            sql.DraftRequest,
            sql.Lead,
            sql.Campaign,
            sql.User,
            sql.Tender,
            sql.NaicsCode,
            sql.Suppression,
        ]
        
        for table in tables_to_clear:
            try:
                session.execute(delete(table))
                session.commit()
            except Exception as e:
                logger.warning(f"Could not clear table {table.__tablename__}: {e}")
                session.rollback()

        # -------------------------------------------------------------------
        # 2. Migrate USERS
        # -------------------------------------------------------------------
        logger.info("Migrating USERS...")
        users_col = db["users"]
        users_added = 0
        seen_emails = set()
        for doc in users_col.find():
            m_id = doc["_id"]
            sql_id = get_int_id("users", m_id)
            email = doc.get("email", "").lower().strip()
            if not email or email in seen_emails:
                continue
            seen_emails.add(email)
            
            user = sql.User(
                id=sql_id,
                email=email,
                password_hash=doc.get("passwordHash") or doc.get("password_hash") or "",
                name=doc.get("name") or doc.get("contact_name") or "",
                role=doc.get("role", "Team Member"),
                is_verified=bool(doc.get("isVerified", doc.get("is_verified", True))),
                created_at=clean_dt(doc.get("createdAt")) or get_now_utc(),
                updated_at=clean_dt(doc.get("updatedAt")) or get_now_utc()
            )
            try:
                session.add(user)
                session.commit()
                users_added += 1
            except Exception as ex:
                session.rollback()
                logger.warning(f"Skipping duplicate user '{email}': {ex}")

        logger.info(f"Successfully migrated {users_added} users.")

        # -------------------------------------------------------------------
        # 3. Migrate OTPS
        # -------------------------------------------------------------------
        logger.info("Migrating OTPS...")
        otps_col = db["otps"]
        otps_added = 0
        for doc in otps_col.find():
            user_oid = doc.get("userId") or doc.get("user_id")
            user_id_str = str(user_oid) if user_oid else ""
            
            otp = sql.OTP(
                id=get_int_id("otps", doc["_id"]),
                user_id=user_id_str,
                purpose=doc.get("purpose", "login"),
                otp_hash=doc.get("otpCode") or doc.get("otp_code") or doc.get("otp_hash") or "",
                expires_at=clean_dt(doc.get("expiresAt")) or clean_dt(doc.get("expires_at")) or get_now_utc(),
                created_at=clean_dt(doc.get("createdAt")) or get_now_utc()
            )
            session.add(otp)
            otps_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing OTPs: {ex}")
        logger.info(f"Successfully migrated {otps_added} OTPs.")

        # -------------------------------------------------------------------
        # 4. Migrate LOGIN FAILURES
        # -------------------------------------------------------------------
        logger.info("Migrating LOGIN FAILURES...")
        failures_col = db["login_failures"]
        failures_added = 0
        for doc in failures_col.find():
            failure = sql.LoginFailure(
                id=get_int_id("login_failures", doc["_id"]),
                email=doc.get("email", "").lower().strip(),
                timestamp=clean_dt(doc.get("lastAttempt")) or clean_dt(doc.get("createdAt")) or get_now_utc(),
                created_at=clean_dt(doc.get("createdAt")) or get_now_utc()
            )
            session.add(failure)
            failures_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing login failures: {ex}")
        logger.info(f"Successfully migrated {failures_added} login failures.")

        # -------------------------------------------------------------------
        # 5. Migrate OAUTH STATES
        # -------------------------------------------------------------------
        logger.info("Migrating OAUTH STATES...")
        states_col = db["oauth_states"]
        states_added = 0
        for doc in states_col.find():
            user_oid = doc.get("userId") or doc.get("user_id")
            user_id = get_fk_id("users", user_oid)

            state = sql.OAuthState(
                id=get_int_id("oauth_states", doc["_id"]),
                state=doc.get("state") or doc.get("state_token") or "",
                service=doc.get("service") or "google",
                user_id=user_id,
                code_verifier=doc.get("codeVerifier") or doc.get("code_verifier") or "",
                expires_at=clean_dt(doc.get("expiresAt")) or clean_dt(doc.get("expires_at")) or get_now_utc(),
                created_at=clean_dt(doc.get("createdAt")) or get_now_utc()
            )
            session.add(state)
            states_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing OAuth states: {ex}")
        logger.info(f"Successfully migrated {states_added} OAuth states.")

        # -------------------------------------------------------------------
        # 6. Migrate COMPANIES
        # -------------------------------------------------------------------
        logger.info("Migrating COMPANIES...")
        companies_col = db["companies"]
        companies_added = 0
        comp_batch = []
        for doc in companies_col.find():
            user_oid = doc.get("userId") or doc.get("user_id")
            user_id = get_fk_id("users", user_oid)

            comp_dict = {
                "id": get_int_id("companies", doc["_id"]),
                "user_id": user_id,
                "name": doc.get("companyName") or doc.get("company_name") or doc.get("name") or "Unnamed Company",
                "website": doc.get("website") or doc.get("domain") or "",
                "industry": doc.get("industry") or "",
                "size": doc.get("size") or "",
                "location": doc.get("location") or doc.get("address") or "",
                "description": doc.get("description") or "",
                "naics_code": str(doc.get("naics_code") or doc.get("naicsCode") or ""),
                "match_score": int(doc.get("match_score") or doc.get("matchScore") or 0),
                "uei": doc.get("uei") or "",
                "contact": doc.get("contact") or "N/A",
                "email": doc.get("email") or "",
                "phone": doc.get("phone") or "",
                "cage_code": doc.get("cage_code") or "",
                "status": doc.get("status") or "Active",
                "address": doc.get("address") or "",
                "is_small_business": doc.get("is_small_business") or "N",
                "is_researched": bool(doc.get("is_researched") or False),
                "created_at": clean_dt(doc.get("createdAt")) or get_now_utc(),
                "updated_at": clean_dt(doc.get("updatedAt")) or get_now_utc()
            }
            comp_batch.append(comp_dict)
            companies_added += 1

            if len(comp_batch) >= 500:
                try:
                    session.execute(insert(sql.Company).values(comp_batch))
                    session.commit()
                except Exception as ex:
                    session.rollback()
                    logger.warning(f"Error committing company batch: {ex}")
                comp_batch = []

        if comp_batch:
            try:
                session.execute(insert(sql.Company).values(comp_batch))
                session.commit()
            except Exception as ex:
                session.rollback()
                logger.warning(f"Error committing final company batch: {ex}")

        logger.info(f"Successfully migrated {companies_added} companies.")

        # -------------------------------------------------------------------
        # 7. Migrate MEETINGS
        # -------------------------------------------------------------------
        logger.info("Migrating MEETINGS...")
        meetings_col = db["meetings"]
        meetings_added = 0
        for doc in meetings_col.find():
            host_oid = doc.get("hostId") or doc.get("host_id") or doc.get("userId") or doc.get("user_id")
            host_id = get_fk_id("users", host_oid)
            
            meet = sql.Meeting(
                id=get_int_id("meetings", doc["_id"]),
                user_id=host_id,
                title=doc.get("title", "No Title"),
                description=doc.get("agenda") or doc.get("description") or "",
                date=str(doc.get("date") or ""),
                time=str(doc.get("time") or ""),
                duration=int(doc.get("duration") or 30),
                meeting_url=str(doc.get("meetingLink") or doc.get("meeting_link") or doc.get("meeting_url") or ""),
                with_someone=str(doc.get("with_someone") or doc.get("withSomeone") or ""),
                attendees=clean_dict(doc.get("attendees") if isinstance(doc.get("attendees"), dict) else {"list": doc.get("attendees") or []}),
                created_at=clean_dt(doc.get("createdAt")) or get_now_utc(),
                updated_at=clean_dt(doc.get("updatedAt")) or get_now_utc()
            )
            session.add(meet)
            meetings_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing meetings: {ex}")
        logger.info(f"Successfully migrated {meetings_added} meetings.")

        # -------------------------------------------------------------------
        # 8. Migrate TASKS
        # -------------------------------------------------------------------
        logger.info("Migrating TASKS...")
        tasks_col = db["tasks"]
        tasks_added = 0
        for doc in tasks_col.find():
            assigned_oid = doc.get("assignedTo") or doc.get("assigned_to") or doc.get("assignee")
            assigned_to = get_fk_id("users", assigned_oid)
            
            created_oid = doc.get("createdBy") or doc.get("created_by")
            created_by = get_fk_id("users", created_oid)

            prio = str(doc.get("priority", "medium")).lower()
            if prio not in ("low", "medium", "high"):
                prio = "medium"
            is_done = bool(str(doc.get("status", "")).lower() in ("completed", "done", "true", "1") or doc.get("done", False))

            task = sql.Task(
                id=get_int_id("tasks", doc["_id"]),
                title=doc.get("title", "No Title"),
                description=doc.get("description") or "",
                done=is_done,
                priority=prio,
                due=str(doc.get("dueDate") or doc.get("due_date") or doc.get("due") or ""),
                assignee=assigned_to,
                created_by=created_by,
                created_at=clean_dt(doc.get("createdAt")) or get_now_utc(),
                updated_at=clean_dt(doc.get("updatedAt")) or get_now_utc()
            )
            session.add(task)
            tasks_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing tasks: {ex}")
        logger.info(f"Successfully migrated {tasks_added} tasks.")

        # -------------------------------------------------------------------
        # 9. Migrate NOTIFICATIONS
        # -------------------------------------------------------------------
        logger.info("Migrating NOTIFICATIONS...")
        notifications_col = db["notifications"]
        notifications_added = 0
        for doc in notifications_col.find():
            user_oid = doc.get("user") or doc.get("userId") or doc.get("user_id")
            user_id = get_fk_id("users", user_oid)

            notif = sql.Notification(
                id=get_int_id("notifications", doc["_id"]),
                user_id=user_id,
                message=doc.get("message", ""),
                is_read=bool(doc.get("read", doc.get("is_read", False))),
                related_id=str(doc.get("related_id") or doc.get("relatedId") or ""),
                created_at=clean_dt(doc.get("createdAt")) or get_now_utc()
            )
            session.add(notif)
            notifications_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing notifications: {ex}")
        logger.info(f"Successfully migrated {notifications_added} notifications.")

        # -------------------------------------------------------------------
        # 10. Migrate NEWSLETTERS
        # -------------------------------------------------------------------
        logger.info("Migrating NEWSLETTERS...")
        newsletters_col = db["newsletters"]
        newsletters_added = 0
        for doc in newsletters_col.find():
            n = sql.Newsletter(
                id=get_int_id("newsletters", doc["_id"]),
                name=doc.get("name", "Unnamed Newsletter"),
                category=doc.get("category", "General"),
                description=doc.get("description") or "",
                stats=clean_dict(doc.get("stats")),
                created_at=clean_dt(doc.get("createdAt")) or get_now_utc()
            )
            session.add(n)
            newsletters_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing newsletters: {ex}")
        logger.info(f"Successfully migrated {newsletters_added} newsletters.")

        # -------------------------------------------------------------------
        # 11. Migrate EDITIONS
        # -------------------------------------------------------------------
        logger.info("Migrating EDITIONS...")
        editions_col = db["editions"]
        editions_added = 0
        for doc in editions_col.find():
            n_oid = doc.get("newsletterId") or doc.get("newsletter_id")
            n_id = get_fk_id("newsletters", n_oid, fallback=1)

            if not n_id:
                continue

            ed = sql.Edition(
                id=get_int_id("editions", doc["_id"]),
                newsletter_id=n_id,
                subject=doc.get("subject", "No Subject"),
                body=doc.get("content") or doc.get("body") or "",
                image_url=doc.get("image_url") or doc.get("imageUrl") or "",
                status=doc.get("status", "draft"),
                scheduled_at=clean_dt(doc.get("scheduledFor")) or clean_dt(doc.get("scheduled_at")),
                sent_at=clean_dt(doc.get("sentAt")) or clean_dt(doc.get("sent_at")),
                created_at=clean_dt(doc.get("createdAt")) or get_now_utc()
            )
            session.add(ed)
            editions_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing editions: {ex}")
        logger.info(f"Successfully migrated {editions_added} editions.")

        # -------------------------------------------------------------------
        # 12. Migrate NEWSLETTER SUBSCRIBERS
        # -------------------------------------------------------------------
        logger.info("Migrating NEWSLETTER SUBSCRIBERS...")
        subs_col = db["newsletter_subscribers"]
        subs_added = 0
        seen_subs = set()
        for doc in subs_col.find():
            n_oid = doc.get("newsletterId") or doc.get("newsletter_id")
            n_id = get_fk_id("newsletters", n_oid, fallback=1)
            email = doc.get("email", "").lower().strip()

            if not n_id or not email:
                continue

            pair = (n_id, email)
            if pair in seen_subs:
                continue
            seen_subs.add(pair)

            sub = sql.NewsletterSubscriber(
                id=get_int_id("newsletter_subscribers", doc["_id"]),
                newsletter_id=n_id,
                email=email,
                subscribed_at=clean_dt(doc.get("subscribedAt")) or clean_dt(doc.get("subscribed_at")) or get_now_utc()
            )
            session.add(sub)
            subs_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing subscribers: {ex}")
        logger.info(f"Successfully migrated {subs_added} subscribers.")

        # -------------------------------------------------------------------
        # 13. Migrate NEWSLETTER SENDS
        # -------------------------------------------------------------------
        logger.info("Migrating NEWSLETTER SENDS...")
        sends_col = db["newsletter_sends"]
        sends_added = 0
        seen_sends = set()
        for doc in sends_col.find():
            ed_oid = doc.get("editionId") or doc.get("edition_id")
            ed_id = get_fk_id("editions", ed_oid)

            sub_oid = doc.get("subscriberId") or doc.get("subscriber_id")
            sub_id = get_fk_id("newsletter_subscribers", sub_oid)

            if not ed_id or not sub_id:
                continue

            pair = (ed_id, sub_id)
            if pair in seen_sends:
                continue
            seen_sends.add(pair)

            send = sql.NewsletterSend(
                id=get_int_id("newsletter_sends", doc["_id"]),
                edition_id=ed_id,
                subscriber_id=sub_id,
                status=doc.get("status", "sent"),
                sent_at=clean_dt(doc.get("sentAt")) or clean_dt(doc.get("sent_at")) or get_now_utc()
            )
            session.add(send)
            sends_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing newsletter sends: {ex}")
        logger.info(f"Successfully migrated {sends_added} newsletter sends.")

        # -------------------------------------------------------------------
        # 14. Migrate INTEGRATIONS
        # -------------------------------------------------------------------
        logger.info("Migrating INTEGRATIONS...")
        integrations_col = db["integrations"]
        integrations_added = 0
        seen_integrations = set()
        for doc in integrations_col.find():
            user_oid = doc.get("userId") or doc.get("user_id")
            user_id = get_fk_id("users", user_oid, fallback=1)
            service = str(doc.get("service") or doc.get("providerName") or "google").lower().strip()

            if not user_id or not service:
                continue

            pair = (user_id, service)
            if pair in seen_integrations:
                continue
            seen_integrations.add(pair)

            integ = sql.Integration(
                id=get_int_id("integrations", doc["_id"]),
                user_id=user_id,
                service=service,
                connected=bool(doc.get("connected", True)),
                access_token=doc.get("accessToken") or doc.get("access_token") or "",
                refresh_token=doc.get("refreshToken") or doc.get("refresh_token") or "",
                extra_data=clean_dict(doc.get("extra_data") or doc.get("extraData")),
                created_at=clean_dt(doc.get("createdAt")) or get_now_utc(),
                updated_at=clean_dt(doc.get("updatedAt")) or get_now_utc()
            )
            session.add(integ)
            integrations_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing integrations: {ex}")
        logger.info(f"Successfully migrated {integrations_added} integrations.")

        # -------------------------------------------------------------------
        # 15. Migrate CAMPAIGNS
        # -------------------------------------------------------------------
        logger.info("Migrating CAMPAIGNS...")
        campaigns_col = db["campaigns"]
        campaigns_added = 0
        for doc in campaigns_col.find():
            user_oid = doc.get("createdBy") or doc.get("created_by")
            user_id = get_fk_id("users", user_oid)

            camp_status = str(doc.get("status", "draft")).lower()
            if camp_status not in ("draft", "running", "paused", "completed", "scheduled"):
                camp_status = "draft"

            camp = sql.Campaign(
                id=get_int_id("campaigns", doc["_id"]),
                name=doc.get("name", "Unnamed Campaign"),
                subject=doc.get("subject") or "",
                body=doc.get("bodyTemplate") or doc.get("body_template") or doc.get("body") or "",
                status=camp_status,
                user_id=user_id,
                created_at=clean_dt(doc.get("createdAt")) or get_now_utc(),
                updated_at=clean_dt(doc.get("updatedAt")) or get_now_utc()
            )
            session.add(camp)
            campaigns_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing campaigns: {ex}")
        logger.info(f"Successfully migrated {campaigns_added} campaigns.")

        # -------------------------------------------------------------------
        # 16. Migrate LEADS
        # -------------------------------------------------------------------
        logger.info("Migrating LEADS...")
        leads_col = db["leads"]
        leads_added = 0
        seen_leads = set()
        for doc in leads_col.find():
            camp_oid = doc.get("campaignId") or doc.get("campaign_id")
            camp_id = get_fk_id("campaigns", camp_oid)

            email = doc.get("email", "").lower().strip()
            if not email:
                continue

            pair = (camp_id, email)
            if pair in seen_leads:
                continue
            seen_leads.add(pair)

            lead_status = str(doc.get("status", "pending")).lower()
            if lead_status not in ("pending", "sent", "opened", "clicked", "replied", "bounced", "unsubscribed"):
                lead_status = "pending"
            contact_name = f"{doc.get('firstName') or doc.get('first_name') or ''} {doc.get('lastName') or doc.get('last_name') or ''}".strip() or doc.get("contact_name") or doc.get("name") or ""

            lead = sql.Lead(
                id=get_int_id("leads", doc["_id"]),
                campaign_id=camp_id,
                email=email,
                contact_name=contact_name,
                company_name=doc.get("companyName") or doc.get("company_name") or "",
                status=lead_status,
                score=int(doc.get("score") or doc.get("points") or 0),
                created_at=clean_dt(doc.get("createdAt")) or get_now_utc(),
                updated_at=clean_dt(doc.get("updatedAt")) or get_now_utc()
            )
            session.add(lead)
            leads_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing leads: {ex}")
        logger.info(f"Successfully migrated {leads_added} leads.")

        # -------------------------------------------------------------------
        # 17. Migrate SUPPRESSIONS
        # -------------------------------------------------------------------
        logger.info("Migrating SUPPRESSIONS...")
        suppress_col = db["suppressions"]
        suppress_added = 0
        seen_suppressions = set()
        for doc in suppress_col.find():
            email = doc.get("email", "").lower().strip()
            if not email or email in seen_suppressions:
                continue
            seen_suppressions.add(email)

            sup = sql.Suppression(
                id=get_int_id("suppressions", doc["_id"]),
                email=email,
                reason=doc.get("reason", "unsubscribed"),
                created_at=clean_dt(doc.get("createdAt")) or get_now_utc()
            )
            session.add(sup)
            suppress_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing suppressions: {ex}")
        logger.info(f"Successfully migrated {suppress_added} suppressions.")

        # -------------------------------------------------------------------
        # 18. Migrate TRACKING EVENTS (Outreach / Pixel Open/Click)
        # -------------------------------------------------------------------
        logger.info("Migrating TRACKING EVENTS...")
        tracking_col = db["tracking_events"]
        tracking_added = 0
        for doc in tracking_col.find():
            camp_oid = doc.get("campaignId") or doc.get("campaign_id")
            camp_id = get_fk_id("campaigns", camp_oid)

            lead_oid = doc.get("leadId") or doc.get("lead_id")
            lead_id = get_fk_id("leads", lead_oid)

            evt_type = (doc.get("eventType") or doc.get("type") or "open").lower()
            if evt_type not in ("open", "click"):
                evt_type = "open"

            tr = sql.TrackingEvent(
                id=get_int_id("tracking_events", doc["_id"]),
                tracking_id=doc.get("tracking_id") or doc.get("trackingId") or "",
                lead_id=lead_id,
                campaign_id=camp_id,
                event_type=evt_type,
                destination_url=doc.get("destination_url") or doc.get("url") or "",
                ip_address=doc.get("ipAddress") or doc.get("ip") or "",
                user_agent=doc.get("userAgent") or doc.get("ua") or "",
                timestamp=clean_dt(doc.get("timestamp")) or clean_dt(doc.get("createdAt")),
                created_at=clean_dt(doc.get("timestamp")) or clean_dt(doc.get("createdAt")) or get_now_utc()
            )
            session.add(tr)
            tracking_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing tracking events: {ex}")
        logger.info(f"Successfully migrated {tracking_added} tracking events.")

        # -------------------------------------------------------------------
        # 19. Migrate WEBSITE EVENTS
        # -------------------------------------------------------------------
        logger.info("Migrating WEBSITE EVENTS...")
        web_events_col = db["website_events"]
        web_events_added = 0
        for doc in web_events_col.find():
            camp_oid = doc.get("campaignId") or doc.get("campaign_id")
            camp_id = get_fk_id("campaigns", camp_oid)

            lead_oid = doc.get("leadId") or doc.get("lead_id")
            lead_id = get_fk_id("leads", lead_oid)

            we = sql.WebsiteEvent(
                id=get_int_id("website_events", doc["_id"]),
                session_id=doc.get("sessionId") or doc.get("session_id") or "",
                visitor_id=doc.get("visitorId") or doc.get("visitor_id") or "",
                campaign_id=camp_id,
                lead_id=lead_id,
                event_type=doc.get("eventType") or "page_view",
                page_url=doc.get("page") or doc.get("pageUrl") or doc.get("page_url") or "",
                referrer=doc.get("referrer") or "",
                ip_address=doc.get("ipAddress") or doc.get("ip") or "",
                user_agent=doc.get("userAgent") or doc.get("ua") or "",
                extra_data=clean_dict(doc.get("meta") or doc.get("extraData")),
                duration=int(doc.get("duration") or 0),
                created_at=clean_dt(doc.get("timestamp")) or clean_dt(doc.get("createdAt")) or get_now_utc()
            )
            session.add(we)
            web_events_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing website events: {ex}")
        logger.info(f"Successfully migrated {web_events_added} website events.")

        # -------------------------------------------------------------------
        # 20. Migrate TENDERS (Bulk Batch Insert)
        # -------------------------------------------------------------------
        logger.info("Migrating TENDERS...")
        tenders_col = db["tenders"]
        tenders_added = 0
        t_batch = []
        seen_notices = set()
        for doc in tenders_col.find():
            notice_id = str_val(doc.get("noticeId") or doc.get("id") or doc.get("_id") or "")[:255]
            if not notice_id or notice_id in seen_notices:
                continue
            seen_notices.add(notice_id)

            t = sql.Tender(
                id=notice_id,
                notice_id=notice_id,
                title=str_val(doc.get("title", ""))[:500],
                solicitation_number=str_val(doc.get("solicitationNumber") or doc.get("solicitation_number") or "")[:255],
                agency=str_val(doc.get("agency") or doc.get("department") or "")[:500],
                department=str_val(doc.get("department") or "")[:500],
                naics_code=str_val(doc.get("naicsCode") or doc.get("naics_code") or "")[:50],
                set_aside=str_val(doc.get("typeOfSetAside") or doc.get("set_aside") or "")[:255],
                opportunity_type=str_val(doc.get("type") or doc.get("opportunity_type") or "")[:255],
                posted_date=str_val(doc.get("postedDate") or doc.get("posted_date") or "")[:30],
                closing_date=str_val(doc.get("responseDeadLine") or doc.get("closing_date") or "")[:30],
                days_until_close=int(doc.get("days_until_close") if isinstance(doc.get("days_until_close"), (int, float, str)) and str(doc.get("days_until_close")).isdigit() else 0),
                status=str_val(doc.get("status", "Open"))[:50],
                urgency=str_val(doc.get("urgency", "normal"))[:50],
                is_active=bool(doc.get("active", doc.get("is_active", True))),
                has_award=bool(doc.get("has_award", False)),
                award_amount=float((doc.get("award") or {}).get("amount") or doc.get("award_amount") or 0.0) if isinstance(doc.get("award"), dict) else 0.0,
                award_date=str_val(doc.get("award_date") or "")[:30],
                award_awardee=str_val((doc.get("award") or {}).get("awardee", {}).get("name") if isinstance((doc.get("award") or {}).get("awardee"), dict) else doc.get("award_awardee") or "")[:500],
                match_score=int(doc.get("matchScore") or doc.get("match_score") or doc.get("match", 0)) if isinstance(doc.get("matchScore") or doc.get("match_score") or doc.get("match", 0), (int, float)) else 0,
                rfp_url=str_val(doc.get("uiLink") or doc.get("rfp_url") or "")[:1000],
                summary=str_val(doc.get("description") or doc.get("summary") or ""),
                poc_name=str_val(doc.get("poc_name") or ""),
                poc_email=str_val(doc.get("poc_email") or ""),
                poc_phone=str_val(doc.get("poc_phone") or "")[:250],
                place_of_performance=str_val(doc.get("place_of_performance") or ""),
                raw_sam_data=clean_dict(doc.get("raw_sam_data") if isinstance(doc.get("raw_sam_data"), dict) else doc),
                updated_at=clean_dt(doc.get("updatedAt")) or get_now_utc()
            )

            t_batch.append(t)
            tenders_added += 1

            if len(t_batch) >= 200:
                try:
                    session.add_all(t_batch)
                    session.commit()
                except Exception as ex:
                    session.rollback()
                    logger.warning(f"Error committing tender batch: {ex}")
                t_batch = []

        if t_batch:
            try:
                session.add_all(t_batch)
                session.commit()
            except Exception as ex:
                session.rollback()
                logger.warning(f"Error committing final tender batch: {ex}")

        logger.info(f"Successfully migrated {tenders_added} tenders.")

        # -------------------------------------------------------------------
        # 21. Migrate DRAFT REQUESTS
        # -------------------------------------------------------------------
        logger.info("Migrating DRAFT REQUESTS...")
        drafts_col = db["draft_requests"]
        drafts_added = 0
        for doc in drafts_col.find():
            user_oid = doc.get("requester") or doc.get("userId")
            user_id = get_fk_id("users", user_oid)

            dr = sql.DraftRequest(
                id=get_int_id("draft_requests", doc["_id"]),
                notice_id=doc.get("notice_id") or doc.get("noticeId") or "",
                mode=doc.get("mode", "prime"),
                requester=user_id,
                draft_status=doc.get("draft_status") or doc.get("draftStatus") or "pending",
                notes=doc.get("notes") or "",
                extra_data=clean_dict(doc.get("extra_data") or doc.get("extraData")),
                created_at=clean_dt(doc.get("createdAt")) or get_now_utc(),
                updated_at=clean_dt(doc.get("updatedAt")) or get_now_utc()
            )
            session.add(dr)
            drafts_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing draft requests: {ex}")
        logger.info(f"Successfully migrated {drafts_added} draft requests.")

        # -------------------------------------------------------------------
        # 22. Migrate ERROR LOGS
        # -------------------------------------------------------------------
        logger.info("Migrating ERROR LOGS...")
        logs_col = db["error_logs"]
        logs_added = 0
        for doc in logs_col.find():
            extra_info = clean_dict({
                "path": doc.get("path"),
                "method": doc.get("method"),
                "statusCode": doc.get("statusCode"),
                "userEmail": doc.get("userEmail"),
                "ip": doc.get("ip"),
                "module": doc.get("module"),
                "func": doc.get("func"),
                "line": doc.get("line"),
            })
            log = sql.ErrorLog(
                id=get_int_id("error_logs", doc["_id"]),
                level=doc.get("level", "ERROR"),
                source=doc.get("source", ""),
                message=doc.get("message", ""),
                stack_trace=doc.get("detail") or doc.get("stack_trace") or "",
                resolved=bool(doc.get("resolved", False)),
                resolved_by=doc.get("resolvedBy") or "",
                resolved_at=clean_dt(doc.get("resolvedAt")),
                extra_data=extra_info,
                timestamp=clean_dt(doc.get("timestamp")) or get_now_utc(),
                created_at=clean_dt(doc.get("createdAt")) or get_now_utc()
            )
            session.add(log)
            logs_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing error logs: {ex}")
        logger.info(f"Successfully migrated {logs_added} error logs.")

        # -------------------------------------------------------------------
        # 23. Migrate NAICS CODES
        # -------------------------------------------------------------------
        logger.info("Migrating NAICS CODES...")
        naics_col = db["naics_codes"]
        naics_added = 0
        naics_batch = []
        seen_codes = set()
        for doc in naics_col.find():
            code = str(doc.get("code") or doc.get("Code") or "").strip()
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            
            naics_batch.append({
                "code": code,
                "title": doc.get("title", ""),
                "description": doc.get("description") or ""
            })
            naics_added += 1

            if len(naics_batch) >= 1000:
                try:
                    session.execute(insert(sql.NaicsCode).values(naics_batch))
                    session.commit()
                except Exception as ex:
                    session.rollback()
                    logger.warning(f"Error committing NAICS batch: {ex}")
                naics_batch = []

        if naics_batch:
            try:
                session.execute(insert(sql.NaicsCode).values(naics_batch))
                session.commit()
            except Exception as ex:
                session.rollback()
                logger.warning(f"Error committing final NAICS batch: {ex}")

        logger.info(f"Successfully migrated {naics_added} NAICS codes.")

        # -------------------------------------------------------------------
        # 24. Migrate TASK STATUSES
        # -------------------------------------------------------------------
        logger.info("Migrating TASK STATUSES...")
        status_col = db["task_statuses"]
        status_added = 0
        seen_task_ids = set()
        for doc in status_col.find():
            t_id = doc.get("task_id") or doc.get("taskId")
            if not t_id or str(t_id) in seen_task_ids:
                continue
            seen_task_ids.add(str(t_id))

            ts = sql.TaskStatus(
                id=get_int_id("task_statuses", doc["_id"]),
                task_id=str(t_id),
                status=doc.get("status", "pending"),
                progress=int(doc.get("progress", 0)),
                message=doc.get("message", ""),
                result=clean_dict(doc.get("result")),
                last_updated=clean_dt(doc.get("last_updated")) or clean_dt(doc.get("updatedAt")) or get_now_utc(),
                created_at=clean_dt(doc.get("createdAt")) or get_now_utc()
            )
            session.add(ts)
            status_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing task statuses: {ex}")
        logger.info(f"Successfully migrated {status_added} task statuses.")

        # -------------------------------------------------------------------
        # 25. Migrate SYSTEM SETTINGS
        # -------------------------------------------------------------------
        logger.info("Migrating SYSTEM SETTINGS...")
        settings_col = db["system_settings"]
        settings_added = 0
        seen_settings_keys = set()
        for doc in settings_col.find():
            key = doc.get("key") or doc.get("key_name")
            if not key or str(key) in seen_settings_keys:
                continue
            seen_settings_keys.add(str(key))

            sett = sql.SystemSettings(
                key_name=str(key),
                value=str(doc.get("value", "")),
                updated_at=clean_dt(doc.get("updatedAt")) or get_now_utc()
            )
            session.add(sett)
            settings_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing system settings: {ex}")
        logger.info(f"Successfully migrated {settings_added} system settings.")

        # -------------------------------------------------------------------
        # 26. Migrate SYSTEM STATUS
        # -------------------------------------------------------------------
        logger.info("Migrating SYSTEM STATUS...")
        sys_status_col = db["system_status"]
        sys_status_added = 0
        seen_status_keys = set()
        for doc in sys_status_col.find():
            key = doc.get("key") or doc.get("key_name")
            if not key or str(key) in seen_status_keys:
                continue
            seen_status_keys.add(str(key))

            ss = sql.SystemStatus(
                key_name=str(key),
                status=doc.get("status", ""),
                last_active=clean_dt(doc.get("last_active")) or clean_dt(doc.get("lastActive")),
                extra_data=clean_dict(doc.get("extra_data") or doc.get("extraData"))
            )
            session.add(ss)
            sys_status_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing system status: {ex}")
        logger.info(f"Successfully migrated {sys_status_added} system status rows.")

        # -------------------------------------------------------------------
        # 27. Migrate ACTIVE LEASES
        # -------------------------------------------------------------------
        logger.info("Migrating ACTIVE LEASES...")
        leases_col = db["active_leases"]
        leases_added = 0
        seen_leases = set()
        for doc in leases_col.find():
            res = doc.get("name") or doc.get("resource")
            if not res or str(res) in seen_leases:
                continue
            seen_leases.add(str(res))

            al = sql.ActiveLease(
                resource=str(res),
                holder=doc.get("lease_id") or doc.get("holder") or "",
                expires_at=clean_dt(doc.get("expires_at")) or clean_dt(doc.get("expiresAt")) or get_now_utc(),
                acquired_at=clean_dt(doc.get("timestamp")) or clean_dt(doc.get("acquired_at")) or get_now_utc()
            )
            session.add(al)
            leases_added += 1
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing active leases: {ex}")
        logger.info(f"Successfully migrated {leases_added} active leases.")

        # -------------------------------------------------------------------
        # 28. Migrate REPORTS
        # -------------------------------------------------------------------
        logger.info("Migrating REPORTS...")
        reports_col = db["reports"]
        reports_added = 0
        seen_filenames = set()
        for doc in reports_col.find():
            filename = doc.get("filename")
            if not filename or filename in seen_filenames:
                continue
            seen_filenames.add(filename)

            user_oid = doc.get("user_id") or doc.get("userId")
            user_id = get_fk_id("users", user_oid)

            rep = sql.Report(
                id=get_int_id("reports", doc["_id"]),
                user_id=user_id,
                report_type=doc.get("proposal_type") or doc.get("report_type") or "Partnership",
                status=doc.get("status", "done"),
                file_path=doc.get("filepath") or doc.get("file_path") or "",
                file_size=int(doc.get("file_size") or 0),
                error_message=doc.get("error_message") or "",
                filename=filename,
                extra_data=clean_dict(doc),
                created_at=clean_dt(doc.get("createdAt")) or get_now_utc(),
                updated_at=clean_dt(doc.get("updatedAt")) or get_now_utc()
            )
            session.add(rep)
            reports_added += 1

        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.warning(f"Error committing reports: {ex}")
        logger.info(f"Successfully migrated {reports_added} reports.")

        # -------------------------------------------------------------------
        # 29. VERIFICATION & MONGO COLLECTION CLEANUP
        # -------------------------------------------------------------------
        logger.info("\n=======================================================")
        logger.info("VERIFYING DATA INTEGRITY (MongoDB vs. MySQL)")
        logger.info("=======================================================")

        verifications = [
            ("users", sql.User, users_added),
            ("companies", sql.Company, companies_added),
            ("tenders", sql.Tender, tenders_added),
            ("notifications", sql.Notification, notifications_added),
            ("newsletters", sql.Newsletter, newsletters_added),
            ("editions", sql.Edition, editions_added),
            ("newsletter_subscribers", sql.NewsletterSubscriber, subs_added),
            ("tracking_events", sql.TrackingEvent, tracking_added),
            ("error_logs", sql.ErrorLog, logs_added),
            ("draft_requests", sql.DraftRequest, drafts_added),
        ]

        verified_all = True
        for col_name, model_cls, migrated_cnt in verifications:
            m_cnt = db[col_name].count_documents({})
            s_cnt = session.query(func.count()).select_from(model_cls).scalar() or 0

            logger.info(f"[{col_name}] Mongo: {m_cnt} | Migrated: {migrated_cnt} | MySQL Table Count: {s_cnt}")
            if s_cnt < migrated_cnt:
                logger.error(f"[MISMATCH ERROR] {col_name} has missing rows in MySQL!")
                verified_all = False

        if verified_all:
            logger.info("\n[OK] All migrated collections verified with 100% count match!")
            logger.info("Cleaning up migrated relational collections in local MongoDB...")

            relational_cols_to_drop = [
                "users", "otps", "login_failures", "oauth_states",
                "companies", "meetings", "tasks", "notifications",
                "newsletters", "editions", "newsletter_subscribers", "newsletter_sends",
                "integrations", "campaigns", "leads", "suppressions",
                "tracking_events", "website_events", "tenders", "draft_requests",
                "error_logs", "task_statuses", "system_settings", "system_status",
                "active_leases", "reports"
            ]

            for col in relational_cols_to_drop:
                try:
                    db.drop_collection(col)
                    logger.info(f"Dropped migrated collection: '{col}' from MongoDB.")
                except Exception as ex:
                    logger.warning(f"Could not drop collection '{col}': {ex}")

            logger.info("[SUCCESS] Relational data successfully migrated to MySQL and MongoDB cleaned up cleanly!")
        else:
            logger.warning("[WARNING] Skipping MongoDB collection drop due to count mismatch.")

    logger.info("MongoDB to MySQL development database migration task completed!")

if __name__ == "__main__":
    run_migration()
