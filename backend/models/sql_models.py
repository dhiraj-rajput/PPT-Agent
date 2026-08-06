"""
models/sql_models.py
--------------------
SQLAlchemy ORM model definitions for ALL MySQL tables in the dual-DB setup.

These 29 tables replace the 24+ "flat/relational" MongoDB collections while
the remaining 13 document-shaped collections stay in MongoDB untouched.

Naming conventions:
  - Table names: lowercase, plural (matches existing MongoDB collection names)
  - Column names: snake_case
  - All datetimes stored as UTC DATETIME (no timezone info in MySQL)
  - JSON columns used for nested/variable-length data that doesn't warrant
    its own table (e.g. stats, attendees, raw_sam_data)

Migration note:
  Call `await init_mysql()` (from utils.mysql_client) at startup.
  All tables use CREATE TABLE IF NOT EXISTS semantics — safe to call repeatedly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BIGINT,
    JSON,
    TEXT,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import LONGTEXT, MEDIUMTEXT
from sqlalchemy.orm import relationship

from utils.mysql_client import Base


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    """Return current UTC datetime (used as default in Column definitions)."""
    return datetime.utcnow()


# ===========================================================================
# AUTH & USERS
# ===========================================================================

class User(Base):
    """
    Replaces MongoDB: users
    Core authentication entity — one row per registered user.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False, default="")
    phone = Column(String(50), default="")
    role = Column(
        String(100),
        nullable=False,
        default="Team Member",
        comment="Owner | Admin | Proposal Writer | Contract Specialist | Business Development | Team Member | Viewer",
    )
    password_hash = Column(String(255), nullable=False, default="")
    avatar_url = Column(String(500), default="")
    is_verified = Column(Boolean, default=False, nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    invited_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    # Relationships
    campaigns = relationship("Campaign", back_populates="creator", foreign_keys="Campaign.user_id")
    tasks = relationship("Task", back_populates="creator", foreign_keys="Task.created_by")
    reports = relationship("Report", back_populates="creator")
    notifications = relationship("Notification", back_populates="user")
    integrations = relationship("Integration", back_populates="user")
    newsletters = relationship("Newsletter", back_populates="creator")
    linkedin_accounts = relationship("LinkedInAccount", back_populates="creator", foreign_keys="LinkedInAccount.user_id")
    linkedin_campaigns = relationship("LinkedInCampaign", back_populates="creator", foreign_keys="LinkedInCampaign.user_id")


class OTP(Base):
    """
    Replaces MongoDB: otps
    Short-lived one-time passwords for login/register/reset flows.
    TTL (10 min) enforced via scheduled DELETE (replaces MongoDB TTL index).
    """
    __tablename__ = "otps"
    __table_args__ = (
        Index("ix_otps_user_purpose", "user_id", "purpose"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False)  # Stored as string to match ObjectId → int migration path
    purpose = Column(String(50), nullable=False, comment="login | register | reset-password")
    otp_hash = Column(String(255), nullable=False)  # SHA-256 hash of the OTP
    attempts = Column(Integer, default=0, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)


class LoginFailure(Base):
    """
    Replaces MongoDB: login_failures
    Tracks failed login attempts for rate-limiting.
    TTL (15 min) enforced via scheduled DELETE.
    """
    __tablename__ = "login_failures"
    __table_args__ = (
        Index("ix_login_failures_email_ts", "email", "timestamp"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False)
    timestamp = Column(DateTime, default=_now, nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)


# ===========================================================================
# CRM CORE
# ===========================================================================

class Company(Base):
    """
    Replaces MongoDB: companies
    CRM company records linked to users.
    FULLTEXT index on name+description for fast text search.
    """
    __tablename__ = "companies"
    __table_args__ = (
        Index("ft_companies_name_desc", "name", "description", mysql_prefix="FULLTEXT"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    website = Column(String(500), default="")
    industry = Column(String(255), default="")
    size = Column(String(100), default="")
    location = Column(String(500), default="")
    description = Column(TEXT, default="")
    naics_code = Column(String(20), default="")
    match_score = Column(Integer, default=0)
    uei = Column(String(100), default="", index=True)
    company_number = Column(String(20), default="", index=True)
    source = Column(String(100), default="Manual Entry", index=True)

    
    # Gov / SAM fields
    contact = Column(String(255), default="N/A")
    email = Column(String(255), default="")
    phone = Column(String(100), default="")
    cage_code = Column(String(100), default="")
    status = Column(String(100), default="Active")
    address = Column(String(500), default="")
    is_small_business = Column(String(10), default="N")
    is_minority_owned = Column(String(10), default="N")
    is_women_owned = Column(String(10), default="N")
    is_veteran_owned = Column(String(10), default="N")
    secondary_naics = Column(TEXT, default="")

    # Research properties
    is_researched = Column(Boolean, default=False)
    research_status = Column(String(100), default="pending")
    last_researched_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now)



class Person(Base):
    """
    Replaces / implements: people (contact_management.person_master reference)
    Flat CRM People record - mirrors the Company table's denormalized style
    (organization/source/status stored as plain strings rather than separate
    master-table foreign keys) so it plugs into the existing dual-DB pattern
    with no extra joins required for list/search/import.
    """
    __tablename__ = "people"
    __table_args__ = (
        Index("ix_people_email", "email"),
        Index("ix_people_organization", "organization_name"),
        Index("ix_people_country", "country"),
        Index("ix_people_status", "status"),
        Index("ix_people_source", "source"),
        Index("ft_people_name_title", "full_name", "title", mysql_prefix="FULLTEXT"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Source / Status - free-text, matches source_master.source_name / status_master.status_name
    source = Column(String(100), default="Manual Entry")
    status = Column(String(50), default="Pending")

    # Organization - free-text, matches organization_master.organization_name
    organization_name = Column(String(255), default="")

    # Identity
    first_name = Column(String(100), default="")
    last_name = Column(String(100), default="")
    full_name = Column(String(255), nullable=False)

    # Role
    title = Column(String(255), default="")
    function_name = Column(String(100), default="")
    seniority = Column(String(100), default="")

    # Contact
    email = Column(String(255), default="", index=True)
    email_status = Column(String(50), default="")
    email_confidence = Column(Numeric(4, 2), nullable=True)
    phone = Column(String(30), default="")
    linkedin_url = Column(String(500), default="")

    # Location
    city = Column(String(100), default="")
    state = Column(String(100), default="")
    country = Column(String(100), default="")

    job_start_date = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class LinkedInCampaign(Base):
    """
    LinkedIn outreach campaigns.
    """
    __tablename__ = "linkedin_campaigns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False, default="")
    mode = Column(Enum("auto", "manual", "hybrid", name="linkedin_campaign_mode"), default="hybrid")
    role_filter = Column(String(255), default="")
    message_generation_mode = Column(Enum("llm", "manual", "template", name="linkedin_message_gen_mode"), default="llm")
    our_company_profile_id = Column(Integer, nullable=True)
    connection_note_prompt = Column(TEXT, default="")
    followup_prompt = Column(TEXT, default="")
    region_routing_rule = Column(JSON, default=dict)
    require_approval = Column(Boolean, default=True)
    status = Column(Enum("draft", "running", "paused", "completed", name="linkedin_campaign_status"), default="draft")
    linkedin_account_id = Column(Integer, ForeignKey("linkedin_accounts.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    creator = relationship("User", back_populates="linkedin_campaigns", foreign_keys=[user_id])
    account = relationship("LinkedInAccount", foreign_keys=[linkedin_account_id])
    targets = relationship("LinkedInTarget", back_populates="campaign", cascade="all, delete-orphan")
    steps = relationship("LinkedInSequenceStep", back_populates="campaign", cascade="all, delete-orphan")
    messages = relationship("LinkedInMessageLog", back_populates="campaign", cascade="all, delete-orphan")


class Campaign(Base):
    """
    Replaces MongoDB: campaigns
    Email outreach campaigns. stats stored as JSON (open/click/bounce counts).
    """
    __tablename__ = "campaigns"
    __table_args__ = (
        Index("ix_campaigns_user_id", "user_id"),
        Index("ix_campaigns_status", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False, default="")
    description = Column(TEXT, default="")
    subject = Column(String(500), default="")
    body = Column(LONGTEXT, default="")
    sender_email = Column(String(255), default="")
    sender_name = Column(String(255), default="")
    status = Column(
        Enum("draft", "running", "paused", "completed", "scheduled"),
        default="draft",
        nullable=False,
    )
    stats = Column(JSON, default=dict)
    working_hours_only = Column(Boolean, default=False)
    timezone = Column(String(100), default="America/Chicago")
    daily_limit = Column(Integer, default=200)
    schedule_start = Column(DateTime, nullable=True)
    attachment_path = Column(String(500), default="")
    campaign_number = Column(String(100), default="")
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    @property
    def created_by(self):
        return self.user_id
    @created_by.setter
    def created_by(self, val):
        self.user_id = val

    @property
    def attachment_filename(self):
        return self.attachment_path or ""
    @attachment_filename.setter
    def attachment_filename(self, val):
        self.attachment_path = str(val or "")

    creator = relationship("User", back_populates="campaigns", foreign_keys=[user_id])
    leads = relationship("Lead", back_populates="campaign")



class Lead(Base):
    """
    Replaces MongoDB: leads
    Individual email recipients within a campaign.
    """
    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_campaign_id", "campaign_id"),
        Index("ix_leads_email", "email"),
        Index("ix_leads_status", "status"),
        UniqueConstraint("campaign_id", "email", name="uq_leads_campaign_email"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    email = Column(String(255), nullable=False)
    contact_name = Column(String(255), default="")
    company_name = Column(String(255), default="")
    company_key = Column(String(255), default="", index=True)
    company_uei = Column(String(100), default="")
    title = Column(String(255), default="")
    website = Column(String(500), default="")
    linkedin = Column(String(500), default="")
    status = Column(
        Enum("pending", "sent", "opened", "clicked", "replied", "bounced", "unsubscribed"),
        default="pending",
        nullable=False,
    )
    score = Column(Integer, default=0)
    grade = Column(Enum("cold", "warm", "hot", "sql"), default="cold")
    send_after = Column(DateTime, nullable=True)
    send_attempts = Column(Integer, default=0)
    resend_count = Column(Integer, default=0)
    last_send_error = Column(TEXT, default="")
    is_invalid = Column(Boolean, default=False)
    bounce_reason = Column(TEXT, default="")

    reply_subject = Column(String(500), default="")
    reply_message = Column(TEXT, default="")
    reply_preview = Column(String(500), default="")
    sent_at = Column(DateTime, nullable=True)

    opened_at = Column(DateTime, nullable=True)
    clicked_at = Column(DateTime, nullable=True)
    replied_at = Column(DateTime, nullable=True)
    bounced_at = Column(DateTime, nullable=True)
    unsubscribed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    campaign = relationship("Campaign", back_populates="leads")
    tracking_events = relationship("TrackingEvent", back_populates="lead")
    email_logs = relationship("EmailLog", back_populates="lead")


class Suppression(Base):
    """
    Replaces MongoDB: suppressions
    Global email suppression list (unsubscribes, bounces).
    """
    __tablename__ = "suppressions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    reason = Column(String(100), default="")
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)


# ===========================================================================
# TRACKING & LOGS
# ===========================================================================

class TrackingEvent(Base):
    """
    Replaces MongoDB: tracking_events
    Pixel-based open/click tracking for email campaigns.
    High-write volume — consider MySQL partitioning by month in production.
    """
    __tablename__ = "tracking_events"
    __table_args__ = (
        Index("ix_tracking_events_tracking_id", "tracking_id"),
        Index("ix_tracking_events_lead_id", "lead_id"),
        Index("ix_tracking_events_campaign_id", "campaign_id"),
        Index("ix_tracking_events_created_at", "created_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tracking_id = Column(String(255), nullable=False)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    edition_id = Column(Integer, ForeignKey("editions.id", ondelete="SET NULL"), nullable=True)

    newsletter_id = Column(Integer, ForeignKey("newsletters.id", ondelete="SET NULL"), nullable=True)
    subscriber_id = Column(Integer, ForeignKey("newsletter_subscribers.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(50), nullable=False)

    destination_url = Column(String(1000), default="")
    ip_address = Column(String(50), default="")
    user_agent = Column(String(500), default="")
    timestamp = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    lead = relationship("Lead", back_populates="tracking_events")


class EmailLog(Base):
    """
    Replaces MongoDB: email_logs
    Audit log for every email send attempt.
    High-write volume — consider MySQL partitioning by month in production.
    """
    __tablename__ = "email_logs"
    __table_args__ = (
        Index("ix_email_logs_campaign_id", "campaign_id"),
        Index("ix_email_logs_lead_id", "lead_id"),
        Index("ix_email_logs_sent_at", "sent_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    email = Column(String(255), default="")
    subject = Column(String(500), default="")
    status = Column(Enum("sent", "failed", "bounced"), nullable=False, default="sent")
    error_message = Column(TEXT, default="")
    sent_at = Column(DateTime, default=_now, nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)

    lead = relationship("Lead", back_populates="email_logs")


class AuditLog(Base):
    """
    Replaces MongoDB: audit_logs
    Append-only audit trail of all user actions.
    """
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_actor", "performed_by"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(100), default="")
    entity_id = Column(String(100), default="")
    performed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_now, nullable=False)


class ErrorLog(Base):
    """
    Replaces MongoDB: error_logs
    Application error logs written by MongoErrorLogHandler → SQLErrorLogHandler.
    TTL (30 days) enforced via scheduled DELETE.
    """
    __tablename__ = "error_logs"
    __table_args__ = (
        Index("ix_error_logs_level", "level"),
        Index("ix_error_logs_source", "source"),
        Index("ix_error_logs_timestamp", "timestamp"),
        Index("ix_error_logs_resolved", "resolved"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    level = Column(String(20), nullable=False, default="ERROR")
    source = Column(String(255), default="")
    message = Column(TEXT, default="")
    stack_trace = Column(LONGTEXT, default="")
    resolved = Column(Boolean, default=False)
    resolved_by = Column(String(255), default="")
    resolved_at = Column(DateTime, nullable=True)
    extra_data = Column(JSON, default=dict)
    timestamp = Column(DateTime, default=_now, nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)



# ===========================================================================
# MEETINGS, TASKS, NOTIFICATIONS
# ===========================================================================

class Meeting(Base):
    """
    Replaces MongoDB: meetings
    Scheduled meetings — video call or in-person.
    attendees stored as JSON (list of {name, email} objects).
    """
    __tablename__ = "meetings"
    __table_args__ = (
        Index("ix_meetings_user_id", "user_id"),
        Index("ix_meetings_date", "date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(500), nullable=False, default="")
    description = Column(TEXT, default="")
    date = Column(String(20), default="")    # ISO date string (YYYY-MM-DD)
    time = Column(String(10), default="")    # HH:MM
    duration = Column(Integer, default=60)   # minutes
    with_someone = Column(String(255), default="")

    provider = Column(String(50), default="manual", comment="zoom | google_meet | manual")
    meeting_url = Column(String(1000), default="")
    meeting_id = Column(String(255), default="")
    meeting_password = Column(String(255), default="")
    attendees = Column(JSON, default=list)   # [{name, email}, ...]

    @property
    def host(self):
        return self.with_someone or ""

    @property
    def start_time(self):
        return self.time or ""

    status = Column(String(50), default="scheduled")
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class Task(Base):
    """
    Replaces MongoDB: tasks
    To-do items with optional user assignment.
    """
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_created_by", "created_by"),
        Index("ix_tasks_assignee", "assignee"),
        Index("ix_tasks_done", "done"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assignee = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(500), nullable=False, default="")
    description = Column(TEXT, default="")
    due = Column(String(30), default="")   # ISO date or datetime string
    priority = Column(Enum("low", "medium", "high"), default="medium")
    done = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    creator = relationship("User", back_populates="tasks", foreign_keys=[created_by])


class Notification(Base):
    """
    Replaces MongoDB: notifications
    In-app notifications for users.
    TTL (30 days) enforced via scheduled DELETE.
    """
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_id", "user_id"),
        Index("ix_notifications_read", "is_read"),
        Index("ix_notifications_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    notification_type = Column(String(100), default="")
    title = Column(String(500), default="")
    message = Column(TEXT, default="")
    is_read = Column(Boolean, default=False)
    link = Column(String(1000), default="")
    related_id = Column(String(255), default="")
    created_at = Column(DateTime, default=_now, nullable=False)


    user = relationship("User", back_populates="notifications")


# ===========================================================================
# TENDERS & PROPOSALS
# ===========================================================================

class Tender(Base):
    """
    Replaces MongoDB: tenders
    SAM.gov contract opportunities.
    raw_sam_data JSON column preserves full API response for the pipeline.
    FULLTEXT index on title+summary for fast text search.
    """
    __tablename__ = "tenders"
    __table_args__ = (
        Index("ix_tenders_notice_id", "notice_id"),
        Index("ix_tenders_naics_code", "naics_code"),
        Index("ix_tenders_status", "status"),
        Index("ix_tenders_posted_date", "posted_date"),
        Index("ft_tenders_title_summary", "title", "summary", mysql_prefix="FULLTEXT"),
    )

    id = Column(String(255), primary_key=True)    # SAM.gov opportunityId
    notice_id = Column(String(255), unique=True, nullable=False)
    title = Column(TEXT, default="")
    solicitation_number = Column(String(255), default="", index=True)
    agency = Column(TEXT, default="")
    department = Column(TEXT, default="")
    naics_code = Column(String(50), default="")
    set_aside = Column(String(255), default="")
    opportunity_type = Column(String(255), default="")
    posted_date = Column(String(30), default="")
    closing_date = Column(String(30), default="")
    days_until_close = Column(Integer, default=0)
    status = Column(String(100), default="Open")
    urgency = Column(String(50), default="normal")
    is_active = Column(Boolean, default=True)
    has_award = Column(Boolean, default=False)
    award_amount = Column(Numeric(15, 2), default=0)
    award_date = Column(String(30), default="")
    award_awardee = Column(TEXT, default="")
    value = Column(Numeric(15, 2), default=0)
    created_at = Column(DateTime, default=_now, nullable=False)


    match_score = Column(Integer, default=0)
    rfp_url = Column(String(1000), default="")
    summary = Column(LONGTEXT, default="")
    poc_name = Column(TEXT, default="")
    poc_email = Column(TEXT, default="")
    poc_phone = Column(String(255), default="")

    place_of_performance = Column(TEXT, default="")
    source = Column(String(100), default="SAM.gov", index=True)
    raw_sam_data = Column(JSON, default=dict)   # Full SAM.gov API response preserved
    raw_companies_house_data = Column(JSON, default=dict) # Companies House enrichment preserved
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    draft_requests = relationship("DraftRequest", back_populates="tender")


class DraftRequest(Base):
    """
    Replaces MongoDB: draft_requests
    Proposal generation job records.
    """
    __tablename__ = "draft_requests"
    __table_args__ = (
        Index("ix_draft_requests_notice_id", "notice_id"),
        Index("ix_draft_requests_requester", "requester"),
        Index("ix_draft_requests_draft_status", "draft_status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    notice_id = Column(String(255), ForeignKey("tenders.id", ondelete="SET NULL"), nullable=True)
    mode = Column(String(50), default="prime", comment="prime | subcontract | partnership | bidforge")
    requester = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    draft_status = Column(String(50), default="pending")

    output_path = Column(String(1000), default="")
    error_message = Column(TEXT, default="")
    notes = Column(TEXT, default="")
    extra_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


    tender = relationship("Tender", back_populates="draft_requests")


class Report(Base):
    """
    Replaces MongoDB: reports
    Generated report file records (PDF/DOCX downloads).
    """
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_user_id", "user_id"),
        Index("ix_reports_status", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    report_type = Column(String(100), default="")
    title = Column(String(500), default="")
    company_name = Column(String(255), default="")
    proposal_type = Column(String(100), default="")
    size = Column(Integer, default=0)
    status = Column(String(50), default="pending")
    source = Column(String(100), default="", index=True)


    file_path = Column(String(1000), default="")
    file_size = Column(Integer, default=0)
    error_message = Column(TEXT, default="")
    filename = Column(String(255), default="", unique=True)
    extra_data = Column(JSON, default=dict)
    params = Column(JSON, default=dict)   # Generation parameters
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


    creator = relationship("User", back_populates="reports")


class TaskStatus(Base):
    """
    Replaces MongoDB: task_statuses
    Background task progress tracking (SSE-backed).
    TTL (1 day) enforced via scheduled DELETE.
    """
    __tablename__ = "task_statuses"
    __table_args__ = (
        Index("ix_task_statuses_task_id", "task_id"),
        Index("ix_task_statuses_last_updated", "last_updated"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(255), unique=True, nullable=False)
    task_type = Column(String(100), default="")
    status = Column(
        String(50),
        default="pending",
    )
    progress = Column(Integer, default=0)   # 0-100
    message = Column(TEXT, default="")
    result = Column(JSON, default=dict)
    extra_data = Column(JSON, default=dict)

    last_updated = Column(DateTime, default=_now, onupdate=_now)
    created_at = Column(DateTime, default=_now, nullable=False)


# ===========================================================================
# NEWSLETTERS
# ===========================================================================

class Newsletter(Base):
    """
    Replaces MongoDB: newsletters
    Newsletter / mailing list definitions.
    """
    __tablename__ = "newsletters"
    __table_args__ = (
        Index("ix_newsletters_user_id", "user_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False, default="")
    description = Column(TEXT, default="")
    status = Column(Enum("active", "paused", "archived"), default="active")
    category = Column(String(100), default="General")
    stats = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_now, nullable=False)

    updated_at = Column(DateTime, default=_now, onupdate=_now)

    creator = relationship("User", back_populates="newsletters")
    subscribers = relationship("NewsletterSubscriber", back_populates="newsletter")
    editions = relationship("Edition", back_populates="newsletter")


class NewsletterSubscriber(Base):
    """
    Replaces MongoDB: newsletter_subscribers
    Subscriber list per newsletter.
    """
    __tablename__ = "newsletter_subscribers"
    __table_args__ = (
        UniqueConstraint("newsletter_id", "email", name="uq_newsletter_subscriber"),
        Index("ix_newsletter_subscribers_email", "email"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    newsletter_id = Column(Integer, ForeignKey("newsletters.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), nullable=False)
    name = Column(String(255), default="")
    status = Column(Enum("subscribed", "unsubscribed", "bounced"), default="subscribed")
    subscribed_at = Column(DateTime, default=_now, nullable=False)
    unsubscribed_at = Column(DateTime, nullable=True)

    newsletter = relationship("Newsletter", back_populates="subscribers")
    sends = relationship("NewsletterSend", back_populates="subscriber")


class Edition(Base):
    """
    Replaces MongoDB: editions
    Individual newsletter edition / issue.
    """
    __tablename__ = "editions"
    __table_args__ = (
        Index("ix_editions_newsletter_id", "newsletter_id"),
        Index("ix_editions_status", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    newsletter_id = Column(Integer, ForeignKey("newsletters.id", ondelete="CASCADE"), nullable=False)
    subject = Column(String(500), nullable=False, default="")
    body = Column(LONGTEXT, default="")
    image_url = Column(String(500), nullable=True)
    status = Column(Enum("draft", "scheduled", "sending", "sent"), default="draft")
    scheduled_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    stats = Column(JSON, default=dict)

    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    newsletter = relationship("Newsletter", back_populates="editions")
    sends = relationship("NewsletterSend", back_populates="edition")


class NewsletterSend(Base):
    """
    Replaces MongoDB: newsletter_sends
    Per-subscriber send tracking for each edition.
    """
    __tablename__ = "newsletter_sends"
    __table_args__ = (
        UniqueConstraint("edition_id", "subscriber_id", name="uq_newsletter_send"),
        Index("ix_newsletter_sends_edition_id", "edition_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    edition_id = Column(Integer, ForeignKey("editions.id", ondelete="CASCADE"), nullable=False)
    subscriber_id = Column(Integer, ForeignKey("newsletter_subscribers.id", ondelete="CASCADE"), nullable=False)
    sent_at = Column(DateTime, default=_now, nullable=False)
    status = Column(Enum("sent", "failed", "bounced"), default="sent")
    opened_at = Column(DateTime, nullable=True)
    clicked_at = Column(DateTime, nullable=True)

    edition = relationship("Edition", back_populates="sends")

    subscriber = relationship("NewsletterSubscriber", back_populates="sends")


# ===========================================================================
# INTEGRATIONS & OAUTH
# ===========================================================================

class Integration(Base):
    """
    Replaces MongoDB: integrations
    Third-party service connections (Zoom, Google, etc.).
    Tokens stored encrypted — application-level AES-256 encryption required.
    """
    __tablename__ = "integrations"
    __table_args__ = (
        UniqueConstraint("user_id", "service", name="uq_integration_user_service"),
        Index("ix_integrations_service", "service"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    service = Column(String(50), nullable=False, comment="zoom | google")
    connected = Column(Boolean, default=False)
    access_token = Column(TEXT, default="")     # AES-256 encrypted at application layer
    refresh_token = Column(TEXT, default="")    # AES-256 encrypted at application layer
    token_expiry = Column(DateTime, nullable=True)
    scope = Column(String(500), default="")
    extra_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    user = relationship("User", back_populates="integrations")


class OAuthState(Base):
    """
    Replaces MongoDB: oauth_states
    CSRF protection state tokens for OAuth flows.
    TTL (10 min) enforced via scheduled DELETE.
    """
    __tablename__ = "oauth_states"
    __table_args__ = (
        Index("ix_oauth_states_expires_at", "expires_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    state = Column(String(255), unique=True, nullable=False, index=True)
    service = Column(String(50), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    code_verifier = Column(TEXT, default="")
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)



# ===========================================================================
# WEBSITE EVENTS
# ===========================================================================

class WebsiteEvent(Base):
    """
    Replaces MongoDB: website_events
    Visitor tracking events from the pixel / JS snippet.
    TTL (90 days) enforced via scheduled DELETE or MySQL partitioning.
    """
    __tablename__ = "website_events"
    __table_args__ = (
        Index("ix_website_events_session_id", "session_id"),
        Index("ix_website_events_campaign_id", "campaign_id"),
        Index("ix_website_events_created_at", "created_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(255), default="")
    visitor_id = Column(String(255), default="")
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(100), nullable=False)
    page_url = Column(String(1000), default="")
    referrer = Column(String(1000), default="")
    ip_address = Column(String(50), default="")
    user_agent = Column(String(500), default="")
    extra_data = Column(JSON, default=dict)
    duration = Column(Integer, default=0) # duration in seconds
    created_at = Column(DateTime, default=_now, nullable=False)



# ===========================================================================
# NAICS CODES
# ===========================================================================

class NaicsCode(Base):
    """
    Replaces MongoDB: naics_codes
    NAICS industry classification codes.
    FULLTEXT index on title+description for fast keyword search.
    """
    __tablename__ = "naics_codes"
    __table_args__ = (
        Index("ft_naics_title_desc", "title", "description", mysql_prefix="FULLTEXT"),
    )

    code = Column(String(20), primary_key=True)
    title = Column(String(500), nullable=False, default="")
    description = Column(TEXT, default="")


class SicCode(Base):
    """
    UK SIC 2007 classification codes for Companies House.
    FULLTEXT index on title+description for fast keyword search.
    """
    __tablename__ = "sic_codes"
    __table_args__ = (
        Index("ft_sic_title_desc", "title", "description", mysql_prefix="FULLTEXT"),
    )

    code = Column(String(20), primary_key=True)
    title = Column(String(500), nullable=False, default="")
    description = Column(TEXT, default="")


class CompaniesHouseCompany(Base):
    """
    Dedicated store for UK Companies House entity profiles.
    """
    __tablename__ = "ch_companies"
    __table_args__ = (
        Index("ix_ch_companies_number", "company_number"),
        Index("ix_ch_companies_status", "company_status"),
        Index("ft_ch_companies_title", "title", mysql_prefix="FULLTEXT"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_number = Column(String(20), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    company_status = Column(String(100), default="active")
    company_type = Column(String(100), default="ltd")
    date_of_creation = Column(String(50), default="")
    sic_codes = Column(JSON, default=list)
    registered_office_address = Column(JSON, default=dict)
    raw_data = Column(JSON, default=dict)
    source = Column(String(100), default="Companies House", index=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now)



# ===========================================================================
# SYSTEM TABLES
# ===========================================================================

class SystemSettings(Base):
    """
    Replaces MongoDB: system_settings
    Key-value application settings (e.g. ai_mode, naics_populated).
    """
    __tablename__ = "system_settings"

    key_name = Column(String(100), primary_key=True)
    value = Column(TEXT, default="")
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class SystemStatus(Base):
    """
    Replaces MongoDB: system_status
    Worker heartbeat / liveness tracking.
    """
    __tablename__ = "system_status"

    key_name = Column(String(100), primary_key=True)
    status = Column(String(50), default="")
    last_active = Column(DateTime, nullable=True)
    extra_data = Column(JSON, default=dict)


class ActiveLease(Base):
    """
    Replaces MongoDB: active_leases
    Distributed lock table for background worker deduplication.
    Uses INSERT ... ON DUPLICATE KEY UPDATE pattern for atomic acquire.
    TTL enforced via scheduled DELETE WHERE expires_at < NOW().
    """
    __tablename__ = "active_leases"

    resource = Column(String(255), primary_key=True)
    holder = Column(String(255), default="")
    expires_at = Column(DateTime, nullable=False)
    acquired_at = Column(DateTime, default=_now, nullable=False)


# ===========================================================================
# LINKEDIN OUTREACH
# ===========================================================================

class LinkedInAccount(Base):
    __tablename__ = "linkedin_accounts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    label = Column(String(255), nullable=False)
    region = Column(Enum("asia", "usa", "mea", "eu", "other", name="linkedin_region_enum"), nullable=False, default="other")
    auth_method = Column(Enum("guided_login", "extension_capture", name="linkedin_auth_method_enum"), nullable=False, default="guided_login")
    session_cookie_encrypted = Column(TEXT, nullable=True)
    fingerprint_profile_id = Column(Integer, ForeignKey("fingerprint_profiles.id", ondelete="SET NULL"), nullable=True)
    proxy_id = Column(Integer, ForeignKey("proxies.id", ondelete="SET NULL"), nullable=True)
    status = Column(Enum("connecting", "warming_up", "active", "cooldown", "flagged", "banned", "expired", name="linkedin_account_status_enum"), default="connecting")
    daily_connection_cap = Column(Integer, default=8)
    daily_message_cap = Column(Integer, default=15)
    connects_sent_today = Column(Integer, default=0)
    messages_sent_today = Column(Integer, default=0)
    last_quota_reset_date = Column(String(10), nullable=True)
    timezone = Column(String(100), default="Asia/Kolkata")
    working_hours_start = Column(Integer, default=0)
    working_hours_end = Column(Integer, default=24)
    working_days = Column(String(50), default="1,2,3,4,5,6,7")
    ramp_up_enabled = Column(Boolean, default=True)
    ramp_start_date = Column(DateTime, default=_now)
    warmup_stage = Column(Integer, default=0)
    health_score = Column(Integer, default=100)
    consecutive_flags = Column(Integer, default=0)
    last_action_at = Column(DateTime, nullable=True)
    last_checkpoint_at = Column(DateTime, nullable=True)
    cooldown_until = Column(DateTime, nullable=True)
    last_error = Column(TEXT, nullable=True)   # Reason why session was last marked expired/flagged
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    creator = relationship("User", back_populates="linkedin_accounts", foreign_keys=[user_id])
    fingerprint = relationship("FingerprintProfile", foreign_keys=[fingerprint_profile_id], post_update=True)
    proxy = relationship("Proxy", foreign_keys=[proxy_id], post_update=True)


class FingerprintProfile(Base):
    __tablename__ = "fingerprint_profiles"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    linkedin_account_id = Column(Integer, nullable=True)
    user_agent = Column(String(500), nullable=True)
    viewport = Column(String(50), nullable=True)
    timezone = Column(String(100), nullable=True)
    locale = Column(String(20), nullable=True)
    webgl_seed = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)


class Proxy(Base):
    __tablename__ = "proxies"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    region = Column(String(50), nullable=True)
    endpoint = Column(String(255), nullable=False)
    credentials_encrypted = Column(TEXT, nullable=True)
    assigned_account_id = Column(Integer, ForeignKey("linkedin_accounts.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)


class LinkedInTarget(Base):
    __tablename__ = "linkedin_targets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(BigInteger, ForeignKey("people.id", ondelete="CASCADE"), nullable=True)
    campaign_id = Column(Integer, ForeignKey("linkedin_campaigns.id", ondelete="CASCADE"), nullable=True)
    assigned_account_id = Column(Integer, ForeignKey("linkedin_accounts.id", ondelete="SET NULL"), nullable=True)
    seniority_target = Column(String(100), nullable=True)
    scrape_status = Column(Enum("pending", "scraped", "failed", name="linkedin_scrape_status_enum"), default="pending")
    scraped_profile_json = Column(JSON, nullable=True)
    messaging_urn = Column(String(255), nullable=True)
    is_first_degree = Column(Boolean, default=False)
    enriched_at = Column(DateTime, nullable=True)
    connection_status = Column(Enum("not_sent", "pending", "accepted", "rejected", "withdrawn", name="linkedin_conn_status_enum"), default="not_sent")
    last_action_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    person = relationship("Person")
    campaign = relationship("LinkedInCampaign", back_populates="targets")
    account = relationship("LinkedInAccount")
    messages = relationship("LinkedInMessageLog", back_populates="target", cascade="all, delete-orphan")


class LinkedInSequenceStep(Base):
    __tablename__ = "linkedin_sequence_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("linkedin_campaigns.id", ondelete="CASCADE"), nullable=False)
    step_order = Column(Integer, nullable=False)
    trigger = Column(Enum("on_connect_accept", "no_reply_after_days", "on_reply", name="linkedin_seq_trigger_enum"), nullable=False)
    trigger_value = Column(Integer, nullable=True)
    action = Column(Enum("send_message", "send_connection_note", "notify_human", name="linkedin_seq_action_enum"), nullable=False)
    prompt_template = Column(TEXT, nullable=True)
    static_message = Column(TEXT, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    campaign = relationship("LinkedInCampaign", back_populates="steps")


class LinkedInMessageLog(Base):
    __tablename__ = "linkedin_message_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    target_id = Column(Integer, ForeignKey("linkedin_targets.id", ondelete="CASCADE"), nullable=True)
    campaign_id = Column(Integer, ForeignKey("linkedin_campaigns.id", ondelete="CASCADE"), nullable=True)
    account_id_used = Column(Integer, ForeignKey("linkedin_accounts.id", ondelete="CASCADE"), nullable=True)
    direction = Column(Enum("out", "in", name="linkedin_msg_direction_enum"), nullable=False)
    content = Column(TEXT, nullable=True)
    generated_by = Column(Enum("llm", "manual", "template", name="linkedin_msg_gen_by_enum"), nullable=False)
    status = Column(Enum("queued", "needs_review", "approved", "sent", "failed", name="linkedin_msg_status_enum"), default="queued")
    sent_at = Column(DateTime, nullable=True)
    scheduled_send_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    target = relationship("LinkedInTarget", back_populates="messages")
    campaign = relationship("LinkedInCampaign", back_populates="messages")
    account = relationship("LinkedInAccount", foreign_keys=[account_id_used])
    reply_classifications = relationship("LinkedInReplyClassification", back_populates="message_log", cascade="all, delete-orphan")


class LinkedInReplyClassification(Base):
    __tablename__ = "linkedin_reply_classifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_log_id = Column(Integer, ForeignKey("linkedin_message_logs.id", ondelete="CASCADE"), nullable=False)
    intent = Column(Enum("interested", "not_interested", "objection", "out_of_office", "meeting_request", "unclear", name="linkedin_reply_intent_enum"), nullable=False)
    confidence = Column(Numeric(4, 2), nullable=True)
    suggested_next_action = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    message_log = relationship("LinkedInMessageLog", back_populates="reply_classifications")
