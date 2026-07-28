import { useNavigate } from 'react-router-dom';
import { AlertOctagon, AlertTriangle, X, ArrowRight } from 'lucide-react';
import { useErrorLogs } from '../../context/ErrorLogContext.jsx';

export default function ErrorAlertBanner() {
  const { admin, activeAlerts, dismissAlert, dismissAllAlerts } = useErrorLogs();
  const navigate = useNavigate();

  if (!admin || activeAlerts.length === 0) return null;

  const top = activeAlerts[0];
  const extraCount = activeAlerts.length - 1;
  const isCritical = top.level === 'CRITICAL';

  return (
    <div
      className={`flex items-center gap-3 px-4 py-2.5 text-sm text-white shadow-md ${
        isCritical ? 'bg-rose-600' : 'bg-amber-600'
      }`}
    >
      {isCritical ? (
        <AlertOctagon size={18} className="shrink-0" />
      ) : (
        <AlertTriangle size={18} className="shrink-0" />
      )}

      <div className="min-w-0 flex-1">
        <span className="font-bold">{isCritical ? 'Critical server error' : 'Server error'} </span>
        <span className="opacity-90">
          {top.source ? `in ${top.source} — ` : ''}
          {top.message}
        </span>
        {extraCount > 0 && (
          <span className="ml-2 rounded-full bg-black/20 px-2 py-0.5 text-xs font-semibold">
            +{extraCount} more
          </span>
        )}
      </div>

      <button
        onClick={() => navigate('/settings/server-logs')}
        className="flex shrink-0 items-center gap-1 rounded-lg bg-black/15 px-2.5 py-1 text-xs font-bold hover:bg-black/25"
      >
        View details <ArrowRight size={13} />
      </button>

      <button
        onClick={() => (extraCount > 0 ? dismissAlert(top.id) : dismissAllAlerts())}
        title="Dismiss (still visible on the Server Logs page)"
        className="shrink-0 rounded-lg p-1 hover:bg-black/15"
      >
        <X size={16} />
      </button>
    </div>
  );
}
