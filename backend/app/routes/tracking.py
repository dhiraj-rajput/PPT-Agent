from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Header, Request, HTTPException
from fastapi.responses import Response, RedirectResponse, HTMLResponse

from utils.db_client import get_sync_db_session, _mysql_available
from models.sql_models import (
    TrackingEvent as SQL_TrackingEvent,
    Lead as SQL_Lead,
    Campaign as SQL_Campaign,
    Edition as SQL_Edition,
    Newsletter as SQL_Newsletter,
    NewsletterSend as SQL_NewsletterSend,
    Suppression as SQL_Suppression,
    AuditLog as SQL_AuditLog,
    NewsletterSubscriber as SQL_NewsletterSubscriber
)
from sqlalchemy import select, insert, update, delete

from app.core.tracking_helpers import (
    TRANSPARENT_PNG,
    hash_ip,
    verify_unsubscribe_token,
)
from app.core.email_worker import score_email_opened, score_link_clicked

router = APIRouter(prefix="/tracking", tags=["tracking"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.get("/open/{trackingId}.png")
def open_tracking(
    trackingId: str,
    request: Request,
    user_agent: Optional[str] = Header(None, alias="User-Agent"),
):
    """
    Serve a transparent 1x1 pixel image to track email opens.
    Must always return the pixel successfully even if database writes fail.
    """
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, private",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    response = Response(content=TRANSPARENT_PNG, media_type="image/png", headers=headers)

    if not _mysql_available:
        return response

    try:
        with get_sync_db_session() as db:
            stmt = select(SQL_TrackingEvent).where(
                SQL_TrackingEvent.tracking_id == trackingId,
                SQL_TrackingEvent.event_type == "open"
            )
            registered = db.execute(stmt).scalar_one_or_none()
            if not registered:
                return response

            is_first_open = registered.timestamp is None
            ip_hashed = hash_ip(_client_ip(request))
            ua = user_agent or ""

            if is_first_open:
                db.execute(
                    update(SQL_TrackingEvent)
                    .where(SQL_TrackingEvent.id == registered.id)
                    .values(
                        timestamp=datetime.utcnow(),
                        user_agent=ua,
                        ip_hash=ip_hashed,
                        updated_at=datetime.utcnow()
                    )
                )

                # 1. Handle Lead/Campaign Open
                if getattr(registered, "lead_id", None):
                    stmt_lead = select(SQL_Lead).where(SQL_Lead.id == registered.lead_id)
                    lead = db.execute(stmt_lead).scalar_one_or_none()
                    if lead and getattr(lead, "status", "") != "replied":
                        status_to_set = "opened" if getattr(lead, "status", "") in ("sent", "pending", "draft") else getattr(lead, "status", "")
                        update_dict = {
                            "status": status_to_set,
                            "updated_at": datetime.utcnow()
                        }
                        if not getattr(lead, "opened_at", None):
                            update_dict["opened_at"] = datetime.utcnow()

                        db.execute(
                            update(SQL_Lead)
                            .where(SQL_Lead.id == lead.id)
                            .values(**update_dict)
                        )

                        # Increment campaign stats
                        if getattr(registered, "campaign_id", None):
                            camp_row = db.execute(select(SQL_Campaign).where(SQL_Campaign.id == registered.campaign_id)).scalar_one_or_none()
                            if camp_row:
                                raw_stats = getattr(camp_row, "stats", {})
                                stats = {str(k): v for k, v in dict(raw_stats).items()} if isinstance(raw_stats, dict) else {}
                                stats["totalOpened"] = int(str(stats.get("totalOpened", 0) or 0)) + 1
                                db.execute(
                                    update(SQL_Campaign)
                                    .where(SQL_Campaign.id == registered.campaign_id)
                                    .values(stats=stats, updated_at=datetime.utcnow())
                                )

                        # Score open
                        score_email_opened(int(str(lead.id)))

                # 2. Handle Newsletter Edition Open
                if getattr(registered, "edition_id", None):
                    edition_row = db.execute(select(SQL_Edition).where(SQL_Edition.id == registered.edition_id)).scalar_one_or_none()
                    if edition_row:
                        raw_stats = getattr(edition_row, "stats", {})
                        stats = {str(k): v for k, v in dict(raw_stats).items()} if isinstance(raw_stats, dict) else {}
                        stats["opened"] = int(str(stats.get("opened", 0) or 0)) + 1
                        db.execute(
                            update(SQL_Edition)
                            .where(SQL_Edition.id == registered.edition_id)
                            .values(stats=stats, updated_at=datetime.utcnow())
                        )

                    if getattr(registered, "newsletter_id", None):
                        news_row = db.execute(select(SQL_Newsletter).where(SQL_Newsletter.id == registered.newsletter_id)).scalar_one_or_none()
                        if news_row:
                            raw_stats_news = getattr(news_row, "stats", {})
                            stats_news = {str(k): v for k, v in dict(raw_stats_news).items()} if isinstance(raw_stats_news, dict) else {}
                            stats_news["totalOpened"] = int(str(stats_news.get("totalOpened", 0) or 0)) + 1
                            db.execute(
                                update(SQL_Newsletter)
                                .where(SQL_Newsletter.id == registered.newsletter_id)
                                .values(stats=stats_news, updated_at=datetime.utcnow())
                            )


                    if getattr(registered, "subscriber_id", None):
                        db.execute(
                            update(SQL_NewsletterSend)
                            .where(
                                SQL_NewsletterSend.edition_id == registered.edition_id,
                                SQL_NewsletterSend.subscriber_id == registered.subscriber_id
                            )
                            .values(opened_at=datetime.utcnow())
                        )
                db.commit()

            else:
                # Repeat open: Log another tracking event
                db.execute(insert(SQL_TrackingEvent).values(
                    tracking_id=trackingId,
                    lead_id=registered.lead_id,
                    campaign_id=registered.campaign_id,
                    edition_id=registered.edition_id,
                    newsletter_id=registered.newsletter_id,
                    subscriber_id=registered.subscriber_id,
                    event_type="open",
                    user_agent=ua,
                    ip_hash=ip_hashed,
                    timestamp=datetime.utcnow(),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                ))
                db.commit()
    except Exception as e:
        # Silently log to stdout so recipient rendering is never affected
        print(f"[Tracking] Open tracking error: {e}")

    return response


@router.get("/click/{trackingId}")
def click_tracking(
    trackingId: str,
    request: Request,
    user_agent: Optional[str] = Header(None, alias="User-Agent"),
):
    """
    Log link clicks and redirect to the original destination URL.
    """
    if not _mysql_available:
        return RedirectResponse(url="/", status_code=302)

    try:
        with get_sync_db_session() as db:
            stmt = select(SQL_TrackingEvent).where(
                SQL_TrackingEvent.tracking_id == trackingId,
                SQL_TrackingEvent.event_type == "click"
            )
            registered = db.execute(stmt).scalar_one_or_none()
            if not registered or not getattr(registered, "destination_url", ""):
                raise HTTPException(status_code=404, detail="Link not found.")

            dest_url = registered.destination_url
            is_first_click = registered.timestamp is None
            ip_hashed = hash_ip(_client_ip(request))
            ua = user_agent or ""

            if is_first_click:
                db.execute(
                    update(SQL_TrackingEvent)
                    .where(SQL_TrackingEvent.id == registered.id)
                    .values(
                        timestamp=datetime.utcnow(),
                        user_agent=ua,
                        ip_hash=ip_hashed,
                        updated_at=datetime.utcnow()
                    )
                )

                # 1. Handle Campaign Lead Click
                if getattr(registered, "lead_id", None):
                    stmt_lead = select(SQL_Lead).where(SQL_Lead.id == registered.lead_id)
                    lead = db.execute(stmt_lead).scalar_one_or_none()
                    if lead:
                        status_to_set = "clicked" if getattr(lead, "status", "") != "replied" else getattr(lead, "status", "")
                        db.execute(
                            update(SQL_Lead)
                            .where(SQL_Lead.id == lead.id)
                            .values(
                                status=status_to_set,
                                clicked_at=getattr(lead, "clicked_at", None) or datetime.utcnow(),
                                updated_at=datetime.utcnow()
                            )
                        )

                        # Increment campaign stats
                        if getattr(registered, "campaign_id", None):
                            camp_row = db.execute(select(SQL_Campaign).where(SQL_Campaign.id == registered.campaign_id)).scalar_one_or_none()
                            if camp_row:
                                raw_stats = getattr(camp_row, "stats", {})
                                stats = {str(k): v for k, v in dict(raw_stats).items()} if isinstance(raw_stats, dict) else {}
                                stats["totalClicked"] = int(str(stats.get("totalClicked", 0) or 0)) + 1
                                db.execute(
                                    update(SQL_Campaign)
                                    .where(SQL_Campaign.id == registered.campaign_id)
                                    .values(stats=stats, updated_at=datetime.utcnow())
                                )

                        # Score click
                        score_link_clicked(int(str(lead.id)))

                # 2. Handle Newsletter Edition Click
                if getattr(registered, "edition_id", None):
                    edition_row = db.execute(select(SQL_Edition).where(SQL_Edition.id == registered.edition_id)).scalar_one_or_none()
                    if edition_row:
                        raw_stats = getattr(edition_row, "stats", {})
                        stats = {str(k): v for k, v in dict(raw_stats).items()} if isinstance(raw_stats, dict) else {}
                        stats["clicked"] = int(str(stats.get("clicked", 0) or 0)) + 1
                        db.execute(
                            update(SQL_Edition)
                            .where(SQL_Edition.id == registered.edition_id)
                            .values(stats=stats, updated_at=datetime.utcnow())
                        )

                    if getattr(registered, "newsletter_id", None):
                        news_row = db.execute(select(SQL_Newsletter).where(SQL_Newsletter.id == registered.newsletter_id)).scalar_one_or_none()
                        if news_row:
                            raw_stats_news = getattr(news_row, "stats", {})
                            stats_news = {str(k): v for k, v in dict(raw_stats_news).items()} if isinstance(raw_stats_news, dict) else {}
                            stats_news["totalClicked"] = int(str(stats_news.get("totalClicked", 0) or 0)) + 1
                            db.execute(
                                update(SQL_Newsletter)
                                .where(SQL_Newsletter.id == registered.newsletter_id)
                                .values(stats=stats_news, updated_at=datetime.utcnow())
                            )


                    if getattr(registered, "subscriber_id", None):
                        db.execute(
                            update(SQL_NewsletterSend)
                            .where(
                                SQL_NewsletterSend.edition_id == registered.edition_id,
                                SQL_NewsletterSend.subscriber_id == registered.subscriber_id
                            )
                            .values(clicked_at=datetime.utcnow())
                        )
                db.commit()
            else:
                # Repeat click: Log another tracking event
                db.execute(insert(SQL_TrackingEvent).values(
                    tracking_id=trackingId,
                    lead_id=registered.lead_id,
                    campaign_id=registered.campaign_id,
                    edition_id=registered.edition_id,
                    newsletter_id=registered.newsletter_id,
                    subscriber_id=registered.subscriber_id,
                    event_type="click",
                    destination_url=dest_url,
                    user_agent=ua,
                    ip_hash=ip_hashed,
                    timestamp=datetime.utcnow(),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                ))
                db.commit()

            return RedirectResponse(url=str(dest_url), status_code=302)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Tracking] Click tracking error: {e}")
        return RedirectResponse(url="/", status_code=302)


@router.get("/unsubscribe/{campaignId}/{leadId}", response_class=HTMLResponse)
def unsubscribe(campaignId: str, leadId: str, t: str):
    """
    Process recipient unsubscribe requests securely.
    """
    if not verify_unsubscribe_token(leadId, campaignId, t):
        raise HTTPException(status_code=400, detail="Invalid or expired unsubscribe link.")

    try:
        parent_id = int(campaignId)
        target_id = int(leadId)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid parameters.")

    if _mysql_available:
        try:
            with get_sync_db_session() as db:
                stmt_lead = select(SQL_Lead).where(SQL_Lead.id == target_id)
                lead = db.execute(stmt_lead).scalar_one_or_none()

                if lead:
                    db.execute(
                        update(SQL_Lead)
                        .where(SQL_Lead.id == target_id)
                        .values(
                            status="unsubscribed",
                            unsubscribed_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                    )

                    # Update campaign stats
                    camp_row = db.execute(select(SQL_Campaign).where(SQL_Campaign.id == parent_id)).scalar_one_or_none()
                    if camp_row:
                        raw_stats = getattr(camp_row, "stats", {})
                        stats = {str(k): v for k, v in dict(raw_stats).items()} if isinstance(raw_stats, dict) else {}
                        stats["totalUnsubscribed"] = int(str(stats.get("totalUnsubscribed", 0) or 0)) + 1
                        db.execute(
                            update(SQL_Campaign)
                            .where(SQL_Campaign.id == parent_id)
                            .values(stats=stats, updated_at=datetime.utcnow())
                        )

                    # Suppression upsert
                    exist_sup = db.execute(select(SQL_Suppression).where(SQL_Suppression.email == lead.email)).scalar_one_or_none()
                    if not exist_sup:
                        db.execute(insert(SQL_Suppression).values(
                            email=lead.email,
                            reason="unsubscribed",
                            campaign_id=parent_id,
                            created_at=datetime.utcnow()
                        ))

                    db.execute(insert(SQL_AuditLog).values(
                        action="lead.unsubscribe",
                        entity_type="Lead",
                        entity_id=str(target_id),
                        details={"campaignId": campaignId, "email": lead.email},
                        created_at=datetime.utcnow()
                    ))
                    db.commit()
                else:
                    # Not a campaign lead — this unsubscribe link may belong to a newsletter subscriber
                    stmt_sub = select(SQL_NewsletterSubscriber).where(
                        SQL_NewsletterSubscriber.id == target_id,
                        SQL_NewsletterSubscriber.newsletter_id == parent_id
                    )
                    subscriber = db.execute(stmt_sub).scalar_one_or_none()

                    if subscriber:
                        db.execute(
                            update(SQL_NewsletterSubscriber)
                            .where(SQL_NewsletterSubscriber.id == target_id)
                            .values(
                                status="unsubscribed",
                                unsubscribed_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()
                            )
                        )

                        # Update newsletter stats
                        news_row = db.execute(select(SQL_Newsletter).where(SQL_Newsletter.id == parent_id)).scalar_one_or_none()
                        if news_row:
                            raw_stats_news = getattr(news_row, "stats", {})
                            stats_news = {str(k): v for k, v in dict(raw_stats_news).items()} if isinstance(raw_stats_news, dict) else {}
                            stats_news["totalUnsubscribed"] = int(str(stats_news.get("totalUnsubscribed", 0) or 0)) + 1
                            db.execute(
                                update(SQL_Newsletter)
                                .where(SQL_Newsletter.id == parent_id)
                                .values(stats=stats_news, updated_at=datetime.utcnow())
                            )



                        # Suppression upsert
                        exist_sup = db.execute(select(SQL_Suppression).where(SQL_Suppression.email == subscriber.email)).scalar_one_or_none()
                        if not exist_sup:
                            db.execute(insert(SQL_Suppression).values(
                                email=subscriber.email,
                                reason="unsubscribed",
                                newsletter_id=parent_id,
                                created_at=datetime.utcnow()
                            ))

                        db.execute(insert(SQL_AuditLog).values(
                            action="subscriber.unsubscribe",
                            entity_type="NewsletterSubscriber",
                            entity_id=str(target_id),
                            details={"newsletterId": campaignId, "email": subscriber.email},
                            created_at=datetime.utcnow()
                        ))
                        db.commit()
        except Exception as e:
            print(f"[Tracking] Unsubscribe processing error: {e}")

    return """
    <html>
      <body style="font-family: Arial, sans-serif; max-width: 480px; margin: 60px auto; text-align: center;">
        <h2>You've been unsubscribed</h2>
        <p style="color:#6b7280;">You won't receive further emails from this sender.</p>
      </body>
    </html>
    """


TRACKER_JS = """
(function () {
  var API_BASE = (function () {
    var script = document.currentScript || document.querySelector('script[src*="tracker.js"]');
    if (script) {
      try {
        return new URL(script.src).origin;
      } catch (e) {}
    }
    return '';
  })();

  var config = { visitorId: '', campaignId: '', leadId: '' };
  var pageStart = Date.now();
  var maxScrollDepth = 0;
  var sentPageView = false;

  function send(eventType, extra) {
    var payload = Object.assign(
      {
        visitorId: config.visitorId,
        campaignId: config.campaignId,
        leadId: config.leadId,
        page: window.location.pathname,
        eventType: eventType,
        duration: Math.round((Date.now() - pageStart) / 1000),
      },
      extra || {}
    );

    try {
      if (navigator.sendBeacon) {
        var blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
        navigator.sendBeacon(API_BASE + '/api/website-events', blob);
      } else {
        fetch(API_BASE + '/api/website-events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
          keepalive: true,
        }).catch(function () {});
      }
    } catch (e) {}
  }

  function trackScroll() {
    var scrollTop = window.scrollY || document.documentElement.scrollTop;
    var docHeight = document.documentElement.scrollHeight - window.innerHeight;
    var depth = docHeight > 0 ? Math.round((scrollTop / docHeight) * 100) : 0;
    if (depth > maxScrollDepth) {
      maxScrollDepth = depth;
      if (maxScrollDepth === 25 || maxScrollDepth === 50 || maxScrollDepth === 75 || maxScrollDepth >= 100) {
        send('scroll', { meta: { scrollDepth: maxScrollDepth } });
      }
    }
  }

  function trackClicks(e) {
    var el = e.target.closest('button, a[role="button"], [data-track-click]');
    if (!el) return;
    send('button_click', {
      meta: { label: el.getAttribute('data-track-label') || el.innerText?.slice(0, 60) || '' },
    });
  }

  function trackForms(e) {
    var form = e.target;
    if (form.tagName !== 'FORM') return;
    send('form_submit', { meta: { formId: form.id || form.getAttribute('name') || '' } });
  }

  window.EmailTracker = {
    init: function (options) {
      config = Object.assign(config, options || {});
      if (!sentPageView) {
        sentPageView = true;
        send('page_view');
      }
      window.addEventListener('scroll', throttle(trackScroll, 500), { passive: true });
      document.addEventListener('click', trackClicks, true);
      document.addEventListener('submit', trackForms, true);
      window.addEventListener('beforeunload', function () {
        send('scroll', { meta: { scrollDepth: maxScrollDepth, final: true } });
      });
    },
  };

  function throttle(fn, wait) {
    var last = 0;
    return function () {
      var now = Date.now();
      if (now - last >= wait) {
        last = now;
        fn.apply(this, arguments);
      }
    };
  }
})();
"""


@router.get("/tracker.js")
def get_tracker_js():
    return Response(content=TRACKER_JS, media_type="application/javascript")
