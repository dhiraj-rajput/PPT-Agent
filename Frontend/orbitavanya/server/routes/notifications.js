import { Router } from 'express';
import Notification from '../models/Notification.js';
import User from '../models/User.js';
import { requireAuth } from '../middleware/auth.js';
import { pushNotification } from '../utils/notify.js';

const router = Router();
router.use(requireAuth);

function toPublicNotification(n) {
  return {
    id: n._id,
    type: n.type,
    title: n.title,
    message: n.message,
    link: n.link,
    relatedId: n.relatedId,
    read: n.read,
    createdAt: n.createdAt,
  };
}

// ---------- GET /api/notifications — latest alerts for the signed-in user ----------
router.get('/', async (req, res) => {
  try {
    const notifications = await Notification.find({ user: req.userId })
      .sort({ createdAt: -1 })
      .limit(50);
    const unreadCount = await Notification.countDocuments({ user: req.userId, read: false });
    res.json({ notifications: notifications.map(toPublicNotification), unreadCount });
  } catch (err) {
    console.error('List notifications failed:', err.message);
    res.status(500).json({ error: 'Could not load notifications.' });
  }
});

// ---------- POST /api/notifications — create a custom alert ----------
// Lets any signed-in user raise their own reminder/alert, or notify a
// specific teammate about anything that isn't a meeting/task event.
router.post('/', async (req, res) => {
  try {
    const { title, message, link, userId } = req.body || {};
    if (!title) return res.status(400).json({ error: 'Title is required.' });

    let targetId = req.userId;
    if (userId) {
      const exists = await User.exists({ _id: userId });
      if (!exists) return res.status(400).json({ error: 'Target user not found.' });
      targetId = userId;
    }

    const notification = await pushNotification({
      userId: targetId,
      type: 'custom',
      title,
      message: message || '',
      link: link || '',
    });

    if (!notification) return res.status(500).json({ error: 'Could not create alert.' });
    res.status(201).json({ notification: toPublicNotification(notification) });
  } catch (err) {
    console.error('Create notification failed:', err.message);
    res.status(500).json({ error: 'Could not create alert.' });
  }
});

// ---------- PATCH /api/notifications/read-all ----------
router.patch('/read-all', async (req, res) => {
  try {
    await Notification.updateMany({ user: req.userId, read: false }, { $set: { read: true } });
    res.json({ ok: true });
  } catch (err) {
    console.error('Mark all read failed:', err.message);
    res.status(500).json({ error: 'Could not update alerts.' });
  }
});

// ---------- PATCH /api/notifications/:id/read ----------
router.patch('/:id/read', async (req, res) => {
  try {
    const notification = await Notification.findOneAndUpdate(
      { _id: req.params.id, user: req.userId },
      { $set: { read: true } },
      { new: true }
    );
    if (!notification) return res.status(404).json({ error: 'Alert not found.' });
    res.json({ notification: toPublicNotification(notification) });
  } catch (err) {
    console.error('Mark read failed:', err.message);
    res.status(500).json({ error: 'Could not update alert.' });
  }
});

// ---------- DELETE /api/notifications/:id ----------
router.delete('/:id', async (req, res) => {
  try {
    const result = await Notification.findOneAndDelete({ _id: req.params.id, user: req.userId });
    if (!result) return res.status(404).json({ error: 'Alert not found.' });
    res.json({ ok: true });
  } catch (err) {
    console.error('Delete notification failed:', err.message);
    res.status(500).json({ error: 'Could not delete alert.' });
  }
});

export default router;
