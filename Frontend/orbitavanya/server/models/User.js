import mongoose from 'mongoose';

const userSchema = new mongoose.Schema(
  {
    name: { type: String, required: true, trim: true },
    // Not required: users created via the "Invite User" flow don't supply a phone
    // number up front — they can fill it in later from Settings.
    phone: { type: String, trim: true, default: '' },
    email: {
      type: String,
      required: true,
      unique: true,
      lowercase: true,
      trim: true,
      index: true,
    },
    // Never store the plaintext password — only the bcrypt hash.
    passwordHash: { type: String, required: true },

    isVerified: { type: Boolean, default: false },

    // Extra profile fields shown/edited on the Settings page.
    role: { type: String, trim: true, default: 'Admin' },
    company: { type: String, trim: true, default: 'OrbitAvanya Tech' },
    timezone: { type: String, trim: true, default: 'America/Chicago' },

    // OTP is stored as a bcrypt hash too, never in plaintext, so a DB read
    // alone can't be used to log in or complete registration.
    otpHash: { type: String, default: null },
    otpExpiresAt: { type: Date, default: null },
    otpPurpose: {
      type: String,
      enum: ['register', 'login', 'reset-password', 'change-password', null],
      default: null,
    },
    otpAttempts: { type: Number, default: 0 },

    lastLoginAt: { type: Date, default: null },

    // Set when this account was created through the Users & Roles "Invite User"
    // flow instead of self-registration.
    invitedBy: { type: mongoose.Schema.Types.ObjectId, ref: 'User', default: null },
    mustChangePassword: { type: Boolean, default: false },
  },
  { timestamps: true }
);

export default mongoose.model('User', userSchema);
