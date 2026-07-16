import { Router } from 'express';
import Task from '../models/Task.js';
import User from '../models/User.js';
import { requireAuth } from '../middleware/auth.js';
import { sendTaskAssignedEmail } from '../utils/mailer.js';
import { pushNotification } from '../utils/notify.js';

const router = Router();
router.use(requireAuth);

function toPublicTask(t) {
  return {
    id: t._id,
    title: t.title,
    due: t.due,
    priority: t.priority,
    done: t.done,
    assigneeId: t.assignee ? String(t.assignee._id || t.assignee) : null,
    assignee: t.assignee && t.assignee.name
      ? { id: t.assignee._id, name: t.assignee.name, email: t.assignee.email, seed: t.assignee.email }
      : null,
  };
}

async function notifyAssignee(task, assignerId) {
  if (!task.assignee) return;
  const [assignee, assigner] = await Promise.all([
    User.findById(task.assignee),
    User.findById(assignerId),
  ]);
  if (!assignee) return;
  try {
    await sendTaskAssignedEmail({
      toEmail: assignee.email,
      assigneeName: assignee.name,
      taskTitle: task.title,
      due: task.due,
      priority: task.priority,
      assignerName: assigner?.name,
    });
  } catch (err) {
    console.error('Task assignment email failed:', err.message);
  }

  await pushNotification({
    userId: assignee._id,
    type: 'task_assigned',
    title: 'New task assigned to you',
    message: `${assigner?.name || 'Someone'} assigned you "${task.title}"${task.due ? ` — due ${task.due}` : ''}.`,
    link: '/tasks',
    relatedId: task._id,
  });
}

// ---------- GET /api/tasks ----------
router.get('/', async (req, res) => {
  try {
    const tasks = await Task.find().sort({ createdAt: -1 }).populate('assignee', 'name email');
    res.json({ tasks: tasks.map(toPublicTask) });
  } catch (err) {
    console.error('List tasks failed:', err.message);
    res.status(500).json({ error: 'Could not load tasks.' });
  }
});

// ---------- POST /api/tasks — create + real DB assignment + email the assignee ----------
router.post('/', async (req, res) => {
  try {
    const { title, due, priority, assigneeId } = req.body || {};
    if (!title) return res.status(400).json({ error: 'Title is required.' });

    if (assigneeId) {
      const exists = await User.exists({ _id: assigneeId });
      if (!exists) return res.status(400).json({ error: 'Assignee not found.' });
    }

    const task = await Task.create({
      title,
      due: due || '',
      priority: priority || 'Medium',
      assignee: assigneeId || null,
      createdBy: req.userId,
    });

    await notifyAssignee(task, req.userId);

    const populated = await task.populate('assignee', 'name email');
    res.status(201).json({ task: toPublicTask(populated) });
  } catch (err) {
    console.error('Create task failed:', err.message);
    res.status(500).json({ error: 'Could not create task.' });
  }
});

// ---------- PATCH /api/tasks/:id/toggle ----------
router.patch('/:id/toggle', async (req, res) => {
  try {
    const task = await Task.findById(req.params.id);
    if (!task) return res.status(404).json({ error: 'Task not found.' });

    task.done = !task.done;
    await task.save();

    const populated = await task.populate('assignee', 'name email');
    res.json({ task: toPublicTask(populated) });
  } catch (err) {
    console.error('Toggle task failed:', err.message);
    res.status(500).json({ error: 'Could not update task.' });
  }
});

// ---------- PATCH /api/tasks/:id/assignee — reassign, notifies the new assignee ----------
router.patch('/:id/assignee', async (req, res) => {
  try {
    const { assigneeId } = req.body || {};
    if (!assigneeId) return res.status(400).json({ error: 'assigneeId is required.' });

    const exists = await User.exists({ _id: assigneeId });
    if (!exists) return res.status(400).json({ error: 'Assignee not found.' });

    const task = await Task.findById(req.params.id);
    if (!task) return res.status(404).json({ error: 'Task not found.' });

    task.assignee = assigneeId;
    await task.save();

    await notifyAssignee(task, req.userId);

    const populated = await task.populate('assignee', 'name email');
    res.json({ task: toPublicTask(populated) });
  } catch (err) {
    console.error('Reassign task failed:', err.message);
    res.status(500).json({ error: 'Could not reassign task.' });
  }
});

export default router;
