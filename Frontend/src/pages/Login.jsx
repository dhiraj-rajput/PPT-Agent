import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Sparkles, Mail, Lock, Eye, EyeOff } from 'lucide-react';
import { api } from '../lib/api.jsx';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await api.login(email, password);
      navigate('/verify-otp', { state: { email, purpose: 'login' } });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen bg-[#F6F7FB] dark:bg-navy-950">
      {/* Left brand panel */}
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
          <h2 className="text-3xl font-extrabold leading-tight">Win more tenders with AI-powered intelligence.</h2>
          <p className="mt-4 text-sm text-slate-300">
            Discover high-match opportunities, research companies instantly, and generate winning proposals — all in one platform.
          </p>
          <div className="mt-8 flex gap-8">
            <div>
              <p className="text-2xl font-extrabold">18,245</p>
              <p className="text-xs text-slate-400 dark:text-slate-500">Companies tracked</p>
            </div>
            <div>
              <p className="text-2xl font-extrabold">8,954</p>
              <p className="text-xs text-slate-400 dark:text-slate-500">Active tenders</p>
            </div>
            <div>
              <p className="text-2xl font-extrabold">96%</p>
              <p className="text-xs text-slate-400 dark:text-slate-500">AI match accuracy</p>
            </div>
          </div>
        </div>

        <p className="relative text-xs text-slate-500 dark:text-slate-400">© 2026 OrbitAvanya Tech. All rights reserved.</p>
      </div>

      {/* Right form panel */}
      <div className="flex w-full flex-1 items-center justify-center px-6 py-12 lg:w-1/2">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-accent-orange">
              <Sparkles size={18} className="text-white" />
            </div>
            <p className="text-sm font-extrabold tracking-wide text-navy-900 dark:text-white">ORBITAVANYA TECH</p>
          </div>

          <h1 className="text-2xl font-extrabold text-navy-900 dark:text-white">Welcome back</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Sign in to your account to continue.</p>

          {error && (
            <div className="mt-4 rounded-lg bg-tomato-50 px-3.5 py-2.5 text-sm text-tomato-700">{error}</div>
          )}

          <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-4">
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
              <div className="mb-1.5 flex items-center justify-between">
                <label className="block text-sm font-semibold text-navy-900 dark:text-white">Password</label>
                <Link to="/forgot-password" className="text-xs font-semibold text-brand-600">Forgot password?</Link>
              </div>
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 focus-within:border-brand-500">
                <Lock size={16} className="text-slate-400 dark:text-slate-500" />
                <input
                  type={showPw ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full border-0 bg-transparent text-sm outline-none"
                />
                <button type="button" onClick={() => setShowPw((s) => !s)} className="text-slate-400 dark:text-slate-500">
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <label className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <input type="checkbox" defaultChecked className="h-4 w-4 rounded border-slate-300 dark:border-navy-600 text-brand-600" />
              Keep me signed in
            </label>

            <button
              type="submit"
              disabled={loading}
              className="mt-2 w-full rounded-xl bg-brand-500 py-3 text-sm font-bold text-white shadow-soft transition-colors hover:bg-brand-600 disabled:opacity-60"
            >
              {loading ? 'Signing in…' : 'Sign In'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-500 dark:text-slate-400">
            Don't have an account? <Link to="/register" className="font-semibold text-brand-600">Request access</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
