import { Router } from 'express';
import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';
import rateLimit from 'express-rate-limit';
import User from '../models/User.js';
import { generateOtp, hashOtp, verifyOtp, otpExpiry } from '../utils/otp.js';
import { sendOtpEmail } from '../utils/mailer.js';
import { requireAuth } from '../middleware/auth.js';
import { checkPasswordRules } from '../utils/passwordStrength.js';

const router = Router();
const SALT_ROUNDS = 12;
const MAX_OTP_ATTEMPTS = 5;

// Slow down brute-force guessing on OTP + password endpoints.
const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  limit: 20,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Too many attempts. Please try again later.' },
});
router.use(authLimiter);

function signToken(userId) {
  return jwt.sign({ sub: userId }, process.env.JWT_SECRET, {
    expiresIn: process.env.JWT_EXPIRES_IN || '7d',
  });
}

// Short-lived tokens used to prove "I just verified the OTP" between the
// verify-otp step and the final password-set step, without re-sending a code.
function signActionToken(userId, purpose) {
  return jwt.sign({ sub: userId, purpose }, process.env.JWT_SECRET, {
    expiresIn: '10m',
  });
}

function verifyActionToken(token, purpose) {
  try {
    const payload = jwt.verify(token, process.env.JWT_SECRET);
    if (payload.purpose !== purpose) return null;
    return payload.sub;
  } catch {
    return null;
  }
}

function checkNewPassword(newPassword, confirmPassword) {
  if (!newPassword || !confirmPassword) {
    return 'New password and confirmation are required.';
  }
  if (newPassword !== confirmPassword) {
    return 'Passwords do not match.';
  }
  if (!checkPasswordRules(newPassword).isStrong) {
    return 'Password is too weak. Use at least 8 characters with uppercase, lowercase, a number, and a special character.';
  }
  return null;
}

function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function isValidPhone(phone) {
  // Accepts digits with optional +, spaces, dashes, parentheses; 7-15 digits total.
  const digits = phone.replace(/[^\d]/g, '');
  return /^[\d+\-\s()]+$/.test(phone) && digits.length >= 7 && digits.length <= 15;
}

// ---------- Register (step 1): create pending user, email OTP ----------
router.post('/register', async (req, res) => {
  try {
    const { name, email, phone, password, confirmPassword } = req.body || {};

    if (!name || !email || !phone || !password || !confirmPassword) {
      return res.status(400).json({ error: 'Name, email, phone number, and password are required.' });
    }
    if (!isValidEmail(email)) {
      return res.status(400).json({ error: 'Enter a valid email address.' });
    }
    if (!isValidPhone(phone)) {
      return res.status(400).json({ error: 'Enter a valid phone number.' });
    }
    if (password !== confirmPassword) {
      return res.status(400).json({ error: 'Passwords do not match.' });
    }
    if (!checkPasswordRules(password).isStrong) {
      return res.status(400).json({
        error:
          'Password is too weak. Use at least 8 characters with uppercase, lowercase, a number, and a special character.',
      });
    }

    const normalizedEmail = email.toLowerCase().trim();
    const existing = await User.findOne({ email: normalizedEmail });

    if (existing && existing.isVerified) {
      return res.status(409).json({ error: 'An account with this email already exists.' });
    }

    const passwordHash = await bcrypt.hash(password, SALT_ROUNDS);
    const otp = generateOtp();
    const otpHash = await hashOtp(otp);

    if (existing && !existing.isVerified) {
      // Re-registering before verifying — refresh their details + OTP.
      existing.name = name;
      existing.phone = phone;
      existing.passwordHash = passwordHash;
      existing.otpHash = otpHash;
      existing.otpExpiresAt = otpExpiry();
      existing.otpPurpose = 'register';
      existing.otpAttempts = 0;
      await existing.save();
    } else {
      await User.create({
        name,
        phone,
        email: normalizedEmail,
        passwordHash,
        otpHash,
        otpExpiresAt: otpExpiry(),
        otpPurpose: 'register',
      });
    }

    await sendOtpEmail(normalizedEmail, otp, 'register');

    res.status(201).json({
      message: 'Verification code sent to your email.',
      email: normalizedEmail,
    });
  } catch (err) {
    console.error('register error:', err);
    res.status(500).json({ error: 'Could not create account. Please try again.' });
  }
});

// ---------- Register (step 2): verify email OTP, activate account ----------
router.post('/verify-registration', async (req, res) => {
  try {
    const { email, otp } = req.body || {};
    if (!email || !otp) {
      return res.status(400).json({ error: 'Email and code are required.' });
    }

    const user = await User.findOne({ email: email.toLowerCase().trim() });
    if (!user || user.otpPurpose !== 'register') {
      return res.status(400).json({ error: 'No pending registration for this email.' });
    }
    if (user.isVerified) {
      return res.status(400).json({ error: 'This account is already verified.' });
    }
    if (!user.otpExpiresAt || user.otpExpiresAt < new Date()) {
      return res.status(400).json({ error: 'Code expired. Please request a new one.' });
    }
    if (user.otpAttempts >= MAX_OTP_ATTEMPTS) {
      return res.status(429).json({ error: 'Too many incorrect attempts. Request a new code.' });
    }

    const ok = await verifyOtp(otp, user.otpHash);
    if (!ok) {
      user.otpAttempts += 1;
      await user.save();
      return res.status(400).json({ error: 'Incorrect code.' });
    }

    user.isVerified = true;
    user.otpHash = null;
    user.otpExpiresAt = null;
    user.otpPurpose = null;
    user.otpAttempts = 0;
    await user.save();

    const token = signToken(user._id.toString());
    res.json({
      message: 'Account verified.',
      token,
      user: { id: user._id, name: user.name, email: user.email, phone: user.phone, role: user.role, company: user.company, timezone: user.timezone },
    });
  } catch (err) {
    console.error('verify-registration error:', err);
    res.status(500).json({ error: 'Verification failed. Please try again.' });
  }
});

// ---------- Login (step 1): check password, email OTP for 2FA ----------
router.post('/login', async (req, res) => {
  try {
    const { email, password } = req.body || {};
    if (!email || !password) {
      return res.status(400).json({ error: 'Email and password are required.' });
    }

    const user = await User.findOne({ email: email.toLowerCase().trim() });

    // Same generic error whether the email exists or the password is wrong,
    // so login can't be used to enumerate registered accounts.
    const genericError = { error: 'Invalid email or password.' };
    if (!user) return res.status(401).json(genericError);

    const passwordOk = await bcrypt.compare(password, user.passwordHash);
    if (!passwordOk) return res.status(401).json(genericError);

    if (!user.isVerified) {
      return res.status(403).json({ error: 'Please verify your email before signing in.' });
    }

    const otp = generateOtp();
    user.otpHash = await hashOtp(otp);
    user.otpExpiresAt = otpExpiry();
    user.otpPurpose = 'login';
    user.otpAttempts = 0;
    await user.save();

    await sendOtpEmail(user.email, otp, 'login');

    res.json({
      message: 'Verification code sent to your email.',
      email: user.email,
      requiresOtp: true,
    });
  } catch (err) {
    console.error('login error:', err);
    res.status(500).json({ error: 'Login failed. Please try again.' });
  }
});

// ---------- Login (step 2): verify OTP, issue session token ----------
router.post('/verify-login', async (req, res) => {
  try {
    const { email, otp } = req.body || {};
    if (!email || !otp) {
      return res.status(400).json({ error: 'Email and code are required.' });
    }

    const user = await User.findOne({ email: email.toLowerCase().trim() });
    if (!user || user.otpPurpose !== 'login') {
      return res.status(400).json({ error: 'No pending sign-in for this email.' });
    }
    if (!user.otpExpiresAt || user.otpExpiresAt < new Date()) {
      return res.status(400).json({ error: 'Code expired. Please sign in again.' });
    }
    if (user.otpAttempts >= MAX_OTP_ATTEMPTS) {
      return res.status(429).json({ error: 'Too many incorrect attempts. Sign in again.' });
    }

    const ok = await verifyOtp(otp, user.otpHash);
    if (!ok) {
      user.otpAttempts += 1;
      await user.save();
      return res.status(400).json({ error: 'Incorrect code.' });
    }

    user.otpHash = null;
    user.otpExpiresAt = null;
    user.otpPurpose = null;
    user.otpAttempts = 0;
    user.lastLoginAt = new Date();
    await user.save();

    const token = signToken(user._id.toString());
    res.json({
      message: 'Signed in.',
      token,
      user: {
        id: user._id,
        name: user.name,
        email: user.email,
        phone: user.phone,
        role: user.role,
        company: user.company,
        timezone: user.timezone,
        mustChangePassword: user.mustChangePassword,
      },
    });
  } catch (err) {
    console.error('verify-login error:', err);
    res.status(500).json({ error: 'Verification failed. Please try again.' });
  }
});

// ---------- Resend OTP (works for either pending purpose) ----------
router.post('/resend-otp', async (req, res) => {
  try {
    const { email } = req.body || {};
    if (!email) return res.status(400).json({ error: 'Email is required.' });

    const user = await User.findOne({ email: email.toLowerCase().trim() });
    if (!user || !user.otpPurpose) {
      return res.status(400).json({ error: 'Nothing pending for this email.' });
    }

    const otp = generateOtp();
    user.otpHash = await hashOtp(otp);
    user.otpExpiresAt = otpExpiry();
    user.otpAttempts = 0;
    await user.save();

    await sendOtpEmail(user.email, otp, user.otpPurpose);
    res.json({ message: 'A new code has been sent.' });
  } catch (err) {
    console.error('resend-otp error:', err);
    res.status(500).json({ error: 'Could not resend code.' });
  }
});

// ---------- Current user ----------
router.get('/me', requireAuth, async (req, res) => {
  const user = await User.findById(req.userId).select(
    'name email phone role company timezone createdAt lastLoginAt mustChangePassword'
  );
  if (!user) return res.status(404).json({ error: 'User not found.' });
  res.json({ user });
});

// ---------- Update profile (Settings page) ----------
// Email is intentionally not editable here — changing it would require its
// own re-verification flow, which is out of scope for this endpoint.
router.put('/profile', requireAuth, async (req, res) => {
  try {
    const { name, phone, role, company, timezone } = req.body || {};

    if (name !== undefined && !String(name).trim()) {
      return res.status(400).json({ error: 'Name cannot be empty.' });
    }
    if (phone !== undefined && !isValidPhone(phone)) {
      return res.status(400).json({ error: 'Enter a valid phone number.' });
    }

    const user = await User.findById(req.userId);
    if (!user) return res.status(404).json({ error: 'User not found.' });

    if (name !== undefined) user.name = String(name).trim();
    if (phone !== undefined) user.phone = String(phone).trim();
    if (role !== undefined) user.role = String(role).trim();
    if (company !== undefined) user.company = String(company).trim();
    if (timezone !== undefined) user.timezone = String(timezone).trim();

    await user.save();

    res.json({
      message: 'Profile updated.',
      user: {
        id: user._id,
        name: user.name,
        email: user.email,
        phone: user.phone,
        role: user.role,
        company: user.company,
        timezone: user.timezone,
      },
    });
  } catch (err) {
    console.error('update profile error:', err);
    res.status(500).json({ error: 'Could not update profile. Please try again.' });
  }
});

// ============================================================
// Forgot password (unauthenticated — from the Login page)
// Step 1: request an OTP  Step 2: verify it  Step 3: set a new password
// ============================================================

// ---------- Forgot password (step 1): email OTP if the account exists ----------
router.post('/forgot-password', async (req, res) => {
  try {
    const { email } = req.body || {};
    if (!email || !isValidEmail(email)) {
      return res.status(400).json({ error: 'Enter a valid email address.' });
    }

    const normalizedEmail = email.toLowerCase().trim();
    const user = await User.findOne({ email: normalizedEmail });

    // Always return the same generic response, whether or not the account
    // exists, so this endpoint can't be used to enumerate registered emails.
    const genericResponse = {
      message: 'If an account exists for that email, a verification code has been sent.',
    };

    if (!user || !user.isVerified) {
      return res.json(genericResponse);
    }

    const otp = generateOtp();
    user.otpHash = await hashOtp(otp);
    user.otpExpiresAt = otpExpiry();
    user.otpPurpose = 'reset-password';
    user.otpAttempts = 0;
    await user.save();

    await sendOtpEmail(user.email, otp, 'reset-password');

    res.json(genericResponse);
  } catch (err) {
    console.error('forgot-password error:', err);
    res.status(500).json({ error: 'Could not process request. Please try again.' });
  }
});

// ---------- Forgot password (step 2): verify OTP, issue a short-lived reset token ----------
router.post('/verify-reset-otp', async (req, res) => {
  try {
    const { email, otp } = req.body || {};
    if (!email || !otp) {
      return res.status(400).json({ error: 'Email and code are required.' });
    }

    const user = await User.findOne({ email: email.toLowerCase().trim() });
    if (!user || user.otpPurpose !== 'reset-password') {
      return res.status(400).json({ error: 'No pending password reset for this email.' });
    }
    if (!user.otpExpiresAt || user.otpExpiresAt < new Date()) {
      return res.status(400).json({ error: 'Code expired. Please request a new one.' });
    }
    if (user.otpAttempts >= MAX_OTP_ATTEMPTS) {
      return res.status(429).json({ error: 'Too many incorrect attempts. Request a new code.' });
    }

    const ok = await verifyOtp(otp, user.otpHash);
    if (!ok) {
      user.otpAttempts += 1;
      await user.save();
      return res.status(400).json({ error: 'Incorrect code.' });
    }

    // OTP confirmed — clear it so it can't be reused, and hand back a
    // short-lived token that authorizes exactly one password reset.
    user.otpHash = null;
    user.otpExpiresAt = null;
    user.otpPurpose = null;
    user.otpAttempts = 0;
    await user.save();

    const resetToken = signActionToken(user._id.toString(), 'reset-password');
    res.json({ message: 'Code verified.', resetToken });
  } catch (err) {
    console.error('verify-reset-otp error:', err);
    res.status(500).json({ error: 'Verification failed. Please try again.' });
  }
});

// ---------- Forgot password (step 3): set new password, sign the user in ----------
router.post('/reset-password', async (req, res) => {
  try {
    const { resetToken, newPassword, confirmPassword } = req.body || {};
    if (!resetToken) {
      return res.status(400).json({ error: 'Missing or expired reset session. Please start over.' });
    }

    const passwordError = checkNewPassword(newPassword, confirmPassword);
    if (passwordError) {
      return res.status(400).json({ error: passwordError });
    }

    const userId = verifyActionToken(resetToken, 'reset-password');
    if (!userId) {
      return res.status(400).json({ error: 'This reset link has expired. Please start over.' });
    }

    const user = await User.findById(userId);
    if (!user) return res.status(404).json({ error: 'User not found.' });

    user.passwordHash = await bcrypt.hash(newPassword, SALT_ROUNDS);
    // Belt-and-suspenders: make sure no OTP state lingers after a reset.
    user.otpHash = null;
    user.otpExpiresAt = null;
    user.otpPurpose = null;
    user.otpAttempts = 0;
    await user.save();

    const token = signToken(user._id.toString());
    res.json({
      message: 'Password updated. You are now signed in.',
      token,
      user: {
        id: user._id,
        name: user.name,
        email: user.email,
        phone: user.phone,
        role: user.role,
        company: user.company,
        timezone: user.timezone,
      },
    });
  } catch (err) {
    console.error('reset-password error:', err);
    res.status(500).json({ error: 'Could not reset password. Please try again.' });
  }
});

// ============================================================
// Change password (authenticated — from the Settings page)
// Step 1: request an OTP to the account's own email
// Step 2: verify it   Step 3: set the new password
// ============================================================

// ---------- Change password (step 1): email OTP to the signed-in user ----------
router.post('/change-password/request-otp', requireAuth, async (req, res) => {
  try {
    const user = await User.findById(req.userId);
    if (!user) return res.status(404).json({ error: 'User not found.' });

    const otp = generateOtp();
    user.otpHash = await hashOtp(otp);
    user.otpExpiresAt = otpExpiry();
    user.otpPurpose = 'change-password';
    user.otpAttempts = 0;
    await user.save();

    await sendOtpEmail(user.email, otp, 'change-password');

    res.json({ message: 'Verification code sent to your email.', email: user.email });
  } catch (err) {
    console.error('change-password request-otp error:', err);
    res.status(500).json({ error: 'Could not send verification code. Please try again.' });
  }
});

// ---------- Change password (step 2): verify OTP, issue a short-lived change token ----------
router.post('/change-password/verify-otp', requireAuth, async (req, res) => {
  try {
    const { otp } = req.body || {};
    if (!otp) return res.status(400).json({ error: 'Code is required.' });

    const user = await User.findById(req.userId);
    if (!user || user.otpPurpose !== 'change-password') {
      return res.status(400).json({ error: 'No pending password change. Please request a new code.' });
    }
    if (!user.otpExpiresAt || user.otpExpiresAt < new Date()) {
      return res.status(400).json({ error: 'Code expired. Please request a new one.' });
    }
    if (user.otpAttempts >= MAX_OTP_ATTEMPTS) {
      return res.status(429).json({ error: 'Too many incorrect attempts. Request a new code.' });
    }

    const ok = await verifyOtp(otp, user.otpHash);
    if (!ok) {
      user.otpAttempts += 1;
      await user.save();
      return res.status(400).json({ error: 'Incorrect code.' });
    }

    user.otpHash = null;
    user.otpExpiresAt = null;
    user.otpPurpose = null;
    user.otpAttempts = 0;
    await user.save();

    const changeToken = signActionToken(user._id.toString(), 'change-password');
    res.json({ message: 'Code verified.', changeToken });
  } catch (err) {
    console.error('change-password verify-otp error:', err);
    res.status(500).json({ error: 'Verification failed. Please try again.' });
  }
});

// ---------- Change password (step 3): set the new password ----------
router.post('/change-password/confirm', requireAuth, async (req, res) => {
  try {
    const { changeToken, newPassword, confirmPassword } = req.body || {};
    if (!changeToken) {
      return res.status(400).json({ error: 'Missing or expired verification. Please start over.' });
    }

    const passwordError = checkNewPassword(newPassword, confirmPassword);
    if (passwordError) {
      return res.status(400).json({ error: passwordError });
    }

    const userId = verifyActionToken(changeToken, 'change-password');
    if (!userId || userId !== req.userId) {
      return res.status(400).json({ error: 'Verification expired. Please start over.' });
    }

    const user = await User.findById(userId);
    if (!user) return res.status(404).json({ error: 'User not found.' });

    const sameAsOld = await bcrypt.compare(newPassword, user.passwordHash);
    if (sameAsOld) {
      return res.status(400).json({ error: 'New password must be different from your current password.' });
    }

    user.passwordHash = await bcrypt.hash(newPassword, SALT_ROUNDS);
    user.otpHash = null;
    user.otpExpiresAt = null;
    user.otpPurpose = null;
    user.otpAttempts = 0;
    await user.save();

    res.json({ message: 'Password updated successfully.' });
  } catch (err) {
    console.error('change-password confirm error:', err);
    res.status(500).json({ error: 'Could not update password. Please try again.' });
  }
});

// ============================================================
// Force change password (authenticated — required right after an
// invited user's first login, while mustChangePassword is still true).
// No OTP needed here: the user already proved identity via the
// login + OTP flow moments earlier.
// ============================================================
router.post('/force-change-password', requireAuth, async (req, res) => {
  try {
    const user = await User.findById(req.userId);
    if (!user) return res.status(404).json({ error: 'User not found.' });

    if (!user.mustChangePassword) {
      return res.status(400).json({ error: 'No pending password change for this account.' });
    }

    const { newPassword, confirmPassword } = req.body || {};
    const passwordError = checkNewPassword(newPassword, confirmPassword);
    if (passwordError) {
      return res.status(400).json({ error: passwordError });
    }

    user.passwordHash = await bcrypt.hash(newPassword, SALT_ROUNDS);
    user.mustChangePassword = false;
    await user.save();

    res.json({
      message: 'Password updated. You can now use your new password.',
      user: {
        id: user._id,
        name: user.name,
        email: user.email,
        phone: user.phone,
        role: user.role,
        company: user.company,
        timezone: user.timezone,
        mustChangePassword: user.mustChangePassword,
      },
    });
  } catch (err) {
    console.error('force-change-password error:', err);
    res.status(500).json({ error: 'Could not update password. Please try again.' });
  }
});

export default router;
