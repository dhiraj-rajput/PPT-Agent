from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
from fastapi import APIRouter, Header, Request, HTTPException
from fastapi.responses import Response, RedirectResponse, HTMLResponse

from utils.db_client import get_collection
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

    try:
        events_col = get_collection("tracking_events")
        registered = events_col.find_one({"trackingId": trackingId, "type": "open"})
        if not registered:
            return response

        is_first_open = registered.get("timestamp") is None
        ip_hashed = hash_ip(_client_ip(request))
        ua = user_agent or ""

        if is_first_open:
            events_col.update_one(
                {"_id": registered["_id"]},
                {"$set": {
                    "timestamp": datetime.now(timezone.utc),
                    "userAgent": ua,
                    "ipHash": ip_hashed,
                    "updatedAt": datetime.now(timezone.utc)
                }}
            )

            leads_col = get_collection("leads")
            lead = leads_col.find_one({"_id": registered["leadId"]})
            if lead and lead.get("status") != "replied" and not lead.get("openedAt"):
                status_to_set = "opened" if lead.get("status") == "sent" else lead.get("status", "opened")
                leads_col.update_one(
                    {"_id": lead["_id"]},
                    {"$set": {
                        "status": status_to_set,
                        "openedAt": datetime.now(timezone.utc),
                        "updatedAt": datetime.now(timezone.utc)
                    }}
                )

                # Increment campaign stats
                get_collection("campaigns").update_one(
                    {"_id": registered["campaignId"]},
                    {"$inc": {"stats.totalOpened": 1}}
                )

                # Score open
                score_email_opened(lead["_id"])
        else:
            # Repeat open: Log another tracking event
            events_col.insert_one({
                "trackingId": trackingId,
                "leadId": registered["leadId"],
                "campaignId": registered["campaignId"],
                "type": "open",
                "userAgent": ua,
                "ipHash": ip_hashed,
                "timestamp": datetime.now(timezone.utc),
                "createdAt": datetime.now(timezone.utc),
                "updatedAt": datetime.now(timezone.utc),
            })
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
    try:
        events_col = get_collection("tracking_events")
        registered = events_col.find_one({"trackingId": trackingId, "type": "click"})
        if not registered or not registered.get("destinationUrl"):
            raise HTTPException(status_code=404, detail="Link not found.")

        dest_url = registered["destinationUrl"]
        is_first_click = registered.get("timestamp") is None
        ip_hashed = hash_ip(_client_ip(request))
        ua = user_agent or ""

        if is_first_click:
            events_col.update_one(
                {"_id": registered["_id"]},
                {"$set": {
                    "timestamp": datetime.now(timezone.utc),
                    "userAgent": ua,
                    "ipHash": ip_hashed,
                    "updatedAt": datetime.now(timezone.utc)
                }}
            )

            leads_col = get_collection("leads")
            lead = leads_col.find_one({"_id": registered["leadId"]})
            if lead:
                status_to_set = "clicked" if lead.get("status") != "replied" else lead.get("status")
                leads_col.update_one(
                    {"_id": lead["_id"]},
                    {"$set": {
                        "status": status_to_set,
                        "clickedAt": lead.get("clickedAt") or datetime.now(timezone.utc),
                        "updatedAt": datetime.now(timezone.utc)
                    }}
                )

                # Increment campaign stats
                get_collection("campaigns").update_one(
                    {"_id": registered["campaignId"]},
                    {"$inc": {"stats.totalClicked": 1}}
                )

                # Score click
                score_link_clicked(lead["_id"])
        else:
            # Repeat click: Log another tracking event
            events_col.insert_one({
                "trackingId": trackingId,
                "leadId": registered["leadId"],
                "campaignId": registered["campaignId"],
                "type": "click",
                "destinationUrl": dest_url,
                "userAgent": ua,
                "ipHash": ip_hashed,
                "timestamp": datetime.now(timezone.utc),
                "createdAt": datetime.now(timezone.utc),
                "updatedAt": datetime.now(timezone.utc),
            })

        return RedirectResponse(url=dest_url, status_code=302)
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
        camp_oid = ObjectId(campaignId)
        lead_oid = ObjectId(leadId)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid parameters.")

    leads_col = get_collection("leads")
    lead = leads_col.find_one({"_id": lead_oid})

    if lead:
        leads_col.update_one(
            {"_id": lead_oid},
            {"$set": {
                "status": "unsubscribed",
                "unsubscribedAt": datetime.now(timezone.utc),
                "updatedAt": datetime.now(timezone.utc)
            }}
        )

        get_collection("campaigns").update_one(
            {"_id": camp_oid},
            {"$inc": {"stats.totalUnsubscribed": 1}}
        )

        get_collection("suppressions").update_one(
            {"email": lead["email"]},
            {
                "$setOnInsert": {
                    "email": lead["email"],
                    "reason": "unsubscribed",
                    "campaignId": camp_oid,
                    "createdAt": datetime.now(timezone.utc),
                }
            },
            upsert=True
        )

        get_collection("audit_logs").insert_one({
            "action": "lead.unsubscribe",
            "entityType": "Lead",
            "entityId": lead_oid,
            "details": {"campaignId": campaignId, "email": lead["email"]},
            "createdAt": datetime.now(timezone.utc),
        })

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

