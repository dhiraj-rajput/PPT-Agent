import mongoose from 'mongoose';

// One attendee on a meeting — either a registered OrbitAvanya user (userId set)
// or an external contact invited by email only (userId left null).
const attendeeSchema = new mongoose.Schema(
  {
    name: { type: String, trim: true, default: '' },
    email: { type: String, trim: true, lowercase: true, required: true },
    userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', default: null },
    inviteSent: { type: Boolean, default: false },
  },
  { _id: false }
);

const meetingSchema = new mongoose.Schema(
  {
    title: { type: String, required: true, trim: true },
    with: { type: String, trim: true, default: '' },
    date: { type: String, required: true }, // YYYY-MM-DD
    time: { type: String, required: true }, // HH:mm
    type: { type: String, enum: ['Video Call', 'In Person'], default: 'Video Call' },

    // Which video provider was used to create the room/call for this meeting.
    provider: { type: String, enum: ['jitsi', 'zoom', 'google_meet', 'in-person'], default: 'jitsi' },
    location: { type: String, trim: true, default: '' },

    // Auto-generated video room/join link for "Video Call" meetings.
    meetingLink: { type: String, trim: true, default: '' },

    // Everyone invited to this meeting — registered users and/or external emails.
    attendees: { type: [attendeeSchema], default: [] },

    status: { type: String, enum: ['scheduled', 'cancelled'], default: 'scheduled' },
    cancelledAt: { type: Date, default: null },

    createdBy: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
  },
  { timestamps: true }
);

export default mongoose.model('Meeting', meetingSchema);
