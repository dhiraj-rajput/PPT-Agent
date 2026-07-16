import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Building2, FileStack, BrainCircuit, FileEdit, Mail,
  Kanban, Calendar, CheckSquare, BarChart3, FileBarChart, Users,
  Plug, Settings, ChevronLeft, Sparkles, UploadCloud
} from 'lucide-react';

const topNav = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/reports', label: 'Reports', icon: FileBarChart },
];

const bizNav = [
  { to: '/companies', label: 'Companies', icon: Building2 },
  { to: '/tenders', label: 'Tenders', icon: FileStack },
  { to: '/ai-research', label: 'AI Research', icon: BrainCircuit },
  { to: '/proposal-builder', label: 'Proposal Builder', icon: FileEdit },
  { to: '/bidforge', label: 'BidForge Upload', icon: UploadCloud },
  { to: '/email-campaign', label: 'Email Campaign', icon: Mail },
  { to: '/meetings', label: 'Meetings', icon: Calendar },
];

const opsNav = [
  { to: '/crm-pipeline', label: 'CRM Pipeline', icon: Kanban },
  { to: '/tasks', label: 'Tasks', icon: CheckSquare },
];

const settingsNav = [
  { to: '/settings/users', label: 'Users & Roles', icon: Users },
  { to: '/settings/integrations', label: 'Integrations', icon: Plug },
  { to: '/settings', label: 'Settings', icon: Settings, end: true },
];

function NavSection({ title, items, collapsed }) {
  return (
    <div className="mt-6">
      {!collapsed && (
        <p className="px-4 mb-2 text-[11px] font-bold tracking-wider text-navy-700/60 uppercase">{title}</p>
      )}
      <nav className="flex flex-col gap-1 px-2">
        {items.map(({ to, label, icon: Icon, end }) => (
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
            <Icon size={18} strokeWidth={2} className="shrink-0" />
            {!collapsed && <span className="truncate">{label}</span>}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

export default function Sidebar({ collapsed, onToggle }) {
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
            <p className="text-[10px] font-semibold tracking-[0.2em] text-slate-400">TECH</p>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-none pb-4">
        <NavSection title="Dashboard & Analytics" items={topNav} collapsed={collapsed} />
        <NavSection title="Business Development" items={bizNav} collapsed={collapsed} />
        <NavSection title="Operations & CRM" items={opsNav} collapsed={collapsed} />
        <NavSection title="Settings" items={settingsNav} collapsed={collapsed} />
      </div>

      {/* AI Credits */}
      {!collapsed ? (
        <div className="mx-3 mb-3 rounded-xl bg-white/5 p-3.5">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-white">AI Credits</span>
            <span className="text-slate-400">12,450 / 20,000</span>
          </div>
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
            <div className="h-full w-[62%] rounded-full bg-gradient-to-r from-brand-500 to-accent-sky" />
          </div>
          <button className="mt-3 w-full rounded-lg bg-white/10 py-2 text-xs font-semibold text-white transition-colors hover:bg-white/20">
            Upgrade Plan
          </button>
        </div>
      ) : (
        <div className="mx-auto mb-3 h-2 w-8 rounded-full bg-white/10" />
      )}

      <button
        onClick={onToggle}
        className="flex items-center justify-center gap-2 border-t border-white/10 py-3 text-xs font-medium text-slate-400 hover:text-white"
      >
        <ChevronLeft size={16} className={`transition-transform ${collapsed ? 'rotate-180' : ''}`} />
        {!collapsed && 'Collapse'}
      </button>
    </aside>
  );
}
