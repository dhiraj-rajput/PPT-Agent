import { Router } from 'express';
import crypto from 'crypto';
import Meeting from '../models/Meeting.js';
import User from '../models/User.js';
import { requireAuth } from '../middleware/auth.js';
import { sendMeetingInviteEmail, sendMeetingCancelledEmail } from '../utils/mailer.js';
import { createZoomMeeting } from '../utils/zoom.js';
import { createGoogleMeetEvent } from '../utils/googleMeet.js';

const router = Router();
router.use(requireAuth);

function toPublicMeeting(m) {
  return {
    id: m._id,
    title: m.title,
    with: m.with,
    date: m.date,
    time: m.time,
    type: m.type,
    provider: m.provider,
    location: m.location,
    meetingLink: m.meetingLink,
    attendees: (m.attendees || []).map((a) => ({
      name: a.name,
      email: a.email,
      userId: a.userId,
      inviteSent: a.inviteSent,
    })),
    status: m.status,
    cancelledAt: m.cancelledAt,
  };
}

function slugify(text) {
  return (text || 'meeting')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
    .slice(0, 40);
}

// Jitsi's free public server — anyone with the link can join instantly, no
// account, API key, or OAuth setup required. Always available as a fallback.
function generateJitsiLink(title) {
  const room = `OrbitAvanya-${slugify(title)}-${crypto.randomBytes(4).toString('hex')}`;
  return `https://meet.jit.si/${room}`;
}

// Create the actual video room/join link for a meeting, given the provider
// the user picked. Falls back to Jitsi (and reports why) if the requested
// provider isn't configured or the call to it fails, so scheduling never
// hard-fails just because a key is missing or temporary.
async function createVideoRoom({ provider, title, date, time, attendeeEmails }) {
  if (provider === 'zoom') {
    try {
      const { joinUrl } = await createZoomMeeting({ title, date, time });
      return { provider: 'zoom', meetingLink: joinUrl };
    } catch (err) {
      return {
        provider: 'jitsi',
        meetingLink: generateJitsiLink(title),
        warning: `Zoom meeting couldn't be created (${err.message}) — used a Jitsi link instead.`,
      };
    }
  }

  if (provider === 'google_meet') {
    try {
      const { joinUrl } = await createGoogleMeetEvent({ title, date, time, attendeeEmails });
      return { provider: 'google_meet', meetingLink: joinUrl };
    } catch (err) {
      return {
        provider: 'jitsi',
        meetingLink: generateJitsiLink(title),
        warning: `Google Meet link couldn't be created (${err.message}) — used a Jitsi link instead.`,
      };
    }
  }

  return { provider: 'jitsi', meetingLink: generateJitsiLink(title) };
}

// Normalize + de-duplicate the incoming attendees list. Accepts a mix of
// { userId } for already-registered users and { email, name } for anyone
// invited by email only.
async function resolveAttendees(rawAttendees) {
  if (!Array.isArray(rawAttendees)) return [];

  const userIds = rawAttendees.filter((a) => a?.userId).map((a) => a.userId);
  const users = userIds.length ? await User.find({ _id: { $in: userIds } }) : [];
  const userById = new Map(users.map((u) => [u._id.toString(), u]));

  const byEmail = new Map();
  for (const raw of rawAttendees) {
    if (raw?.userId && userById.has(String(raw.userId))) {
      const u = userById.get(String(raw.userId));
      byEmail.set(u.email, { name: u.name, email: u.email, userId: u._id, inviteSent: false });
    } else if (raw?.email) {
      const email = String(raw.email).toLowerCase().trim();
      if (!email) continue;
      byEmail.set(email, { name: raw.name || '', email, userId: null, inviteSent: false });
    }
  }
  return Array.from(byEmail.values());
}

// ---------- GET /api/meetings ----------
router.get('/', async (req, res) => {
  try {
    const meetings = await Meeting.find().sort({ date: 1, time: 1 });
    res.json({ meetings: meetings.map(toPublicMeeting) });
  } catch (err) {
    console.error('List meetings failed:', err.message);
    res.status(500).json({ error: 'Could not load meetings.' });
  }
});

// ---------- POST /api/meetings — auto-creates the video room + emails every attendee ----------
router.post('/', async (req, res) => {
  try {
    const { title, with: withName, date, time, type, location, provider, attendees } = req.body || {};

    if (!title || !date || !time) {
      return res.status(400).json({ error: 'Title, date, and time are required.' });
    }

    const meetingType = type === 'In Person' ? 'In Person' : 'Video Call';
    const resolvedAttendees = await resolveAttendees(attendees);

    let meetingLink = '';
    let usedProvider = 'in-person';
    let providerWarning = '';

    if (meetingType === 'Video Call') {
      const requestedProvider = ['jitsi', 'zoom', 'google_meet'].includes(provider) ? provider : 'jitsi';
      const room = await createVideoRoom({
        provider: requestedProvider,
        title,
        date,
        time,
        attendeeEmails: resolvedAttendees.map((a) => a.email),
      });
      meetingLink = room.meetingLink;
      usedProvider = room.provider;
      providerWarning = room.warning || '';
    }

    const meeting = await Meeting.create({
      title,
      with: withName || '',
      date,
      time,
      type: meetingType,
      provider: usedProvider,
      location: location || '',
      meetingLink,
      attendees: resolvedAttendees,
      createdBy: req.userId,
    });

    if (resolvedAttendees.length) {
      const organizer = await User.findById(req.userId);
      const results = await Promise.allSettled(
        resolvedAttendees.map((a) =>
          sendMeetingInviteEmail({
            toEmail: a.email,
            title,
            date,
            time,
            type: meetingType,
            meetingLink,
            location,
            organizerName: organizer?.name,
          })
        )
      );
      meeting.attendees.forEach((a, i) => {
        a.inviteSent = results[i].status === 'fulfilled';
        if (results[i].status === 'rejected') {
          console.error(`Meeting invite email to ${a.email} failed:`, results[i].reason?.message);
        }
      });
      await meeting.save();
    }

    res.status(201).json({ meeting: toPublicMeeting(meeting), providerWarning });
  } catch (err) {
    console.error('Create meeting failed:', err.message);
    res.status(500).json({ error: 'Could not schedule meeting.' });
  }
});

// ---------- POST /api/meetings/:id/cancel — cancels + emails every attendee ----------
router.post('/:id/cancel', async (req, res) => {
  try {
    const meeting = await Meeting.findById(req.params.id);
    if (!meeting) return res.status(404).json({ error: 'Meeting not found.' });
    if (meeting.status === 'cancelled') {
      return res.status(400).json({ error: 'This meeting is already cancelled.' });
    }

    meeting.status = 'cancelled';
    meeting.cancelledAt = new Date();
    await meeting.save();

    if (meeting.attendees.length) {
      const organizer = await User.findById(req.userId);
      const results = await Promise.allSettled(
        meeting.attendees.map((a) =>
          sendMeetingCancelledEmail({
            toEmail: a.email,
            title: meeting.title,
            date: meeting.date,
            time: meeting.time,
            organizerName: organizer?.name,
          })
        )
      );
      results.forEach((r, i) => {
        if (r.status === 'rejected') {
          console.error(`Cancellation email to ${meeting.attendees[i].email} failed:`, r.reason?.message);
        }
      });
    }

    res.json({ meeting: toPublicMeeting(meeting) });
  } catch (err) {
    console.error('Cancel meeting failed:', err.message);
    res.status(500).json({ error: 'Could not cancel meeting.' });
  }
});

export default router;
