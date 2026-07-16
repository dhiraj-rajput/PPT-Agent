import { Router } from 'express';
import { requireAuth } from '../middleware/auth.js';
import { getGoogleAuthUrl, handleGoogleCallback, getGoogleConnectionStatus } from '../utils/googleMeet.js';

const router = Router();

const CLIENT_URL = process.env.CLIENT_URL || 'http://localhost:5173';

// ---------- GET /api/integrations/google/status ----------
router.get('/google/status', requireAuth, async (req, res) => {
  try {
    const status = await getGoogleConnectionStatus();
    res.json(status);
  } catch (err) {
    console.error('Google status check failed:', err.message);
    res.status(500).json({ error: 'Could not check Google connection status.' });
  }
});

// ---------- GET /api/integrations/google/auth-url ----------
// Kicks off the one-time consent flow — the admin is redirected to Google,
// then back to /api/integrations/google/callback below.
router.get('/google/auth-url', requireAuth, (req, res) => {
  try {
    res.json({ url: getGoogleAuthUrl() });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ---------- GET /api/integrations/google/callback ----------
// Hit directly by Google's redirect — not by the frontend — so it responds
// with a redirect back into the app rather than JSON.
router.get('/google/callback', async (req, res) => {
  const { code, error } = req.query;
  if (error) {
    return res.redirect(`${CLIENT_URL}/settings/integrations?google=error`);
  }
  try {
    await handleGoogleCallback(code);
    res.redirect(`${CLIENT_URL}/settings/integrations?google=connected`);
  } catch (err) {
    console.error('Google OAuth callback failed:', err.message);
    res.redirect(`${CLIENT_URL}/settings/integrations?google=error`);
  }
});

export default router;
