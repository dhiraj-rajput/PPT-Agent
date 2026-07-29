import { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import { api } from '../lib/api.jsx';
import { useAuth } from './AuthContext.jsx';

const ErrorLogContext = createContext(null);
const POLL_INTERVAL_MS = 10000; // check for new server errors every 10s
const SINCE_KEY = 'orbitavanya_error_log_since';

function isAdmin(user) {
  const role = (user?.role || '').toLowerCase();
  return role === 'admin' || role === 'owner';
}

export function ErrorLogProvider({ children }) {
  const { user } = useAuth();
  const admin = isAdmin(user);

  const [summary, setSummary] = useState(null);
  const [activeAlerts, setActiveAlerts] = useState([]); // errors not yet dismissed from the banner
  const dismissedIdsRef = useRef(new Set());
  const sinceRef = useRef(localStorage.getItem(SINCE_KEY) || null);
  const timerRef = useRef(null);

  const refreshSummary = useCallback(async () => {
    if (!admin) return;
    try {
      const data = await api.getSystemLogsSummary();
      setSummary(data);
    } catch {
      // Silent — polling shouldn't surface its own errors to the user.
    }
  }, [admin]);

  const poll = useCallback(async () => {
    if (!admin) return;
    try {
      const { newLogs } = await api.pollSystemLogs(sinceRef.current);
      if (newLogs && newLogs.length > 0) {
        // Newest first from the API — track the latest timestamp we've seen.
        const latestTs = newLogs[0].timestamp;
        if (latestTs) {
          sinceRef.current = latestTs;
          localStorage.setItem(SINCE_KEY, latestTs);
        }
        const fresh = newLogs.filter((l) => !dismissedIdsRef.current.has(l.id));
        if (fresh.length > 0) {
          setActiveAlerts((prev) => {
            const existingIds = new Set(prev.map((p) => p.id));
            const merged = [...fresh.filter((f) => !existingIds.has(f.id)), ...prev];
            return merged.slice(0, 500); // cap how many stack up in the banner
          });
        }
        refreshSummary();
      }
    } catch {
      // Silent — polling shouldn't surface its own errors to the user.
    }
  }, [admin, refreshSummary]);

  useEffect(() => {
    if (!admin) {
      setSummary(null);
      setActiveAlerts([]);
      if (timerRef.current) clearInterval(timerRef.current);
      return;
    }

    // On first load for an admin, only alert on genuinely new errors going
    // forward — don't replay history that happened before this session.
    if (!sinceRef.current) {
      const nowIso = new Date().toISOString();
      sinceRef.current = nowIso;
      localStorage.setItem(SINCE_KEY, nowIso);
    }

    refreshSummary();
    poll();
    timerRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [admin]);

  function dismissAlert(id) {
    dismissedIdsRef.current.add(id);
    setActiveAlerts((prev) => prev.filter((a) => a.id !== id));
  }

  function dismissAllAlerts() {
    activeAlerts.forEach((a) => dismissedIdsRef.current.add(a.id));
    setActiveAlerts([]);
  }

  return (
    <ErrorLogContext.Provider
      value={{ admin, summary, activeAlerts, refreshSummary, dismissAlert, dismissAllAlerts }}
    >
      {children}
    </ErrorLogContext.Provider>
  );
}

export function useErrorLogs() {
  const ctx = useContext(ErrorLogContext);
  if (!ctx) throw new Error('useErrorLogs must be used within ErrorLogProvider');
  return ctx;
}
