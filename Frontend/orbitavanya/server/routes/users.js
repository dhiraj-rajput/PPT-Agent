import { Router } from 'express';
import crypto from 'crypto';
import bcrypt from 'bcrypt';
import User from '../models/User.js';
import { requireAuth } from '../middleware/auth.js';
import { sendInviteEmail } from '../utils/mailer.js';

const router = Router();
const SALT_ROUNDS = 12;

router.use(requireAuth);

function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function toPublicUser(u) {
  return {
    id: u._id,
    name: u.name,
    email: u.email,
    role: u.role,
    status: u.isVerified ? 'Active' : 'Pending',
    seed: u.email,
    createdAt: u.createdAt,
  };
}

// ---------- GET /api/users — real data straight from MongoDB ----------
router.get('/', async (req, res) => {
  try {
    const users = await User.find().sort({ createdAt: -1 });
    res.json({ users: users.map(toPublicUser) });
  } catch (err) {
    console.error('List users failed:', err.message);
    res.status(500).json({ error: 'Could not load users.' });
  }
});

// ---------- POST /api/users/invite — create the account + email them in ----------
router.post('/invite', async (req, res) => {
  try {
    const { name, email, role } = req.body || {};

    if (!email || !isValidEmail(email)) {
      return res.status(400).json({ error: 'A valid email address is required.' });
    }

    const existing = await User.findOne({ email: email.toLowerCase().trim() });
    if (existing) {
      return res.status(409).json({ error: 'A user with that email already exists.' });
    }

    const inviter = await User.findById(req.userId);

    // Random one-time password; the invitee is required to change it on first login.
    const tempPassword = crypto.randomBytes(9).toString('base64url');
    const passwordHash = await bcrypt.hash(tempPassword, SALT_ROUNDS);

    const user = await User.create({
      name: name?.trim() || email.split('@')[0],
      email: email.toLowerCase().trim(),
      phone: '',
      passwordHash,
      isVerified: true,
      role: role?.trim() || 'Team Member',
      invitedBy: inviter?._id || null,
      mustChangePassword: true,
    });

    try {
      await sendInviteEmail({
        toEmail: user.email,
        inviteeName: user.name,
        role: user.role,
        inviterName: inviter?.name,
        tempPassword,
      });
    } catch (mailErr) {
      console.error('Invite email failed to send:', mailErr.message);
      // The account was still created — surface this so the admin can resend/share manually.
      return res.status(201).json({
        user: toPublicUser(user),
        warning: 'User created, but the invite email could not be sent. Check SMTP settings.',
      });
    }

    res.status(201).json({ user: toPublicUser(user) });
  } catch (err) {
    console.error('Invite user failed:', err.message);
    res.status(500).json({ error: 'Could not invite user.' });
  }
});

// ---------- PATCH /api/users/:id/role — change a user's role ----------
router.patch('/:id/role', async (req, res) => {
  try {
    const { role } = req.body || {};
    if (!role) return res.status(400).json({ error: 'Role is required.' });

    const user = await User.findByIdAndUpdate(req.params.id, { role }, { new: true });
    if (!user) return res.status(404).json({ error: 'User not found.' });

    res.json({ user: toPublicUser(user) });
  } catch (err) {
    console.error('Update role failed:', err.message);
    res.status(500).json({ error: 'Could not update role.' });
  }
});

export default router;
