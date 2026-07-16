import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, Lock, Eye, EyeOff, Check, X, ShieldAlert } from 'lucide-react';
import { api } from '../lib/api.jsx';
import { useAuth } from '../context/AuthContext.jsx';
import { checkPasswordRules } from '../lib/passwordStrength.jsx';

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
      <p className="mt-1 text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</p>
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

// Shown immediately after an invited user's very first sign-in, while their
// account still has a temporary password. There's no "skip" or "later" —
// ProtectedRoute sends them straight back here for anything else they try
// to open until this is done, so no temp password ever lingers in use.
export default function ForceChangePassword() {
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { updateUser } = useAuth();

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const result = await api.forceChangePassword(newPassword, confirmPassword);
      updateUser({ mustChangePassword: false, ...(result.user || {}) });
      navigate('/', { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#F6F7FB] dark:bg-navy-950 px-6 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center justify-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-accent-orange">
            <Sparkles size={20} className="text-white" />
          </div>
          <p className="text-sm font-extrabold tracking-wide text-navy-900 dark:text-white">ORBITAVANYA TECH</p>
        </div>

        <div className="rounded-2xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 p-8 shadow-card">
          <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-tomato-50">
            <ShieldAlert size={20} className="text-tomato-600" />
          </div>
          <h1 className="text-xl font-extrabold text-navy-900 dark:text-white">Set a permanent password</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            You signed in with a temporary password. Choose a new one now to finish setting up your account —
            you won't be able to use the rest of OrbitAvanya until this is done.
          </p>

          {error && (
            <div className="mt-4 rounded-lg bg-tomato-50 px-3.5 py-2.5 text-sm text-tomato-700">{error}</div>
          )}

          <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
            <div>
              <label className="mb-1.5 block text-sm font-semibold text-navy-900 dark:text-white">New password</label>
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 focus-within:border-brand-500">
                <Lock size={16} className="text-slate-400 dark:text-slate-500" />
                <input
                  type={showPw ? 'text' : 'password'}
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full border-0 bg-transparent text-sm outline-none"
                />
                <button type="button" onClick={() => setShowPw((s) => !s)} className="text-slate-400 dark:text-slate-500">
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              <PasswordStrengthMeter password={newPassword} />
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-semibold text-navy-900 dark:text-white">Confirm new password</label>
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 focus-within:border-brand-500">
                <Lock size={16} className="text-slate-400 dark:text-slate-500" />
                <input
                  type={showPw ? 'text' : 'password'}
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full border-0 bg-transparent text-sm outline-none"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="mt-2 w-full rounded-xl bg-brand-500 py-3 text-sm font-bold text-white shadow-soft transition-colors hover:bg-brand-600 disabled:opacity-60"
            >
              {loading ? 'Saving…' : 'Set password & continue'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
