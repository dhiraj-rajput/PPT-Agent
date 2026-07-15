import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Sparkles, Mail, Lock, Eye, EyeOff, Check, X, ShieldCheck } from 'lucide-react';
import { api } from '../lib/api.js';
import { useAuth } from '../context/AuthContext.jsx';
import { checkPasswordRules } from '../lib/passwordStrength.js';

const STRENGTH_BAR_COLORS = {
  'Very weak': 'bg-tomato-500',
  Weak: 'bg-orange-400',
  Fair: 'bg-yellow-400',
  Strong: 'bg-green-500',
};

function PasswordStrengthMeter({ password }) {
  const { checks, score, label } = checkPasswordRules(password);
  const rules = [
    { key: 'length', label: 'At least 8 characters' },
    { key: 'upper', label: 'One uppercase letter' },
    { key: 'lower', label: 'One lowercase letter' },
    { key: 'number', label: 'One number' },
    { key: 'special', label: 'One special character' },
  ];

  if (!password) return null;

  return (
    <div className="mt-2">
      <div className="flex gap-1">
        {[0, 1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className={`h-1.5 flex-1 rounded-full ${
              i < score ? STRENGTH_BAR_COLORS[label] || 'bg-slate-200' : 'bg-slate-200'
            }`}
          />
        ))}
      </div>
      <p className="mt-1 text-xs font-semibold text-slate-500">{label}</p>
      <ul className="mt-2 grid grid-cols-1 gap-1 sm:grid-cols-2">
        {rules.map((rule) => (
          <li key={rule.key} className="flex items-center gap-1.5 text-xs">
            {checks[rule.key] ? (
              <Check size={13} className="shrink-0 text-green-600" />
            ) : (
              <X size={13} className="shrink-0 text-slate-300" />
            )}
            <span className={checks[rule.key] ? 'text-slate-600' : 'text-slate-400'}>{rule.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Shell({ children }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#F6F7FB] px-6 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center justify-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-accent-orange">
            <Sparkles size={20} className="text-white" />
          </div>
          <p className="text-sm font-extrabold tracking-wide text-navy-900">ORBITAVANYA TECH</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-card">{children}</div>

        <p className="mt-6 text-center text-sm text-slate-500">
          <Link to="/login" className="font-semibold text-brand-600">
            Back to sign in
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function ForgotPassword() {
  // step: 'email' -> 'otp' -> 'password' -> 'done'
  const [step, setStep] = useState('email');
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [showConfirmPw, setShowConfirmPw] = useState(false);

  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);

  const navigate = useNavigate();
  const { completeAuth } = useAuth();

  const { isStrong } = checkPasswordRules(newPassword);
  const passwordsMatch = confirmPassword.length > 0 && newPassword === confirmPassword;

  async function handleRequestOtp(e) {
    e.preventDefault();
    setError('');
    setInfo('');
    setLoading(true);
    try {
      await api.forgotPassword(email);
      setStep('otp');
      setInfo('If an account exists for that email, a verification code has been sent.');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    setError('');
    setInfo('');
    setResending(true);
    try {
      await api.forgotPassword(email);
      setInfo('A new code has been sent, if that email is registered.');
    } catch (err) {
      setError(err.message);
    } finally {
      setResending(false);
    }
  }

  async function handleVerifyOtp(e) {
    e.preventDefault();
    setError('');
    setInfo('');
    setLoading(true);
    try {
      const result = await api.verifyResetOtp(email, otp);
      setResetToken(result.resetToken);
      setStep('password');
    } catch (err) {
      // Fallback: an expired/invalid code shouldn't dead-end the person —
      // let them request a fresh one from the same screen.
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleResetPassword(e) {
    e.preventDefault();
    setError('');

    if (!isStrong) {
      setError('Please choose a stronger password before continuing.');
      return;
    }
    if (!passwordsMatch) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      const result = await api.resetPassword(resetToken, newPassword, confirmPassword);
      completeAuth(result.token, result.user);
      setStep('done');
      setTimeout(() => navigate('/', { replace: true }), 1200);
    } catch (err) {
      // Fallback: if the reset session expired between steps, send the
      // person back to request a brand-new code instead of getting stuck.
      setError(err.message);
      if (/expired|start over/i.test(err.message)) {
        setResetToken('');
        setOtp('');
        setStep('email');
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <Shell>
      {(error || info) && (
        <div
          className={`mb-4 rounded-lg px-3.5 py-2.5 text-sm ${
            error ? 'bg-tomato-50 text-tomato-700' : 'bg-pacific-blue-50 text-pacific-blue-700'
          }`}
        >
          {error || info}
        </div>
      )}

      {step === 'email' && (
        <>
          <h1 className="text-xl font-extrabold text-navy-900">Forgot your password?</h1>
          <p className="mt-1 text-sm text-slate-500">
            Enter your account email and we'll send you a verification code.
          </p>
          <form onSubmit={handleRequestOtp} className="mt-6 flex flex-col gap-4">
            <div>
              <label className="mb-1.5 block text-sm font-semibold text-navy-900">Email address</label>
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 focus-within:border-brand-500">
                <Mail size={16} className="text-slate-400" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full border-0 bg-transparent text-sm outline-none placeholder:text-slate-400"
                  placeholder="you@company.com"
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-brand-500 py-3 text-sm font-bold text-white shadow-soft transition-colors hover:bg-brand-600 disabled:opacity-60"
            >
              {loading ? 'Sending…' : 'Send verification code'}
            </button>
          </form>
        </>
      )}

      {step === 'otp' && (
        <>
          <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-brand-50">
            <ShieldCheck size={20} className="text-brand-600" />
          </div>
          <h1 className="text-xl font-extrabold text-navy-900">Check your email</h1>
          <p className="mt-1 text-sm text-slate-500">
            Enter the 6-digit code we sent to <span className="font-semibold text-navy-900">{email}</span>.
          </p>
          <form onSubmit={handleVerifyOtp} className="mt-6 flex flex-col gap-4">
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={6}
              required
              value={otp}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
              placeholder="000000"
              className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-center text-2xl font-bold tracking-[0.5em] outline-none focus:border-brand-500"
            />
            <button
              type="submit"
              disabled={loading || otp.length !== 6}
              className="w-full rounded-xl bg-brand-500 py-3 text-sm font-bold text-white shadow-soft transition-colors hover:bg-brand-600 disabled:opacity-60"
            >
              {loading ? 'Verifying…' : 'Verify code'}
            </button>
          </form>
          <button
            onClick={handleResend}
            disabled={resending}
            className="mt-4 w-full text-center text-sm font-semibold text-brand-600 disabled:opacity-60"
          >
            {resending ? 'Sending…' : "Didn't get a code? Resend"}
          </button>
          <button
            onClick={() => {
              setStep('email');
              setOtp('');
              setError('');
              setInfo('');
            }}
            className="mt-2 w-full text-center text-xs font-semibold text-slate-400"
          >
            Use a different email
          </button>
        </>
      )}

      {step === 'password' && (
        <>
          <h1 className="text-xl font-extrabold text-navy-900">Set a new password</h1>
          <p className="mt-1 text-sm text-slate-500">Choose a strong password for your account.</p>
          <form onSubmit={handleResetPassword} className="mt-6 flex flex-col gap-4">
            <div>
              <label className="mb-1.5 block text-sm font-semibold text-navy-900">New password</label>
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 focus-within:border-brand-500">
                <Lock size={16} className="text-slate-400" />
                <input
                  type={showPw ? 'text' : 'password'}
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full border-0 bg-transparent text-sm outline-none"
                />
                <button type="button" onClick={() => setShowPw((s) => !s)} className="text-slate-400">
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              <PasswordStrengthMeter password={newPassword} />
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-semibold text-navy-900">Confirm new password</label>
              <div
                className={`flex items-center gap-2 rounded-xl border bg-white px-3.5 py-2.5 focus-within:border-brand-500 ${
                  confirmPassword && !passwordsMatch ? 'border-tomato-300' : 'border-slate-200'
                }`}
              >
                <Lock size={16} className="text-slate-400" />
                <input
                  type={showConfirmPw ? 'text' : 'password'}
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full border-0 bg-transparent text-sm outline-none"
                />
                <button type="button" onClick={() => setShowConfirmPw((s) => !s)} className="text-slate-400">
                  {showConfirmPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {confirmPassword && !passwordsMatch && (
                <p className="mt-1.5 text-xs font-medium text-tomato-600">Passwords do not match.</p>
              )}
            </div>

            <button
              type="submit"
              disabled={loading || !isStrong || !passwordsMatch}
              className="mt-2 w-full rounded-xl bg-brand-500 py-3 text-sm font-bold text-white shadow-soft transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? 'Updating…' : 'Reset password'}
            </button>
          </form>
        </>
      )}

      {step === 'done' && (
        <div className="flex flex-col items-center py-4 text-center">
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50">
            <Check size={22} className="text-emerald-600" />
          </div>
          <h1 className="text-xl font-extrabold text-navy-900">Password updated</h1>
          <p className="mt-1 text-sm text-slate-500">Taking you to your dashboard…</p>
        </div>
      )}
    </Shell>
  );
}
