import Notification from '../models/Notification.js';

// Small shared helper so any route (meetings, tasks, etc.) can drop an
// in-app alert for a user without duplicating the Notification.create call.
// Never throws — a failed notification should never break the main action
// (scheduling a meeting, assigning a task, ...) it's attached to.
export async function pushNotification({ userId, type = 'custom', title, message = '', link = '', relatedId = null }) {
  if (!userId || !title) return null;
  try {
    return await Notification.create({ user: userId, type, title, message, link, relatedId });
  } catch (err) {
    console.error('Failed to create notification:', err.message);
    return null;
  }
}

// Convenience for alerting several users at once (e.g. every attendee on a
// meeting) without failing the whole batch if one insert fails.
export async function pushNotifications(userIds, payload) {
  const uniqueIds = [...new Set((userIds || []).filter(Boolean).map(String))];
  await Promise.allSettled(uniqueIds.map((userId) => pushNotification({ ...payload, userId })));
}
