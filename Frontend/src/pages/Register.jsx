import { useState, useMemo } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Sparkles, Mail, Lock, User, Phone, Eye, EyeOff, Check, X } from 'lucide-react';
import { api } from '../lib/api.jsx';
import { checkPasswordRules, strengthLabel } from '../lib/passwordStrength.jsx';

const getBarColor = (i, currentScore) => {
  if (i >= currentScore) return 'bg-slate-200';
  if (currentScore <= 1) return 'bg-rose-500';
  if (currentScore === 2) return 'bg-orange-500';
  if (currentScore === 3) return 'bg-yellow-500';
  if (currentScore === 4) return 'bg-blue-500';
  return 'bg-emerald-500';
};

function PasswordStrengthMeter({ password }) {
  const { checks, score } = checkPasswordRules(password);
  const label = strengthLabel(score);

  const rules = [
    { key: 'minLength', label: 'At least 8 characters' },
    { key: 'hasUppercase', label: 'One uppercase letter' },
    { key: 'hasLowercase', label: 'One lowercase letter' },
    { key: 'hasNumber', label: 'One number' },
    { key: 'hasSpecial', label: 'One special character' },
  ];

  if (!password) return null;

  return (
    <div className="mt-2">
      <div className="flex gap-1">
        {[0, 1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className={`h-1.5 flex-1 rounded-full ${getBarColor(i, score)}`}
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

export default function Register() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [showConfirmPw, setShowConfirmPw] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const { isStrong } = useMemo(() => checkPasswordRules(password), [password]);
  const passwordsMatch = confirmPassword.length > 0 && password === confirmPassword;
  const canSubmit = name && email && phone && isStrong && passwordsMatch;

  async function handleSubmit(e) {
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
      await api.register(name, email, phone, password, confirmPassword);
      navigate('/verify-otp', { state: { email, purpose: 'register' } });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen bg-[#F6F7FB] dark:bg-navy-950">
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-navy-900 p-12 text-white lg:flex">
        <div className="absolute -right-24 -top-24 h-96 w-96 rounded-full bg-brand-500/20 blur-3xl" />
        <div className="absolute -bottom-32 -left-10 h-96 w-96 rounded-full bg-accent-orange/10 blur-3xl" />

        <div className="relative flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-accent-orange">
            <Sparkles size={20} className="text-white" />
          </div>
          <div className="leading-tight">
            <p className="text-sm font-extrabold tracking-wide">ORBITAVANYA</p>
            <p className="text-[10px] font-semibold tracking-[0.2em] text-slate-400 dark:text-slate-500">TECH</p>
          </div>
        </div>

        <div className="relative max-w-md">
          <h2 className="text-3xl font-extrabold leading-tight">Create your account.</h2>
          <p className="mt-4 text-sm text-slate-300">
            Get access to AI-powered tender discovery, company intelligence, and proposal generation.
          </p>
        </div>

        <p className="relative text-xs text-slate-500 dark:text-slate-400">© 2026 OrbitAvanya Tech. All rights reserved.</p>
      </div>

      <div className="flex w-full flex-1 items-center justify-center px-6 py-12 lg:w-1/2">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-accent-orange">
              <Sparkles size={18} className="text-white" />
            </div>
            <p className="text-sm font-extrabold tracking-wide text-navy-900 dark:text-white">ORBITAVANYA TECH</p>
          </div>

          <h1 className="text-2xl font-extrabold text-navy-900 dark:text-white">Request access</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Create an account to get started.</p>

          {error && (
            <div className="mt-4 rounded-lg bg-tomato-50 px-3.5 py-2.5 text-sm text-tomato-700">{error}</div>
          )}

          <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
            <div>
              <label className="mb-1.5 block text-sm font-semibold text-navy-900 dark:text-white">Full name</label>
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 focus-within:border-brand-500">
                <User size={16} className="text-slate-400 dark:text-slate-500" />
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full border-0 bg-transparent text-sm outline-none placeholder:text-slate-400 dark:placeholder:text-slate-500"
                  placeholder="Jane Doe"
                />
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-semibold text-navy-900 dark:text-white">Email address</label>
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 focus-within:border-brand-500">
                <Mail size={16} className="text-slate-400 dark:text-slate-500" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full border-0 bg-transparent text-sm outline-none placeholder:text-slate-400 dark:placeholder:text-slate-500"
                  placeholder="you@company.com"
                />
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-semibold text-navy-900 dark:text-white">Phone number</label>
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 focus-within:border-brand-500">
                <Phone size={16} className="text-slate-400 dark:text-slate-500" />
                <input
                  type="tel"
                  required
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="w-full border-0 bg-transparent text-sm outline-none placeholder:text-slate-400 dark:placeholder:text-slate-500"
                  placeholder="+91 98765 43210"
                />
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-semibold text-navy-900 dark:text-white">Password</label>
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 focus-within:border-brand-500">
                <Lock size={16} className="text-slate-400 dark:text-slate-500" />
                <input
                  type={showPw ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full border-0 bg-transparent text-sm outline-none"
                  placeholder="Create a strong password"
                />
                <button type="button" onClick={() => setShowPw((s) => !s)} className="text-slate-400 dark:text-slate-500">
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              <PasswordStrengthMeter password={password} />
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-semibold text-navy-900 dark:text-white">Confirm password</label>
              <div
                className={`flex items-center gap-2 rounded-xl border bg-white dark:bg-navy-900 px-3.5 py-2.5 focus-within:border-brand-500 ${
                  confirmPassword && !passwordsMatch ? 'border-tomato-300' : 'border-slate-200 dark:border-navy-700'
                }`}
              >
                <Lock size={16} className="text-slate-400 dark:text-slate-500" />
                <input
                  type={showConfirmPw ? 'text' : 'password'}
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full border-0 bg-transparent text-sm outline-none"
                  placeholder="Re-enter your password"
                />
                <button type="button" onClick={() => setShowConfirmPw((s) => !s)} className="text-slate-400 dark:text-slate-500">
                  {showConfirmPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {confirmPassword && !passwordsMatch && (
                <p className="mt-1.5 text-xs font-medium text-tomato-600">Passwords do not match.</p>
              )}
              {confirmPassword && passwordsMatch && (
                <p className="mt-1.5 flex items-center gap-1 text-xs font-medium text-green-600">
                  <Check size={13} /> Passwords match
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={loading || !canSubmit}
              className="mt-2 w-full rounded-xl bg-brand-500 py-3 text-sm font-bold text-white shadow-soft transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? 'Creating account…' : 'Create account'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-500 dark:text-slate-400">
            Already have an account?{' '}
            <Link to="/login" className="font-semibold text-brand-600">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
