import mongoose from 'mongoose';

// Singleton-per-key settings doc. Currently used to hold the Google OAuth
// refresh token obtained the one time an admin clicks "Connect Google" in
// Settings > Integrations — Calendar/Meet events are then created on behalf
// of that connected account for every future meeting.
const integrationSchema = new mongoose.Schema(
  {
    key: { type: String, required: true, unique: true }, // e.g. 'google'
    connectedEmail: { type: String, trim: true, default: '' },
    refreshToken: { type: String, default: '' },
    connectedAt: { type: Date, default: null },
  },
  { timestamps: true }
);

export default mongoose.model('Integration', integrationSchema);
