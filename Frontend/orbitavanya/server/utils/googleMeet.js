// Google Meet integration, via the Google Calendar API's conferenceData
// support (creating a Calendar event with a Meet link attached).
// Docs: https://developers.google.com/calendar/api/guides/create-events#video-conferencing
//
// Unlike Zoom's Server-to-Server setup, a bare Google client id/secret can't
// create events by itself — Google requires a one-time OAuth consent from a
// real Google account, after which we keep a refresh token and use that for
// every future meeting. That one-time step lives in Settings > Integrations
// ("Connect Google"), backed by server/routes/integrations.js.
import { google } from 'googleapis';
import Integration from '../models/Integration.js';

function getOAuthClient() {
  const { GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI } = process.env;
  if (!GOOGLE_CLIENT_ID || !GOOGLE_CLIENT_SECRET) {
    throw new Error('Google is not configured (missing GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET).');
  }
  return new google.auth.OAuth2(
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI || 'http://localhost:5050/api/integrations/google/callback'
  );
}

export function getGoogleAuthUrl() {
  const oauth2Client = getOAuthClient();
  return oauth2Client.generateAuthUrl({
    access_type: 'offline',
    prompt: 'consent', // forces a refresh_token back even on repeat connects
    scope: ['https://www.googleapis.com/auth/calendar.events', 'https://www.googleapis.com/auth/userinfo.email'],
  });
}

export async function handleGoogleCallback(code) {
  const oauth2Client = getOAuthClient();
  const { tokens } = await oauth2Client.getToken(code);
  if (!tokens.refresh_token) {
    throw new Error(
      'Google did not return a refresh token. Remove access at https://myaccount.google.com/permissions and try connecting again.'
    );
  }
  oauth2Client.setCredentials(tokens);

  const oauth2 = google.oauth2({ auth: oauth2Client, version: 'v2' });
  const { data } = await oauth2.userinfo.get();

  await Integration.findOneAndUpdate(
    { key: 'google' },
    {
      key: 'google',
      connectedEmail: data.email || '',
      refreshToken: tokens.refresh_token,
      connectedAt: new Date(),
    },
    { upsert: true }
  );

  return data.email;
}

export async function getGoogleConnectionStatus() {
  const integration = await Integration.findOne({ key: 'google' });
  return {
    connected: Boolean(integration?.refreshToken),
    connectedEmail: integration?.connectedEmail || '',
  };
}

async function getAuthorizedClient() {
  const integration = await Integration.findOne({ key: 'google' });
  if (!integration?.refreshToken) {
    throw new Error('Google Meet is not connected yet. Connect it from Settings > Integrations first.');
  }
  const oauth2Client = getOAuthClient();
  oauth2Client.setCredentials({ refresh_token: integration.refreshToken });
  return oauth2Client;
}

export async function createGoogleMeetEvent({ title, date, time, attendeeEmails = [] }) {
  const auth = await getAuthorizedClient();
  const calendar = google.calendar({ version: 'v3', auth });

  const startDateTime = new Date(`${date}T${time}:00`);
  const endDateTime = new Date(startDateTime.getTime() + 30 * 60 * 1000); // default 30-minute slot

  const { data } = await calendar.events.insert({
    calendarId: 'primary',
    conferenceDataVersion: 1,
    requestBody: {
      summary: title,
      start: { dateTime: startDateTime.toISOString() },
      end: { dateTime: endDateTime.toISOString() },
      attendees: attendeeEmails.map((email) => ({ email })),
      conferenceData: {
        createRequest: {
          requestId: `orbitavanya-${Date.now()}`,
          conferenceSolutionKey: { type: 'hangoutsMeet' },
        },
      },
    },
  });

  const meetLink = data.conferenceData?.entryPoints?.find((e) => e.entryPointType === 'video')?.uri || data.hangoutLink;
  if (!meetLink) {
    throw new Error('Google Calendar did not return a Meet link.');
  }
  return { joinUrl: meetLink, eventId: data.id };
}
