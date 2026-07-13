import { useState, useEffect } from 'react';
import { Menu, Search, Bell, HelpCircle, Sun, Moon } from 'lucide-react';

export default function Topbar({ onMenuClick }) {
  const [theme, setTheme] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('theme') || 'light';
    }
    return 'light';
  });

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

        <div className="ml-1 flex items-center gap-2.5 border-l border-slate-200 pl-3 dark:border-navy-800">
          <img
            src="https://api.dicebear.com/7.x/avataaars/svg?seed=JohnDoe"
            alt="John Doe"
            className="h-9 w-9 rounded-full border border-slate-200 bg-slate-100 dark:border-navy-700 dark:bg-navy-800"
          />
          <div className="hidden leading-tight sm:block">
            <p className="text-sm font-semibold text-navy-900 dark:text-white">John Doe</p>
            <p className="text-xs text-slate-400">Admin</p>
          </div>
        </div>
      </div>
    </header>
  );
}
