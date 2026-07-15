import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu, Search, Bell, HelpCircle, Sun, Moon, LogOut, ChevronDown } from 'lucide-react';
import { useAuth } from '../../context/AuthContext.jsx';

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
        <button className="relative rounded-lg p-2.5 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-navy-800">
          <Bell size={19} />
          <span className="absolute right-1.5 top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-rose-500 text-[9px] font-bold text-white">6</span>
        </button>

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
