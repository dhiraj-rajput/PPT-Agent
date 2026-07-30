export function PageHeader({ title, subtitle, action }) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 className="text-2xl font-extrabold text-navy-900 dark:text-white">{title}</h1>
        {subtitle && <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">{subtitle}</div>}
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
  Running: 'bg-emerald-100 text-emerald-700',
  Paused: 'bg-amber-100 text-amber-700',
  'In Review': 'bg-amber-100 text-amber-700',
  Submitted: 'bg-brand-100 text-brand-700',
  High: 'bg-rose-100 text-rose-700',
  Medium: 'bg-amber-100 text-amber-700',
  Low: 'bg-slate-100 text-slate-600',
  Processing: 'bg-sky-100 text-sky-700',
  Failed: 'bg-rose-100 text-rose-700',
  Duplicate: 'bg-slate-100 text-slate-500',
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

export function ProgressBar({ progress, message, status }) {
  const isError = status === 'error' || status === 'failed';
  const isCompleted = status === 'completed' || progress >= 100;
  
  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-semibold text-slate-600 dark:text-slate-400">
          {message || 'Processing...'}
        </span>
        <span className={`text-xs font-bold ${isError ? 'text-rose-500' : isCompleted ? 'text-emerald-500' : 'text-brand-500'}`}>
          {progress}%
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-navy-800">
        <div
          className={`h-full rounded-full transition-all duration-500 ease-out ${
            isError ? 'bg-rose-500' :
            isCompleted ? 'bg-emerald-500' :
            'bg-brand-500'
          }`}
          style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
        />
      </div>
    </div>
  );
}

export function renderSafeText(val, fallback = '—') {
  if (val === null || val === undefined) return fallback;
  if (typeof val === 'string' || typeof val === 'number' || typeof val === 'boolean') {
    return String(val) || fallback;
  }
  if (typeof val === 'object') {
    if (Array.isArray(val)) {
      return val.map(item => typeof item === 'object' ? renderSafeText(item, '') : String(item)).filter(Boolean).join(', ') || fallback;
    }
    const parts = [
      val.streetAddress || val.address || val.street,
      val.city,
      val.state || val.province || val.region,
      val.zip || val.zipCode || val.postalCode,
      val.country
    ].filter(Boolean);
    if (parts.length > 0) return parts.join(', ');
    const vals = Object.values(val).filter(v => v && typeof v !== 'object');
    if (vals.length > 0) return vals.join(', ');
    return fallback;
  }
  return String(val) || fallback;
}
