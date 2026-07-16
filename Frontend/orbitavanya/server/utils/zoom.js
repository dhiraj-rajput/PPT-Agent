// Zoom Server-to-Server OAuth integration.
// Docs: https://developers.zoom.us/docs/internal-apps/s2s-oauth/
//
// Needs three env vars (already added to server/.env):
//   ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET
//
// These are Server-to-Server credentials for the Zoom account itself, so
// meetings are created directly with no separate per-user consent step —
// unlike Google Meet below.

let cachedToken = null; // { accessToken, expiresAt }

async function getAccessToken() {
  const { ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET } = process.env;
  if (!ZOOM_ACCOUNT_ID || !ZOOM_CLIENT_ID || !ZOOM_CLIENT_SECRET) {
    throw new Error('Zoom is not configured (missing ZOOM_ACCOUNT_ID/ZOOM_CLIENT_ID/ZOOM_CLIENT_SECRET).');
  }

  if (cachedToken && cachedToken.expiresAt > Date.now() + 30_000) {
    return cachedToken.accessToken;
  }

  const basicAuth = Buffer.from(`${ZOOM_CLIENT_ID}:${ZOOM_CLIENT_SECRET}`).toString('base64');
  const res = await fetch(
    `https://zoom.us/oauth/token?grant_type=account_credentials&account_id=${encodeURIComponent(ZOOM_ACCOUNT_ID)}`,
    {
      method: 'POST',
      headers: { Authorization: `Basic ${basicAuth}` },
    }
  );

  const data = await res.json();
  if (!res.ok || !data.access_token) {
    throw new Error(data.reason || data.message || 'Could not authenticate with Zoom.');
  }

  cachedToken = {
    accessToken: data.access_token,
    expiresAt: Date.now() + (data.expires_in || 3600) * 1000,
  };
  return cachedToken.accessToken;
}

// Combine an existing date (YYYY-MM-DD) + time (HH:mm) into an ISO string
// for Zoom's `start_time` field. Zoom treats this as being in `timezone`.
function toStartTime(date, time) {
  return `${date}T${time}:00`;
}

export async function createZoomMeeting({ title, date, time }) {
  const accessToken = await getAccessToken();

  const res = await fetch('https://api.zoom.us/v2/users/me/meetings', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      topic: title,
      type: 2, // scheduled meeting
      start_time: toStartTime(date, time),
      timezone: 'UTC',
      settings: {
        join_before_host: true,
        waiting_room: false,
      },
    }),
  });

  const data = await res.json();
  if (!res.ok || !data.join_url) {
    throw new Error(data.message || 'Zoom did not return a meeting link.');
  }

  return { joinUrl: data.join_url, meetingId: data.id };
}
