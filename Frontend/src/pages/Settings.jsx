import { useState, useRef } from 'react';
import { Check, X, Loader2, ShieldCheck, KeyRound, Camera } from 'lucide-react';
import { PageHeader, Card } from '../components/ui/Common.jsx';
import { useAuth } from '../context/AuthContext.jsx';
import { useNotifications } from '../context/NotificationContext.jsx';
import { api } from '../lib/api.jsx';
import { checkPasswordRules } from '../lib/passwordStrength.jsx';
import PasswordStrengthMeter from '../components/ui/PasswordStrengthMeter.jsx';

const TIMEZONES = typeof Intl !== 'undefined' && Intl.supportedValuesOf
  ? Intl.supportedValuesOf('timeZone')
  : ['UTC', 'America/New_York', 'America/Chicago', 'America/Los_Angeles',
     'Europe/London', 'Europe/Paris', 'Asia/Kolkata', 'Asia/Tokyo', 'Australia/Sydney'];

function AvatarCard() {
  const { user, updateUser } = useAuth();
  const { createAlert } = useNotifications();
  const notify = (title, message, link) => createAlert(title, message, link).catch(() => {});
  const name = user?.name || '';
  const email = user?.email || '';

  const fileInputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState('');

  const avatarSrc =
    preview ||
    (user?.avatarUrl
      ? api.getAvatarUrl(user.avatarUrl)
      : api.getInitialsAvatar(name || email || 'User'));

  function handlePickPhoto() {
    setError('');
    fileInputRef.current?.click();
  }

  async function handleFileSelected(e) {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-selecting the same file later
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      setError('Please choose an image file.');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setError('Image is too large. Max size is 5MB.');
      return;
    }

    setError('');
    const localUrl = URL.createObjectURL(file);
    setPreview(localUrl);
    setUploading(true);
    try {
      const { user: updated } = await api.uploadAvatar(file);
      updateUser(updated);
      notify('Profile photo updated', 'Your new profile photo has been assigned to your account.', '/settings');
    } catch (err) {
      setError(err.message || 'Failed to upload photo.');
      setPreview('');
    } finally {
      setUploading(false);
      URL.revokeObjectURL(localUrl);
    }
  }

  return (
    <Card className="lg:col-span-1">
      <div className="flex flex-col items-center text-center">
        <div className="relative">
          <img
            src={avatarSrc}
            className="h-20 w-20 rounded-full border border-slate-200 object-cover dark:border-navy-700"
            alt={name || 'User'}
          />
          {uploading && (
            <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/40">
              <Loader2 size={18} className="animate-spin text-white" />
            </div>
          )}
        </div>
        <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">{name}</p>
        <p className="text-xs text-slate-400 dark:text-slate-500">{email}</p>

        <input
          ref={fileInputRef}
          type="file"
          accept="image/png, image/jpeg, image/gif, image/webp"
          onChange={handleFileSelected}
          className="hidden"
        />
        <button
          type="button"
          onClick={handlePickPhoto}
          disabled={uploading}
          className="mt-4 flex w-full items-center justify-center gap-1.5 rounded-lg border border-slate-200 dark:border-navy-700 py-2 text-xs font-semibold text-navy-900 dark:text-white hover:bg-slate-50 dark:hover:bg-navy-800 disabled:opacity-60"
        >
          <Camera size={13} />
          {uploading ? 'Uploading…' : 'Change Photo'}
        </button>
        {error && <p className="mt-2 text-xs font-medium text-tomato-600">{error}</p>}
      </div>
    </Card>
  );
}

function ProfileCard() {
  const { user, updateUser } = useAuth();
  const { createAlert } = useNotifications();
  const notify = (title, message, link) => createAlert(title, message, link).catch(() => {});

  const [form, setForm] = useState({
    name: user?.name || '',
    phone: user?.phone || '',
    role: user?.role || 'Admin',
    company: user?.company || 'OrbitAvanya Tech',
    timezone: user?.timezone || 'America/Chicago',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  function handleChange(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
    setSuccess('');
  }

  async function handleSave(e) {
    e.preventDefault();
    setError('');
    setSuccess('');
    setSaving(true);
    try {
      const { user: updated } = await api.updateProfile(form);
      updateUser(updated);
      setSuccess('Profile updated successfully.');
      notify('Profile updated', 'Your account details were changed.', '/settings');
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="lg:col-span-2">
      <h3 className="text-sm font-bold text-navy-900 dark:text-white">Profile Information</h3>

      {error && (
        <div className="mt-3 rounded-lg bg-tomato-50 px-3.5 py-2.5 text-sm text-tomato-700">{error}</div>
      )}
      {success && (
        <div className="mt-3 flex items-center gap-1.5 rounded-lg bg-emerald-50 px-3.5 py-2.5 text-sm text-emerald-700">
          <Check size={14} /> {success}
        </div>
      )}

      <form onSubmit={handleSave} className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1.5 block text-xs font-semibold text-slate-500 dark:text-slate-400">Full Name</label>
          <input
            value={form.name}
            onChange={(e) => handleChange('name', e.target.value)}
            required
            className="w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-semibold text-slate-500 dark:text-slate-400">Email</label>
          <input
            value={user?.email || ''}
            disabled
            title="Email can't be changed here."
            className="w-full cursor-not-allowed rounded-xl border border-slate-200 dark:border-navy-700 bg-slate-50 dark:bg-navy-800/60 px-3.5 py-2.5 text-sm text-slate-500 dark:text-slate-400"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-semibold text-slate-500 dark:text-slate-400">Phone</label>
          <input
            type="tel"
            value={form.phone}
            onChange={(e) => handleChange('phone', e.target.value)}
            placeholder="+91 98765 43210"
            required
            className="w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-semibold text-slate-500 dark:text-slate-400">Role</label>
          <input
            value={form.role}
            onChange={(e) => handleChange('role', e.target.value)}
            className="w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-semibold text-slate-500 dark:text-slate-400">Company</label>
          <input
            value={form.company}
            onChange={(e) => handleChange('company', e.target.value)}
            className="w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-semibold text-slate-500 dark:text-slate-400">Timezone</label>
          <select
            value={form.timezone}
            onChange={(e) => handleChange('timezone', e.target.value)}
            className="w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500"
          >
            {TIMEZONES.map((tz) => (
              <option key={tz} value={tz}>
                {tz}
              </option>
            ))}
          </select>
        </div>

        <div className="sm:col-span-2">
          <button
            type="submit"
            disabled={saving}
            className="mt-1 flex items-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 text-sm font-bold text-white shadow-soft transition-colors hover:bg-brand-600 disabled:opacity-60"
          >
            {saving && <Loader2 size={15} className="animate-spin" />}
            {saving ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      </form>
    </Card>
  );
}

function ChangePasswordCard() {
  const { createAlert } = useNotifications();
  const notify = (title, message, link) => createAlert(title, message, link).catch(() => {});
  // step: 'idle' | 'verify' | 'done'
  const [step, setStep] = useState('idle');
  const [otp, setOtp] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [sendingOtp, setSendingOtp] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);

  const { isStrong } = checkPasswordRules(newPassword);
  const passwordsMatch = confirmPassword.length > 0 && newPassword === confirmPassword;

  function resetState() {
    setStep('idle');
    setOtp('');
    setNewPassword('');
    setConfirmPassword('');
    setError('');
    setInfo('');
  }

  async function handleStart() {
    setError('');
    setInfo('');
    setSendingOtp(true);
    try {
      await api.requestChangePasswordOtp();
      setStep('verify');
      setInfo('A verification code has been sent to your email.');
    } catch (err) {
      setError(err.message);
    } finally {
      setSendingOtp(false);
    }
  }

  async function handleResend() {
    setError('');
    setInfo('');
    setResending(true);
    try {
      await api.requestChangePasswordOtp();
      setInfo('A new code has been sent to your email.');
    } catch (err) {
      setError(err.message);
    } finally {
      setResending(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setInfo('');

    if (!isStrong) {
      setError('Please choose a stronger password before continuing.');
      return;
    }
    if (!passwordsMatch) {
      setError('Passwords do not match.');
      return;
    }

    setSubmitting(true);
    try {
      const { changeToken } = await api.verifyChangePasswordOtp(otp);
      await api.confirmChangePassword(changeToken, newPassword, confirmPassword);
      setStep('done');
      notify('Password changed', 'Your account password was updated.', '/settings');
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="lg:col-span-3">
      <div className="flex items-center gap-2.5">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-50">
          <KeyRound size={16} className="text-brand-600" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-navy-900 dark:text-white">Change Password</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            We'll email a verification code before your password can be changed.
          </p>
        </div>
      </div>

      {error && (
        <div className="mt-4 rounded-lg bg-tomato-50 px-3.5 py-2.5 text-sm text-tomato-700">{error}</div>
      )}
      {info && step !== 'done' && (
        <div className="mt-4 rounded-lg bg-pacific-blue-50 px-3.5 py-2.5 text-sm text-pacific-blue-700">
          {info}
        </div>
      )}

      {step === 'idle' && (
        <button
          onClick={handleStart}
          disabled={sendingOtp}
          className="mt-4 flex items-center gap-2 rounded-xl border border-slate-200 dark:border-navy-700 px-5 py-2.5 text-sm font-bold text-navy-900 dark:text-white transition-colors hover:bg-slate-50 dark:hover:bg-navy-800 disabled:opacity-60"
        >
          {sendingOtp && <Loader2 size={15} className="animate-spin" />}
          {sendingOtp ? 'Sending code…' : 'Change Password'}
        </button>
      )}

      {step === 'verify' && (
        <form onSubmit={handleSubmit} className="mt-4 flex max-w-md flex-col gap-4">
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-slate-500 dark:text-slate-400">Verification code</label>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={6}
              required
              value={otp}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
              placeholder="000000"
              className="w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-4 py-2.5 text-center text-xl font-bold tracking-[0.4em] outline-none focus:border-brand-500"
            />
            <button
              type="button"
              onClick={handleResend}
              disabled={resending}
              className="mt-1.5 text-xs font-semibold text-brand-600 disabled:opacity-60"
            >
              {resending ? 'Sending…' : "Didn't get a code? Resend"}
            </button>
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-semibold text-slate-500 dark:text-slate-400">New password</label>
            <input
              type="password"
              required
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500"
            />
            <PasswordStrengthMeter password={newPassword} />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-semibold text-slate-500 dark:text-slate-400">Confirm new password</label>
            <input
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className={`w-full rounded-xl border bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500 ${
                confirmPassword && !passwordsMatch ? 'border-tomato-300' : 'border-slate-200 dark:border-navy-700'
              }`}
            />
            {confirmPassword && !passwordsMatch && (
              <p className="mt-1.5 text-xs font-medium text-tomato-600">Passwords do not match.</p>
            )}
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <button
              type="submit"
              disabled={submitting || otp.length !== 6 || !isStrong || !passwordsMatch}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 text-sm font-bold text-white shadow-soft transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
            >
              {submitting && <Loader2 size={15} className="animate-spin" />}
              {submitting ? 'Updating…' : 'Verify & Update Password'}
            </button>
            <button
              type="button"
              onClick={resetState}
              className="text-sm font-semibold text-slate-500 dark:text-slate-400 hover:text-slate-700"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {step === 'done' && (
        <div className="mt-4 flex max-w-md items-start gap-3 rounded-xl bg-emerald-50 px-4 py-3.5">
          <ShieldCheck size={18} className="mt-0.5 shrink-0 text-emerald-600" />
          <div>
            <p className="text-sm font-semibold text-emerald-800">Password updated successfully.</p>
            <button onClick={resetState} className="mt-1 text-xs font-semibold text-emerald-700 underline">
              Done
            </button>
          </div>
        </div>
      )}
    </Card>
  );
}

export default function Settings() {
  const { user } = useAuth();
  const name = user?.name || '';
  const email = user?.email || '';

  return (
    <div>
      <PageHeader title="Settings" subtitle="Manage your account and workspace preferences" />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <AvatarCard />

        <ProfileCard />

        <Card className="lg:col-span-3">
          <h3 className="text-sm font-bold text-navy-900 dark:text-white">Notification Preferences</h3>
          <div className="mt-4 flex flex-col divide-y divide-slate-50 dark:divide-navy-800/60">
            {[
              ['New high-match tenders', true],
              ['Weekly performance digest', true],
              ['Proposal deadline reminders', true],
              ['Product updates & tips', false],
            ].map(([label, checked]) => (
              <label key={label} className="flex items-center justify-between py-3 text-sm text-navy-900 dark:text-white">
                {label}
                <input type="checkbox" defaultChecked={checked} className="h-4 w-4 rounded border-slate-300 dark:border-navy-600 text-brand-600" />
              </label>
            ))}
          </div>
        </Card>

        <ChangePasswordCard />
      </div>
    </div>
  );
}
