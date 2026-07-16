export function PageHeader({ title, subtitle, action }) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 className="text-2xl font-extrabold text-navy-900 dark:text-white">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Card({ children, className = '' }) {
  return (
    <div className={`rounded-2xl border border-slate-100 bg-white p-5 shadow-card dark:border-navy-800 dark:bg-navy-900 ${className}`}>
      {children}
    </div>
  );
}

const matchColor = (score) => {
  if (score >= 90) return 'bg-emerald-100 text-emerald-700';
  if (score >= 75) return 'bg-brand-100 text-brand-700';
  if (score >= 50) return 'bg-amber-100 text-amber-700';
  return 'bg-rose-100 text-rose-700';
};

export function MatchBadge({ score }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-bold ${matchColor(score)}`}>
      {score}%
    </span>
  );
}

const statusStyles = {
  Active: 'bg-emerald-100 text-emerald-700',
  Open: 'bg-emerald-100 text-emerald-700',
  Prospect: 'bg-amber-100 text-amber-700',
  Draft: 'bg-slate-100 text-slate-600',
  Inactive: 'bg-slate-100 text-slate-500',
  Pending: 'bg-amber-100 text-amber-700',
  Scheduled: 'bg-sky-100 text-sky-700',
  Completed: 'bg-violet-100 text-violet-700',
  'In Review': 'bg-amber-100 text-amber-700',
  Submitted: 'bg-brand-100 text-brand-700',
  High: 'bg-rose-100 text-rose-700',
  Medium: 'bg-amber-100 text-amber-700',
  Low: 'bg-slate-100 text-slate-600',
};

export function StatusBadge({ status }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${statusStyles[status] || 'bg-slate-100 text-slate-600'}`}>
      {status}
    </span>
  );
}

const alertStyles = {
  urgent: 'bg-amaranth-100 text-amaranth-700',
  soon: 'bg-tuscan-sun-100 text-tuscan-sun-700',
  normal: 'bg-slate-100 text-slate-600',
};

export function ClosingAlertBadge({ daysLeft }) {
  const level = daysLeft <= 3 ? 'urgent' : daysLeft <= 7 ? 'soon' : 'normal';
  const label = daysLeft < 0 ? 'Closed' : daysLeft === 0 ? 'Closes today' : `${daysLeft}d left`;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold ${alertStyles[level]}`}>
      {label}
    </span>
  );
}
