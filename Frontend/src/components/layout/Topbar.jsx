import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu, Search, Bell, HelpCircle, Sun, Moon, LogOut, ChevronDown, Calendar, CheckSquare, Info, Plus, Check, X, RefreshCw, FileText, Building2 } from 'lucide-react';
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

function NotificationBell() {
  const { notifications, unreadCount, markRead, markAllRead } = useNotifications();
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef(null);
  const navigate = useNavigate();

  function handleNotificationClick(n) {
    if (!n.read) markRead(n.id);
    setOpen(false);
    if (n.link) {
      // Support both in-app paths ("/tenders/123") and absolute URLs.
      if (/^https?:\/\//i.test(n.link)) {
        window.open(n.link, '_blank', 'noopener,noreferrer');
      } else {
        navigate(n.link);
      }
    }
  }

  useEffect(() => {
    function clickOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', clickOutside);
    return () => document.removeEventListener('mousedown', clickOutside);
  }, []);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative rounded-lg p-2.5 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-navy-800"
      >
        <Bell size={19} />
        {unreadCount > 0 && (
          <span className="absolute right-2 top-2 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[9px] font-bold text-white">
            {unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 rounded-2xl border border-slate-200 bg-white p-4 shadow-soft dark:border-navy-700 dark:bg-navy-800 z-50">
          <div className="mb-3 flex items-center justify-between">
            <h4 className="text-sm font-bold text-navy-900 dark:text-white">Notifications</h4>
            {unreadCount > 0 && (
              <button onClick={markAllRead} className="text-xs font-semibold text-brand-600 dark:text-brand-400 hover:underline">
                Mark all as read
              </button>
            )}
          </div>

          <div className="max-h-64 overflow-y-auto space-y-2.5">
            {notifications.length === 0 ? (
              <div className="py-8 text-center text-xs text-slate-400">No notifications yet.</div>
            ) : (
              notifications.map((n) => {
                const Icon = TYPE_ICON[n.type] || Info;
                const color = TYPE_COLOR[n.type] || 'bg-slate-100 text-slate-700';
                return (
                  <div
                    key={n.id}
                    onClick={() => handleNotificationClick(n)}
                    title={n.link ? 'Click to open' : ''}
                    className={`flex items-start gap-3 rounded-xl p-2.5 transition-all cursor-pointer ${
                      n.read ? 'opacity-60' : 'bg-slate-50/50 hover:bg-slate-50 dark:bg-navy-900/40 dark:hover:bg-navy-900/60'
                    }`}
                  >
                    <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${color}`}>
                      <Icon size={15} />
                    </div>
                    <div className="min-w-0 flex-1 leading-normal">
                      {n.title && (
                        <p className="text-xs font-bold text-navy-900 dark:text-white break-words">{n.title}</p>
                      )}
                      <p className="text-xs font-semibold text-navy-900 dark:text-white break-words">{n.message}</p>
                      <p className="mt-1 text-[10px] text-slate-400">
                        {n.createdAt ? new Date(n.createdAt).toLocaleDateString() : ''}
                      </p>
                    </div>
                  </div>
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
  const searchRef = useRef(null);

  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchTab, setSearchTab] = useState('tenders'); // 'tenders' | 'companies'
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);

  const [theme, setTheme] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('theme') || 'light';
    }
    return 'light';
  });

  // Command K listener
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setShowSearch(true);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Click outside search listener
  useEffect(() => {
    function clickOutsideSearch(e) {
      if (searchRef.current && !searchRef.current.contains(e.target)) {
        setShowSearch(false);
      }
    }
    document.addEventListener('mousedown', clickOutsideSearch);
    return () => document.removeEventListener('mousedown', clickOutsideSearch);
  }, []);

  // Debounced Search Query Fetcher
  useEffect(() => {
    if (!showSearch || !searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    const timer = setTimeout(() => {
      const fetchPromise = searchTab === 'tenders'
        ? api.getTenders({ query: searchQuery })
        : api.getCompanies({ query: searchQuery });

      fetchPromise
        .then((res) => {
          const items = searchTab === 'tenders' ? (res.tenders || []) : (res.companies || []);
          setSearchResults(items);
        })
        .catch((err) => console.error(err))
        .finally(() => setSearchLoading(false));
    }, 250);

    return () => clearTimeout(timer);
  }, [searchQuery, searchTab, showSearch]);

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

        {/* Global Search Autocomplete Bar */}
        <div ref={searchRef} className="relative hidden sm:block sm:w-72 md:w-96 z-50">
          <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2 text-sm text-slate-400 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-300">
            <Search size={16} />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setShowSearch(true);
              }}
              onFocus={() => setShowSearch(true)}
              placeholder="Search companies, tenders..."
              className="flex-1 bg-transparent text-sm text-navy-900 outline-none placeholder:text-slate-400 dark:text-white"
            />
            {searchQuery && (
              <button 
                onClick={() => { setSearchQuery(''); setShowSearch(false); }}
                className="text-slate-400 hover:text-slate-600 mr-1"
              >
                <X size={14} />
              </button>
            )}
            <kbd className="rounded border border-slate-300 bg-white px-1.5 py-0.5 text-[10px] font-semibold text-slate-400 dark:border-navy-600 dark:bg-navy-700 dark:text-slate-400">⌘K</kbd>
          </div>

          {showSearch && (
            <div className="absolute top-full left-0 mt-1.5 w-full overflow-hidden rounded-2xl border border-slate-200 bg-white p-4 shadow-xl dark:border-navy-800 dark:bg-navy-900">
              {/* Tabs */}
              <div className="flex gap-2 border-b border-slate-100 pb-2 dark:border-navy-800">
                <button
                  onClick={() => { setSearchTab('tenders'); setSearchResults([]); }}
                  className={`rounded-lg px-2.5 py-1 text-xs font-bold transition-all ${
                    searchTab === 'tenders'
                      ? 'bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400'
                      : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-300'
                  }`}
                >
                  Tenders
                </button>
                <button
                  onClick={() => { setSearchTab('companies'); setSearchResults([]); }}
                  className={`rounded-lg px-2.5 py-1 text-xs font-bold transition-all ${
                    searchTab === 'companies'
                      ? 'bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400'
                      : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-300'
                  }`}
                >
                  Companies
                </button>
              </div>

              {/* Results Area */}
              <div className="mt-2.5 max-h-60 overflow-y-auto space-y-1">
                {searchLoading ? (
                  <div className="flex py-6 items-center justify-center gap-2 text-slate-400 text-xs">
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    <span>Searching database...</span>
                  </div>
                ) : !searchQuery.trim() ? (
                  <div className="py-6 text-center text-xs text-slate-400">
                    Type a query to search for companies or active tenders.
                  </div>
                ) : searchResults.length === 0 ? (
                  <div className="py-6 text-center text-xs text-slate-400">
                    No matches found for "{searchQuery}".
                  </div>
                ) : (
                  searchResults.map((item) => {
                    const title = searchTab === 'tenders' ? item.title : item.name;
                    const subtitle = searchTab === 'tenders' ? item.agency : (item.primary_naics_desc || item.uei);
                    const path = searchTab === 'tenders' ? `/tenders/${item.id}` : `/companies/${item.uei || item.id}`;

                    return (
                      <button
                        key={item.id || item.uei}
                        onClick={() => {
                          navigate(path);
                          setShowSearch(false);
                          setSearchQuery('');
                        }}
                        className="w-full text-left flex items-start gap-2.5 rounded-xl p-2 hover:bg-slate-50/80 dark:hover:bg-navy-950 transition-all border border-transparent hover:border-slate-100 dark:hover:border-navy-800"
                      >
                        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600 dark:bg-navy-850 dark:text-slate-300">
                          {searchTab === 'tenders' ? <FileText size={14} /> : <Building2 size={14} />}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-[11px] font-bold text-navy-900 dark:text-white truncate">{title}</p>
                          <p className="text-[9px] text-slate-400 truncate mt-0.5">{subtitle}</p>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          )}
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
              src={
                user?.avatarUrl
                  ? api.getAvatarUrl(user.avatarUrl)
                  : api.getInitialsAvatar(user?.name || user?.email || 'User')
              }
              alt={user?.name || 'User'}
              className="h-9 w-9 rounded-full border border-slate-200 bg-slate-100 object-cover dark:border-navy-700 dark:bg-navy-800"
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
                className="flex w-full items-center gap-2 px-3.5 py-2 text-sm font-medium text-tomato-600 hover:bg-slate-50 dark:hover:bg-tomato-950"
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
