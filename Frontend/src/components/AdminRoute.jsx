import { Navigate, Outlet } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';
import { useAuth } from '../context/AuthContext.jsx';

export default function AdminRoute() {
  const { user, loading } = useAuth();

  if (loading) return null;

  const role = (user?.role || '').toLowerCase();
  const isAdmin = role === 'admin' || role === 'owner';

  if (!isAdmin) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-100 text-rose-600 dark:bg-rose-500/10 dark:text-rose-400">
          <ShieldAlert size={26} />
        </div>
        <h2 className="text-lg font-bold text-navy-900 dark:text-white">Admin access required</h2>
        <p className="max-w-sm text-sm text-slate-500 dark:text-slate-400">
          The Server Logs page is restricted to administrators. Contact an admin on your team if you need access.
        </p>
      </div>
    );
  }

  return <Outlet />;
}

// Kept for consistency in case a redirect-based guard is preferred elsewhere.
export function AdminRedirectRoute() {
  const { user, loading } = useAuth();
  if (loading) return null;
  const role = (user?.role || '').toLowerCase();
  const isAdmin = role === 'admin' || role === 'owner';
  return isAdmin ? <Outlet /> : <Navigate to="/" replace />;
}
