import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Building2, FileStack, BrainCircuit, FileEdit, Mail,
  Kanban, Calendar, CheckSquare, BarChart3, FileBarChart, Users,
  Plug, Settings, ChevronLeft, Sparkles, Zap, Hash, ScrollText, X, Database,
  Layers, Inbox
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext.jsx';
import { useErrorLogs } from '../../context/ErrorLogContext.jsx';

const topNav = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/reports', label: 'Reports', icon: FileBarChart },
];

const bizNav = [
  { to: '/database', label: 'Database', icon: Database },
  { to: '/tenders', label: 'Tenders', icon: FileStack },
  { to: '/naics', label: 'NAICS Muster', icon: Hash },
  { to: '/ai-research', label: 'AI Research', icon: BrainCircuit },
  { to: '/proposal-builder', label: 'Proposal Builder', icon: FileEdit },
  { to: '/rfp-auto-respond', label: 'RFP Auto-Respond', icon: Zap },
  { to: '/email-campaign', label: 'Email Campaign', icon: Mail },
  { to: '/newsletter', label: 'Newsletter', icon: Sparkles },
  { to: '/linkedin-campaign', label: 'LinkedIn Campaigns', icon: Layers },
  { to: '/linkedin-inbox', label: 'LinkedIn Inbox', icon: Inbox },
  { to: '/meetings', label: 'Meetings', icon: Calendar },
];

const opsNav = [
  { to: '/crm-pipeline', label: 'CRM Pipeline', icon: Kanban },
  { to: '/tasks', label: 'Tasks', icon: CheckSquare },
];

function NavSection({ title, items, collapsed, onNavigate }) {
  return (
    <div className="mt-6">
      {!collapsed && (
        <p className="px-4 mb-2 text-[11px] font-bold tracking-wider text-navy-700/60 uppercase">{title}</p>
      )}
      <nav className="flex flex-col gap-1 px-2">
        {items.map(({ to, label, icon: Icon, end, badge }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              `group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-brand-500 text-white shadow-soft'
                  : 'text-slate-300 hover:bg-white/5 hover:text-white'
              } ${collapsed ? 'justify-center' : ''}`
            }
            title={collapsed ? label : undefined}
          >
            <span className="relative shrink-0">
              <Icon size={18} strokeWidth={2} />
              {collapsed && !!badge && (
                <span className="absolute -right-1.5 -top-1.5 h-2 w-2 rounded-full bg-rose-500" />
              )}
            </span>
            {!collapsed && <span className="truncate flex-1">{label}</span>}
            {!collapsed && !!badge && (
              <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white">
                {badge > 99 ? '99+' : badge}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

export default function Sidebar({ collapsed, onToggle, mobileOpen = false, onCloseMobile = () => {} }) {
  const { user } = useAuth();
  const { admin, summary } = useErrorLogs();
  const isAdmin = admin || (user?.role || '').toLowerCase() === 'admin' || (user?.role || '').toLowerCase() === 'owner';

  const settingsNav = [
    { to: '/settings/users', label: 'Users & Roles', icon: Users },
    { to: '/settings/integrations', label: 'Integrations', icon: Plug },
    ...(isAdmin
      ? [{
          to: '/settings/server-logs',
          label: 'Server Logs',
          icon: ScrollText,
          badge: summary?.unresolved || 0,
        }]
      : []),
    { to: '/settings', label: 'Settings', icon: Settings, end: true },
  ];

  // On mobile the sidebar is always full-width and lives off-canvas (translate-x-full);
  // `mobileOpen` slides it in. On lg+ screens it's always visible and simply
  // shrinks to icon-width when `collapsed` is true. Using `transform` (not
  // width/margin) keeps the open/close animation on the compositor thread,
  // so it stays smooth instead of jittery on mobile.
  return (
    <>
      {/* Backdrop, mobile only */}
      <div
        onClick={onCloseMobile}
        aria-hidden="true"
        className={`fixed inset-0 z-30 bg-navy-950/60 backdrop-blur-[1px] transition-opacity duration-200 lg:hidden ${
          mobileOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[260px] flex-col bg-navy-900 will-change-transform transition-transform duration-200 ease-out
          ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}
          lg:z-30 lg:translate-x-0 lg:transition-[width] lg:duration-200 ${collapsed ? 'lg:w-[76px]' : 'lg:w-[260px]'}`}
      >
        {/* Logo */}
        <div className={`flex items-center gap-3 px-5 py-6 ${collapsed ? 'lg:justify-center lg:px-0' : ''}`}>
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-accent-orange">
            <Sparkles size={18} className="text-white" />
          </div>
          <div className={`leading-tight ${collapsed ? 'lg:hidden' : ''}`}>
            <p className="text-sm font-extrabold tracking-wide text-white">ORBITAVANYA</p>
            <p className="text-[10px] font-semibold tracking-[0.2em] text-slate-400 dark:text-slate-500">TECH</p>
          </div>
          <button
            onClick={onCloseMobile}
            className="ml-auto rounded-lg p-1.5 text-slate-400 hover:bg-white/5 hover:text-white lg:hidden"
            aria-label="Close menu"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto scrollbar-none pb-4">
          <NavSection title="Dashboard & Analytics" items={topNav} collapsed={collapsed} onNavigate={onCloseMobile} />
          <NavSection title="Business Development" items={bizNav} collapsed={collapsed} onNavigate={onCloseMobile} />
          <NavSection title="Operations & CRM" items={opsNav} collapsed={collapsed} onNavigate={onCloseMobile} />
          <NavSection title="Settings" items={settingsNav} collapsed={collapsed} onNavigate={onCloseMobile} />
        </div>

        <button
          onClick={onToggle}
          className="hidden items-center justify-center gap-2 border-t border-white/10 py-3 text-xs font-medium text-slate-400 dark:text-slate-500 hover:text-white lg:flex"
        >
          <ChevronLeft size={16} className={`transition-transform ${collapsed ? 'rotate-180' : ''}`} />
          {!collapsed && 'Collapse'}
        </button>
      </aside>
    </>
  );
}
