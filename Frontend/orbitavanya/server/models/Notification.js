import mongoose from 'mongoose';

// In-app alert shown in the Topbar bell dropdown. Created automatically when
// a meeting is scheduled/cancelled or a task is assigned, and can also be
// created manually (custom / "any other alert") via POST /api/notifications.
const notificationSchema = new mongoose.Schema(
  {
    // Who should see this alert.
    user: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true, index: true },

    type: {
      type: String,
      enum: ['meeting_scheduled', 'meeting_cancelled', 'task_assigned', 'custom'],
      default: 'custom',
    },

    title: { type: String, required: true, trim: true },
    message: { type: String, trim: true, default: '' },

    // Optional deep-link so clicking the alert can take the user to the
    // relevant page (e.g. /meetings or /tasks).
    link: { type: String, trim: true, default: '' },

    // Loosely tied to the source document (Meeting / Task id) for reference.
    relatedId: { type: mongoose.Schema.Types.ObjectId, default: null },

    read: { type: Boolean, default: false },
  },
  { timestamps: true }
);

notificationSchema.index({ user: 1, createdAt: -1 });

export default mongoose.model('Notification', notificationSchema);
