import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu, Search, Bell, HelpCircle, Sun, Moon, LogOut, ChevronDown, Calendar, CheckSquare, Info, Plus, Check } from 'lucide-react';
import { useAuth } from '../../context/AuthContext.jsx';
import { useNotifications } from '../../context/NotificationContext.jsx';
import { api } from '../../lib/api.jsx';

const TYPE_ICON = {
  meeting_scheduled: Calendar,
  meeting_cancelled: Calendar,
  task_assigned: CheckSquare,
  custom: Info,
};

const TYPE_COLOR = {
  meeting_scheduled: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400',
  meeting_cancelled: 'bg-rose-100 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400',
  task_assigned: 'bg-sky-100 text-sky-700 dark:bg-sky-500/10 dark:text-sky-400',
  custom: 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
};

function timeAgo(dateStr) {
  const diffMs = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function NotificationBell() {
  const navigate = useNavigate();
  const { notifications, unreadCount, markRead, markAllRead, createAlert } = useNotifications();
  const [open, setOpen] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [alertTitle, setAlertTitle] = useState('');
  const [alertMessage, setAlertMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false);
        setShowAddForm(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  function handleClickNotification(n) {
    if (!n.read) markRead(n.id);
    if (n.link) {
      navigate(n.link);
      setOpen(false);
    }
  }

  async function handleAddAlert(e) {
    e.preventDefault();
    if (!alertTitle.trim()) return;
    setSubmitting(true);
    try {
      await createAlert(alertTitle.trim(), alertMessage.trim());
      setAlertTitle('');
      setAlertMessage('');
      setShowAddForm(false);
    } catch {
      // Swallow — a failed manual alert isn't critical enough to block the UI.
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative rounded-lg p-2.5 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-navy-800"
        title="Alerts"
      >
        <Bell size={19} />
        {unreadCount > 0 && (
          <span className="absolute right-1.5 top-1.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-rose-500 px-1 text-[9px] font-bold text-white">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-30 mt-2 w-80 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-soft dark:border-navy-700 dark:bg-navy-900 sm:w-96">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3 dark:border-navy-800">
            <p className="text-sm font-bold text-navy-900 dark:text-white">Alerts</p>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setShowAddForm((s) => !s)}
                className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-brand-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-navy-800"
                title="Create a custom alert"
              >
                <Plus size={13} /> New
              </button>
              {unreadCount > 0 && (
                <button
                  onClick={markAllRead}
                  className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-navy-800"
                  title="Mark all as read"
                >
                  <Check size={13} /> Mark all read
                </button>
              )}
            </div>
          </div>

          {showAddForm && (
            <form onSubmit={handleAddAlert} className="space-y-2 border-b border-slate-100 bg-slate-50 px-4 py-3 dark:border-navy-800 dark:bg-navy-800/40">
              <input
                autoFocus
                value={alertTitle}
                onChange={(e) => setAlertTitle(e.target.value)}
                placeholder="Alert title"
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-navy-900 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none dark:border-navy-700 dark:bg-navy-900 dark:text-white dark:placeholder:text-slate-500"
              />
              <input
                value={alertMessage}
                onChange={(e) => setAlertMessage(e.target.value)}
                placeholder="Details (optional)"
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-navy-900 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none dark:border-navy-700 dark:bg-navy-900 dark:text-white dark:placeholder:text-slate-500"
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowAddForm(false)}
                  className="rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-navy-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting || !alertTitle.trim()}
                  className="rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50"
                >
                  {submitting ? 'Adding…' : 'Add alert'}
                </button>
              </div>
            </form>
          )}

          <div className="max-h-96 overflow-y-auto scrollbar-none">
            {notifications.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-slate-400 dark:text-slate-500">
                No alerts yet. You'll see meeting and task updates here.
              </p>
            ) : (
              notifications.map((n) => {
                const Icon = TYPE_ICON[n.type] || Info;
                return (
                  <button
                    key={n.id}
                    onClick={() => handleClickNotification(n)}
                    className={`flex w-full items-start gap-3 border-b border-slate-50 px-4 py-3 text-left last:border-0 hover:bg-slate-50 dark:border-navy-800/60 dark:hover:bg-navy-800/60 ${
                      !n.read ? 'bg-brand-50/50 dark:bg-white/[0.03]' : ''
                    }`}
                  >
                    <span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${TYPE_COLOR[n.type] || TYPE_COLOR.custom}`}>
                      <Icon size={14} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5">
                        <span className="truncate text-sm font-semibold text-navy-900 dark:text-white">{n.title}</span>
                        {!n.read && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />}
                      </span>
                      {n.message && (
                        <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">{n.message}</span>
                      )}
                      <span className="mt-1 block text-[11px] text-slate-400 dark:text-slate-500">{timeAgo(n.createdAt)}</span>
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Topbar({ onMenuClick }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  const [theme, setTheme] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('theme') || 'light';
    }
    return 'light';
  });

  useEffect(() => {
    function handleClickOutside(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  function handleLogout() {
    logout();
    navigate('/login', { replace: true });
  }

  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    localStorage.setItem('theme', theme);
  }, [theme]);

  const [aiMode, setAiMode] = useState('auto');
  const [loadingMode, setLoadingMode] = useState(false);

  useEffect(() => {
    // Fetch initial AI mode from backend
    api.getAiMode()
      .then((data) => {
        if (data && data.ai_mode) {
          setAiMode(data.ai_mode);
        }
      })
      .catch((err) => console.error('Error fetching AI mode:', err));
  }, []);

  const toggleAiMode = async () => {
    if (loadingMode) return;
    setLoadingMode(true);
    const newMode = aiMode === 'rule_based' ? 'auto' : 'rule_based';
    try {
      const data = await api.setAiMode(newMode);
      if (data && data.ai_mode) {
        setAiMode(data.ai_mode);
      }
    } catch (err) {
      console.error('Error setting AI mode:', err);
    } finally {
      setLoadingMode(false);
    }
  };

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'));
  };

  return (
    <header className="sticky top-0 z-20 flex h-[72px] items-center justify-between gap-4 border-b border-slate-200 bg-white/90 px-6 backdrop-blur dark:border-navy-800 dark:bg-navy-900/90 dark:text-white">
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-navy-800 lg:hidden"
        >
          <Menu size={20} />
        </button>
        <div className="hidden items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm text-slate-400 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-300 sm:flex sm:w-72 md:w-96">
          <Search size={16} />
          <span className="flex-1">Search companies, tenders, contacts...</span>
          <kbd className="rounded border border-slate-300 bg-white px-1.5 py-0.5 text-[10px] font-semibold text-slate-400 dark:border-navy-600 dark:bg-navy-700 dark:text-slate-400">⌘K</kbd>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {/* AI System vs Rule-Based Toggle Button */}
        <button
          onClick={toggleAiMode}
          disabled={loadingMode}
          className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-semibold transition-all ${
            aiMode === 'rule_based'
              ? 'border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-300'
              : 'border-brand-200 bg-brand-50 text-brand-700 hover:bg-brand-100 dark:border-brand-900 dark:bg-brand-950/50 dark:text-brand-300'
          }`}
          title="Click to toggle between AI-first and Rule-based fallback systems"
        >
          <span className="relative flex h-2 w-2">
            <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 ${aiMode === 'rule_based' ? 'bg-amber-400' : 'bg-brand-400'}`}></span>
            <span className={`relative inline-flex h-2 w-2 rounded-full ${aiMode === 'rule_based' ? 'bg-amber-500' : 'bg-brand-500'}`}></span>
          </span>
          <span>{aiMode === 'rule_based' ? 'System: Rule-Based' : 'System: AI-Enabled'}</span>
        </button>

        <button className="rounded-lg p-2.5 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-navy-800">
          <HelpCircle size={19} />
        </button>
        <button
          onClick={toggleTheme}
          className="rounded-lg p-2.5 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-navy-800"
          title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
        >
          {theme === 'light' ? <Moon size={19} /> : <Sun size={19} />}
        </button>

        <NotificationBell />

        <div className="relative ml-1 border-l border-slate-200 pl-3 dark:border-navy-800" ref={menuRef}>
          <button
            onClick={() => setMenuOpen((o) => !o)}
            className="flex items-center gap-2.5 rounded-lg py-1 pr-1 hover:bg-slate-100 dark:hover:bg-navy-800"
          >
            <img
              src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(user?.name || user?.email || 'User')}`}
              alt={user?.name || 'User'}
              className="h-9 w-9 rounded-full border border-slate-200 bg-slate-100 dark:border-navy-700 dark:bg-navy-800"
            />
            <div className="hidden text-left leading-tight sm:block">
              <p className="text-sm font-semibold text-navy-900 dark:text-white">{user?.name || 'Account'}</p>
              <p className="max-w-[160px] truncate text-xs text-slate-400">{user?.email || ''}</p>
            </div>
            <ChevronDown size={16} className="hidden text-slate-400 sm:block" />
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-full mt-2 w-48 rounded-xl border border-slate-200 bg-white py-1.5 shadow-soft dark:border-navy-700 dark:bg-navy-800">
              <div className="border-b border-slate-100 px-3.5 py-2 dark:border-navy-700 sm:hidden">
                <p className="text-sm font-semibold text-navy-900 dark:text-white">{user?.name || 'Account'}</p>
                <p className="truncate text-xs text-slate-400">{user?.email || ''}</p>
              </div>
              <button
                onClick={handleLogout}
                className="flex w-full items-center gap-2 px-3.5 py-2 text-sm font-medium text-tomato-600 hover:bg-slate-50 dark:hover:bg-navy-700"
              >
                <LogOut size={16} />
                Log out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
