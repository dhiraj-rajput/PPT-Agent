import nodemailer from 'nodemailer';

const transporter = nodemailer.createTransport({
  service: 'gmail',
  auth: {
    user: process.env.SMTP_USER,
    pass: process.env.SMTP_PASS,
  },
});

const PURPOSE_COPY = {
  register: {
    subject: 'Verify your OrbitAvanya account',
    heading: 'Confirm your email',
    body: 'verify your email and finish creating your account',
  },
  login: {
    subject: 'Your OrbitAvanya sign-in code',
    heading: 'Two-factor verification code',
    body: 'complete your sign-in',
  },
  'reset-password': {
    subject: 'Reset your OrbitAvanya password',
    heading: 'Reset your password',
    body: "verify it's you before choosing a new password",
  },
  'change-password': {
    subject: 'Confirm your OrbitAvanya password change',
    heading: 'Confirm password change',
    body: 'confirm you want to change your account password',
  },
};

export async function sendOtpEmail(toEmail, otp, purpose) {
  const copy = PURPOSE_COPY[purpose] || PURPOSE_COPY.login;
  const { subject, heading } = copy;

  const html = `
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto;">
      <h2 style="color:#111827;">${heading}</h2>
      <p style="color:#374151; font-size: 14px;">
        Use the code below to ${copy.body}.
        This code expires in ${process.env.OTP_TTL_MINUTES || 10} minutes.
      </p>
      <p style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color:#4f46e5; margin: 24px 0;">
        ${otp}
      </p>
      <p style="color:#9ca3af; font-size: 12px;">
        If you didn't request this, you can safely ignore this email.
      </p>
    </div>
  `;

  await transporter.sendMail({
    from: process.env.SMTP_FROM || process.env.SMTP_USER,
    to: toEmail,
    subject,
    html,
  });
}

const CLIENT_URL = process.env.CLIENT_URL || 'http://localhost:5173';

function shell(heading, bodyHtml) {
  return `
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto;">
      <h2 style="color:#111827;">${heading}</h2>
      ${bodyHtml}
      <p style="color:#9ca3af; font-size: 12px; margin-top: 24px;">
        This is an automated message from OrbitAvanya.
      </p>
    </div>
  `;
}

// ---------- Invite a new team member ----------
export async function sendInviteEmail({ toEmail, inviteeName, role, inviterName, tempPassword }) {
  const loginLink = `${CLIENT_URL}/login`;
  const html = shell(
    "You've been invited to OrbitAvanya",
    `
      <p style="color:#374151; font-size: 14px;">
        Hi ${inviteeName || ''}, ${inviterName || 'A teammate'} has invited you to join the
        OrbitAvanya workspace as <strong>${role}</strong>.
      </p>
      <p style="color:#374151; font-size: 14px;">Your temporary sign-in details:</p>
      <p style="font-size: 14px; color:#111827; background:#f3f4f6; padding: 12px 16px; border-radius: 8px;">
        Email: <strong>${toEmail}</strong><br/>
        Temporary password: <strong>${tempPassword}</strong>
      </p>
      <p style="color:#374151; font-size: 14px;">
        Please sign in and change your password from Settings as soon as possible.
      </p>
      <p style="margin: 24px 0;">
        <a href="${loginLink}" style="background:#4f46e5; color:#fff; padding: 10px 20px; border-radius: 8px; text-decoration:none; font-size: 14px; font-weight: bold;">
          Sign in to OrbitAvanya
        </a>
      </p>
      <p style="color:#9ca3af; font-size: 12px;">Or copy this link: ${loginLink}</p>
    `
  );

  await transporter.sendMail({
    from: process.env.SMTP_FROM || process.env.SMTP_USER,
    to: toEmail,
    subject: "You've been invited to join OrbitAvanya",
    html,
  });
}

// ---------- Notify a user they were assigned (or reassigned) a task ----------
export async function sendTaskAssignedEmail({ toEmail, assigneeName, taskTitle, due, priority, assignerName }) {
  const tasksLink = `${CLIENT_URL}/tasks`;
  const html = shell(
    'New task assigned to you',
    `
      <p style="color:#374151; font-size: 14px;">
        Hi ${assigneeName || ''}, ${assignerName || 'a teammate'} assigned you a new task in OrbitAvanya.
      </p>
      <p style="font-size: 14px; color:#111827; background:#f3f4f6; padding: 12px 16px; border-radius: 8px;">
        <strong>${taskTitle}</strong><br/>
        Due: ${due || 'Not set'} &middot; Priority: ${priority || 'Medium'}
      </p>
      <p style="margin: 24px 0;">
        <a href="${tasksLink}" style="background:#4f46e5; color:#fff; padding: 10px 20px; border-radius: 8px; text-decoration:none; font-size: 14px; font-weight: bold;">
          View task in OrbitAvanya
        </a>
      </p>
      <p style="color:#9ca3af; font-size: 12px;">Or copy this link: ${tasksLink}</p>
    `
  );

  await transporter.sendMail({
    from: process.env.SMTP_FROM || process.env.SMTP_USER,
    to: toEmail,
    subject: `New task assigned: ${taskTitle}`,
    html,
  });
}

// ---------- Meeting cancellation notice ----------
export async function sendMeetingCancelledEmail({ toEmail, title, date, time, organizerName }) {
  const html = shell(
    'Meeting cancelled',
    `
      <p style="color:#374151; font-size: 14px;">
        ${organizerName || 'A teammate'} has cancelled the following meeting on OrbitAvanya:
      </p>
      <p style="font-size: 14px; color:#111827; background:#f3f4f6; padding: 12px 16px; border-radius: 8px;">
        <strong>${title}</strong><br/>
        Was scheduled for ${date} at ${time}
      </p>
      <p style="color:#374151; font-size: 14px;">No action is needed on your end.</p>
    `
  );

  await transporter.sendMail({
    from: process.env.SMTP_FROM || process.env.SMTP_USER,
    to: toEmail,
    subject: `Meeting cancelled: ${title} — ${date} ${time}`,
    html,
  });
}
export async function sendMeetingInviteEmail({ toEmail, title, date, time, type, meetingLink, location, organizerName }) {
  const meetingsLink = `${CLIENT_URL}/meetings`;
  const joinBlock =
    type === 'Video Call' && meetingLink
      ? `<p style="margin: 16px 0;">
          <a href="${meetingLink}" style="background:#4f46e5; color:#fff; padding: 10px 20px; border-radius: 8px; text-decoration:none; font-size: 14px; font-weight: bold;">
            Join Video Call
          </a>
        </p>
        <p style="color:#9ca3af; font-size: 12px;">Or copy this link: ${meetingLink}</p>`
      : `<p style="color:#374151; font-size: 14px;">Location: ${location || 'To be confirmed'}</p>`;

  const html = shell(
    'Meeting invitation',
    `
      <p style="color:#374151; font-size: 14px;">
        ${organizerName || 'A teammate'} scheduled a meeting with you on OrbitAvanya.
      </p>
      <p style="font-size: 14px; color:#111827; background:#f3f4f6; padding: 12px 16px; border-radius: 8px;">
        <strong>${title}</strong><br/>
        ${date} at ${time}
      </p>
      ${joinBlock}
      <p style="color:#9ca3af; font-size: 12px;">Full details: ${meetingsLink}</p>
    `
  );

  await transporter.sendMail({
    from: process.env.SMTP_FROM || process.env.SMTP_USER,
    to: toEmail,
    subject: `Meeting invite: ${title} — ${date} ${time}`,
    html,
  });
}
