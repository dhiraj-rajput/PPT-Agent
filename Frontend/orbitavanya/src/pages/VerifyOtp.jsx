import { useState, useEffect } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { Sparkles, ShieldCheck } from 'lucide-react';
import { api } from '../lib/api.js';
import { useAuth } from '../context/AuthContext.jsx';

export default function VerifyOtp() {
  const location = useLocation();
  const navigate = useNavigate();
  const { completeAuth } = useAuth();

  const email = location.state?.email;
  const purpose = location.state?.purpose; // 'register' | 'login'

  const [otp, setOtp] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);

  useEffect(() => {
    if (!email || !purpose) {
      navigate('/login', { replace: true });
    }
  }, [email, purpose, navigate]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const result =
        purpose === 'register'
          ? await api.verifyRegistration(email, otp)
          : await api.verifyLogin(email, otp);

      completeAuth(result.token, result.user);
      if (result.user?.mustChangePassword) {
        navigate('/force-change-password', { replace: true });
      } else {
        navigate('/', { replace: true });
      }
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
      await api.resendOtp(email);
      setInfo('A new code has been sent to your email.');
    } catch (err) {
      setError(err.message);
    } finally {
      setResending(false);
    }
  }

  if (!email || !purpose) return null;

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
          <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-brand-50">
            <ShieldCheck size={20} className="text-brand-600" />
          </div>
          <h1 className="text-xl font-extrabold text-navy-900 dark:text-white">Check your email</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            We sent a 6-digit code to <span className="font-semibold text-navy-900 dark:text-white">{email}</span>.
            Enter it below to {purpose === 'register' ? 'verify your account' : 'finish signing in'}.
          </p>

          {error && (
            <div className="mt-4 rounded-lg bg-tomato-50 px-3.5 py-2.5 text-sm text-tomato-700">{error}</div>
          )}
          {info && (
            <div className="mt-4 rounded-lg bg-pacific-blue-50 px-3.5 py-2.5 text-sm text-pacific-blue-700">
              {info}
            </div>
          )}

          <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={6}
              required
              value={otp}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
              placeholder="000000"
              className="w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-4 py-3 text-center text-2xl font-bold tracking-[0.5em] outline-none focus:border-brand-500"
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
        </div>

        <p className="mt-6 text-center text-sm text-slate-500 dark:text-slate-400">
          <Link to="/login" className="font-semibold text-brand-600">
            Back to sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
