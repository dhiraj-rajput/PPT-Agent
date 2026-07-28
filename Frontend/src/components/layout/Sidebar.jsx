import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Building2, FileStack, BrainCircuit, FileEdit, Mail,
  Kanban, Calendar, CheckSquare, BarChart3, FileBarChart, Users,
  Plug, Settings, ChevronLeft, Sparkles, Zap, Hash, ScrollText
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext.jsx';
import { useErrorLogs } from '../../context/ErrorLogContext.jsx';

const topNav = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/reports', label: 'Reports', icon: FileBarChart },
];

const bizNav = [
  { to: '/companies', label: 'Companies', icon: Building2 },
  { to: '/tenders', label: 'Tenders', icon: FileStack },
  { to: '/naics', label: 'NAICS Muster', icon: Hash },
  { to: '/ai-research', label: 'AI Research', icon: BrainCircuit },
  { to: '/proposal-builder', label: 'Proposal Builder', icon: FileEdit },
  { to: '/rfp-auto-respond', label: 'RFP Auto-Respond', icon: Zap },
  { to: '/email-campaign', label: 'Email Campaign', icon: Mail },
  { to: '/newsletter', label: 'Newsletter', icon: Sparkles },
  { to: '/meetings', label: 'Meetings', icon: Calendar },
];

const opsNav = [
  { to: '/crm-pipeline', label: 'CRM Pipeline', icon: Kanban },
  { to: '/tasks', label: 'Tasks', icon: CheckSquare },
];

function NavSection({ title, items, collapsed }) {
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

export default function Sidebar({ collapsed, onToggle }) {
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

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-30 flex flex-col bg-navy-900 transition-all duration-200 ${
        collapsed ? 'w-[76px]' : 'w-[260px]'
      }`}
    >
      {/* Logo */}
      <div className={`flex items-center gap-3 px-5 py-6 ${collapsed ? 'justify-center px-0' : ''}`}>
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-accent-orange">
          <Sparkles size={18} className="text-white" />
        </div>
        {!collapsed && (
          <div className="leading-tight">
            <p className="text-sm font-extrabold tracking-wide text-white">ORBITAVANYA</p>
            <p className="text-[10px] font-semibold tracking-[0.2em] text-slate-400 dark:text-slate-500">TECH</p>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-none pb-4">
        <NavSection title="Dashboard & Analytics" items={topNav} collapsed={collapsed} />
        <NavSection title="Business Development" items={bizNav} collapsed={collapsed} />
        <NavSection title="Operations & CRM" items={opsNav} collapsed={collapsed} />
        <NavSection title="Settings" items={settingsNav} collapsed={collapsed} />
      </div>


      <button
        onClick={onToggle}
        className="flex items-center justify-center gap-2 border-t border-white/10 py-3 text-xs font-medium text-slate-400 dark:text-slate-500 hover:text-white"
      >
        <ChevronLeft size={16} className={`transition-transform ${collapsed ? 'rotate-180' : ''}`} />
        {!collapsed && 'Collapse'}
      </button>
    </aside>
  );
}
