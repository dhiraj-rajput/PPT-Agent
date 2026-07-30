import { useEffect, useState, useCallback, useRef } from 'react';
import {
  RefreshCw, Search, Loader2, ChevronDown, ChevronUp, Copy, Check,
  Trash2, CheckCircle2, AlertOctagon, AlertTriangle, Info, Terminal,
  FlaskConical, X, Server, Clock, Globe, Radio, Square,
} from 'lucide-react';
import { PageHeader, Card } from '../components/ui/Common.jsx';
import { api, BASE_URL } from '../lib/api.jsx';
import { useErrorLogs } from '../context/ErrorLogContext.jsx';

const LEVELS = ['ALL', 'CRITICAL', 'ERROR', 'WARNING'];

const LEVEL_STYLE = {
  CRITICAL: {
    badge: 'bg-rose-100 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400',
    icon: AlertOctagon,
    dot: 'bg-rose-500',
    terminal: 'text-rose-400',
  },
  ERROR: {
    badge: 'bg-orange-100 text-orange-700 dark:bg-orange-500/10 dark:text-orange-400',
    icon: AlertTriangle,
    dot: 'bg-orange-500',
    terminal: 'text-orange-400',
  },
  WARNING: {
    badge: 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
    icon: Info,
    dot: 'bg-amber-500',
    terminal: 'text-amber-400',
  },
};

// Detect log level from a raw log line string
function detectLevel(line) {
  const u = line.toUpperCase();
  if (u.includes('CRITICAL')) return 'CRITICAL';
  if (u.includes(' ERROR ') || u.includes('] ERROR') || u.includes('ERROR —')) return 'ERROR';
  if (u.includes(' WARNING ') || u.includes('] WARNING') || u.includes('WARNING —')) return 'WARNING';
  if (u.includes(' DEBUG ') || u.includes('] DEBUG')) return 'DEBUG';
  return 'INFO';
}

function terminalLineColor(level) {
  switch (level) {
    case 'CRITICAL': return 'text-rose-400';
    case 'ERROR': return 'text-orange-400';
    case 'WARNING': return 'text-amber-400';
    case 'DEBUG': return 'text-slate-500';
    default: return 'text-emerald-400';
  }
}

function fmtTime(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

function timeAgo(ts) {
  if (!ts) return '';
  const diffMs = Date.now() - new Date(ts).getTime();
  const s = Math.floor(diffMs / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function StatCard({ label, value, tone = 'default', icon: Icon }) {
  const toneClasses = {
    default: 'text-navy-900 dark:text-white',
    critical: 'text-rose-600 dark:text-rose-400',
    warning: 'text-amber-600 dark:text-amber-400',
    error: 'text-orange-600 dark:text-orange-400',
  };
  return (
    <Card className="!p-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</p>
        {Icon && <Icon size={15} className="text-slate-300 dark:text-slate-600" />}
      </div>
      <p className={`mt-1.5 text-2xl font-extrabold ${toneClasses[tone]}`}>{value ?? '—'}</p>
    </Card>
  );
}

function LogRow({ log, expanded, onToggle, onResolve, onUnresolve, onDelete, busy }) {
  const [copied, setCopied] = useState(false);
  const style = LEVEL_STYLE[log.level] || LEVEL_STYLE.ERROR;
  const Icon = style.icon;

  function copyDetail() {
    const text = [
      `Timestamp: ${log.timestamp}`,
      `Level: ${log.level}`,
      `Source: ${log.source}`,
      log.method && log.path ? `Request: ${log.method} ${log.path}` : null,
      log.statusCode ? `Status: ${log.statusCode}` : null,
      `Message: ${log.message}`,
      '',
      log.detail || '(no traceback captured)',
    ].filter(Boolean).join('\n');
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  }

  return (
    <div
      className={`rounded-xl border transition-colors ${
        log.resolved
          ? 'border-slate-100 bg-slate-50/60 dark:border-navy-800 dark:bg-navy-900/40'
          : 'border-slate-200 bg-white dark:border-navy-800 dark:bg-navy-900'
      }`}
    >
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${style.badge}`}>
          <Icon size={15} />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold ${style.badge}`}>
              {log.level}
            </span>
            {log.resolved && (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400">
                <CheckCircle2 size={11} /> Resolved
              </span>
            )}
            {log.source && (
              <span className="truncate text-[11px] font-semibold text-slate-400">{log.source}</span>
            )}
            {log.method && log.path && (
              <span className="truncate rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-500 dark:bg-navy-800 dark:text-slate-400">
                {log.method} {log.path}
              </span>
            )}
          </div>
          <p className="mt-1 truncate text-sm font-semibold text-navy-900 dark:text-white" title={log.message}>
            {log.message}
          </p>
        </div>

        <div className="hidden shrink-0 text-right sm:block">
          <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">{timeAgo(log.timestamp)}</p>
          <p className="text-[10px] text-slate-400">{fmtTime(log.timestamp)}</p>
        </div>

        {expanded ? <ChevronUp size={16} className="shrink-0 text-slate-400" /> : <ChevronDown size={16} className="shrink-0 text-slate-400" />}
      </button>

      {expanded && (
        <div className="border-t border-slate-100 px-4 py-3 dark:border-navy-800">
          <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <p className="text-[10px] font-bold uppercase text-slate-400">Timestamp</p>
              <p className="mt-0.5 flex items-center gap-1 text-xs font-medium text-navy-900 dark:text-white">
                <Clock size={11} className="text-slate-400" /> {fmtTime(log.timestamp)}
              </p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase text-slate-400">Status code</p>
              <p className="mt-0.5 text-xs font-medium text-navy-900 dark:text-white">{log.statusCode || '—'}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase text-slate-400">Module</p>
              <p className="mt-0.5 text-xs font-medium text-navy-900 dark:text-white">
                {log.module || '—'}{log.line ? `:${log.line}` : ''}
              </p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase text-slate-400">Function</p>
              <p className="mt-0.5 text-xs font-medium text-navy-900 dark:text-white">{log.func || '—'}</p>
            </div>
            {log.userEmail && (
              <div>
                <p className="text-[10px] font-bold uppercase text-slate-400">User</p>
                <p className="mt-0.5 text-xs font-medium text-navy-900 dark:text-white">{log.userEmail}</p>
              </div>
            )}
            {log.ip && (
              <div>
                <p className="text-[10px] font-bold uppercase text-slate-400 flex items-center gap-1"><Globe size={10} /> IP</p>
                <p className="mt-0.5 text-xs font-medium text-navy-900 dark:text-white">{log.ip}</p>
              </div>
            )}
            {log.resolved && log.resolvedBy && (
              <div>
                <p className="text-[10px] font-bold uppercase text-slate-400">Resolved by</p>
                <p className="mt-0.5 text-xs font-medium text-navy-900 dark:text-white">{log.resolvedBy}</p>
              </div>
            )}
          </div>

          <div className="relative">
            <p className="mb-1.5 flex items-center gap-1.5 text-[10px] font-bold uppercase text-slate-400">
              <Terminal size={11} /> Full detail / traceback
            </p>
            <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-navy-950 p-3 font-mono text-[11px] leading-relaxed text-slate-200">
              {log.detail || 'No traceback was captured for this log entry.'}
            </pre>
            <button
              onClick={copyDetail}
              className="absolute right-2 top-8 flex items-center gap-1 rounded-lg bg-white/10 px-2 py-1 text-[10px] font-semibold text-white hover:bg-white/20"
            >
              {copied ? <Check size={11} /> : <Copy size={11} />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
            {log.resolved ? (
              <button
                disabled={busy}
                onClick={() => onUnresolve(log.id)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50 dark:border-navy-700 dark:text-slate-300 dark:hover:bg-navy-800"
              >
                Reopen
              </button>
            ) : (
              <button
                disabled={busy}
                onClick={() => onResolve(log.id)}
                className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-600 disabled:opacity-50"
              >
                <CheckCircle2 size={13} /> Mark resolved
              </button>
            )}
            <button
              disabled={busy}
              onClick={() => onDelete(log.id)}
              className="flex items-center gap-1.5 rounded-lg border border-rose-200 px-3 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-50 disabled:opacity-50 dark:border-rose-900 dark:hover:bg-rose-950/40"
            >
              <Trash2 size={13} /> Delete
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live Terminal tab — connects to SSE /api/system-logs/stream
// ---------------------------------------------------------------------------
const MAX_TERMINAL_LINES = 500;

/**
 * Build the correct SSE URL for both dev and production:
 *
 * DEV (Vite on :5173):
 *   Use window.location.origin (:5173) + /api/... so the request goes
 *   through Vite's dev-server proxy → localhost:5050.
 *   Using BASE_URL (http://127.0.0.1:5050) directly works too, but the
 *   Vite proxy handles SSE headers more reliably than a raw cross-origin call.
 *
 * PRODUCTION (cPanel, served from the same domain):
 *   Use window.location.origin + /api/... — Apache reverse proxies it to
 *   Uvicorn. This also avoids hardcoding the domain in the bundle.
 */
function buildSseUrl(token) {
  const qs = token ? `?token=${encodeURIComponent(token)}` : '';
  // Same-origin always works: in dev the Vite proxy forwards it,
  // in prod Apache proxies it — no CORS, no buffering fights.
  return `${window.location.origin}/api/system-logs/stream${qs}`;
}

function LiveTerminal() {
  const [lines, setLines] = useState([]);
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState('idle'); // 'idle' | 'connecting' | 'live' | 'reconnecting' | 'stopped'
  const [retryCount, setRetryCount] = useState(0);
  const [filterLevel, setFilterLevel] = useState('ALL');
  const [search, setSearch] = useState('');
  const esRef = useRef(null);
  const retryTimerRef = useRef(null);
  const intentionalRef = useRef(false); // true when user clicks Disconnect
  const bottomRef = useRef(null);
  const containerRef = useRef(null);
  const [autoScroll, setAutoScroll] = useState(true);

  const [historyPage, setHistoryPage] = useState(1);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [hasMoreHistory, setHasMoreHistory] = useState(true);

  const loadHistoryLogs = useCallback(async () => {
    if (loadingHistory || !hasMoreHistory) return;
    setLoadingHistory(true);
    try {
      const data = await api.getSystemLogs({ page: historyPage, limit: 50 });
      if (!data.logs || data.logs.length === 0 || historyPage >= data.pages) {
        setHasMoreHistory(false);
      }
      if (data.logs && data.logs.length > 0) {
        const histLines = data.logs.map((log) => {
          const level = log.level || 'INFO';
          const formatted = `[${fmtTime(log.timestamp)}] ${level}${log.source ? ` [${log.source}]` : ''}: ${log.message}${log.detail ? ` — ${log.detail}` : ''}`;
          return { text: formatted, level, ts: new Date(log.timestamp).getTime() };
        });
        setLines((prev) => {
          const existing = new Set(prev.map((l) => l.text));
          const uniqueHist = histLines.filter((l) => !existing.has(l.text));
          return [...uniqueHist, ...prev];
        });
        setHistoryPage((p) => p + 1);
      }
    } catch {
      setHasMoreHistory(false);
    } finally {
      setLoadingHistory(false);
    }
  }, [historyPage, loadingHistory, hasMoreHistory]);

  const token = typeof localStorage !== 'undefined' ? localStorage.getItem('orbitavanya_token') : '';
  const MAX_RETRIES = 12;
  const BASE_RETRY_MS = 2000; // starts at 2s, doubles each time up to ~30s

  function _openSource(attempt = 0) {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }

    const url = buildSseUrl(token);
    const es = new EventSource(url);
    esRef.current = es;
    setStatus(attempt === 0 ? 'connecting' : 'reconnecting');
    setConnected(false);

    es.onopen = () => {
      setConnected(true);
      setStatus('live');
      setRetryCount(0);
    };

    es.onmessage = (evt) => {
      const rawLine = evt.data || '';
      if (!rawLine.trim()) return;
      const level = detectLevel(rawLine);
      setLines((prev) => {
        const next = [...prev, { text: rawLine, level, ts: Date.now() }];
        return next.length > MAX_TERMINAL_LINES ? next.slice(-MAX_TERMINAL_LINES) : next;
      });
    };

    es.onerror = () => {
      es.close();
      esRef.current = null;
      setConnected(false);

      // If the user explicitly disconnected, don't retry
      if (intentionalRef.current) {
        setStatus('stopped');
        return;
      }

      const nextAttempt = attempt + 1;
      setRetryCount(nextAttempt);

      if (nextAttempt > MAX_RETRIES) {
        setStatus('stopped');
        return;
      }

      // Exponential backoff: 2s, 4s, 8s … capped at 30s
      const delay = Math.min(BASE_RETRY_MS * 2 ** attempt, 30000);
      setStatus('reconnecting');
      retryTimerRef.current = setTimeout(() => {
        if (!intentionalRef.current) _openSource(nextAttempt);
      }, delay);
    };
  }

  function connect() {
    intentionalRef.current = false;
    if (typeof localStorage !== 'undefined') localStorage.setItem('orbit_terminal_connected', 'true');
    setRetryCount(0);
    _openSource(0);
  }

  function disconnect() {
    intentionalRef.current = true;
    if (typeof localStorage !== 'undefined') localStorage.setItem('orbit_terminal_connected', 'false');
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setConnected(false);
    setStatus('idle');
  }

  // Auto-connect on mount if previously connected by user
  useEffect(() => {
    if (typeof localStorage !== 'undefined' && localStorage.getItem('orbit_terminal_connected') === 'true') {
      connect();
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => () => {
    intentionalRef.current = true;
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    if (esRef.current) esRef.current.close();
  }, []);

  // Status-derived helpers
  const isRunning = status !== 'idle' && status !== 'stopped';
  const statusLabel = {
    idle: 'Offline',
    connecting: 'Connecting…',
    live: 'Live',
    reconnecting: `Reconnecting (${retryCount}/${MAX_RETRIES})…`,
    stopped: retryCount > MAX_RETRIES ? 'Failed — click Connect to retry' : 'Disconnected',
  }[status] ?? status;

  const statusDotClass = {
    live: 'animate-pulse bg-emerald-500',
    connecting: 'animate-pulse bg-amber-400',
    reconnecting: 'animate-pulse bg-amber-400',
    idle: 'bg-slate-400',
    stopped: 'bg-rose-500',
  }[status] ?? 'bg-slate-400';

  const statusBgClass = connected
    ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400'
    : status === 'reconnecting' || status === 'connecting'
      ? 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400'
      : 'bg-slate-100 text-slate-500 dark:bg-navy-800 dark:text-slate-400';

  // Auto-scroll to bottom when new lines come in
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [lines, autoScroll]);

  const visibleLines = lines.filter((l) => {
    if (filterLevel !== 'ALL' && l.level !== filterLevel) return false;
    if (search && !l.text.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  function copyAll() {
    navigator.clipboard.writeText(visibleLines.map((l) => l.text).join('\n')).catch(() => {});
  }

  // ── Inline URL helper for display in the terminal title bar
  const sseUrl = buildSseUrl('');

  return (
    <div className="space-y-3">
      {/* Controls */}
      <Card className="!p-3">
        <div className="flex flex-wrap items-center gap-2">
          {!isRunning ? (
            <button
              onClick={connect}
              className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-600"
            >
              <Radio size={13} /> Connect Live Stream
            </button>
          ) : (
            <button
              onClick={disconnect}
              className="flex items-center gap-1.5 rounded-lg bg-rose-500 px-3 py-2 text-xs font-bold text-white hover:bg-rose-600"
            >
              <Square size={13} /> Disconnect
            </button>
          )}

          {/* Status badge */}
          <div className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold ${statusBgClass}`}>
            <span className={`h-2 w-2 rounded-full ${statusDotClass}`} />
            {statusLabel}
          </div>

          <div className="relative flex-1 min-w-[160px]">
            <Search size={12} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter lines…"
              className="w-full rounded-lg border border-slate-200 bg-slate-50/50 py-1.5 pl-8 pr-3 text-xs outline-none focus:border-brand-400 dark:border-navy-700 dark:bg-navy-800 dark:text-white"
            />
          </div>

          <div className="flex items-center gap-1 rounded-lg border border-slate-200 p-0.5 dark:border-navy-700">
            {['ALL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'].map((lvl) => (
              <button
                key={lvl}
                onClick={() => setFilterLevel(lvl)}
                className={`rounded-md px-2 py-1 text-[10px] font-bold transition-colors ${
                  filterLevel === lvl
                    ? 'bg-brand-500 text-white'
                    : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-navy-800'
                }`}
              >
                {lvl}
              </button>
            ))}
          </div>

          <button
            onClick={() => setAutoScroll((a) => !a)}
            className={`rounded-lg border px-2.5 py-1.5 text-[10px] font-bold transition-colors ${
              autoScroll
                ? 'border-brand-200 bg-brand-50 text-brand-700 dark:border-brand-900 dark:bg-brand-950/40 dark:text-brand-400'
                : 'border-slate-200 text-slate-500 dark:border-navy-700 dark:text-slate-400'
            }`}
          >
            Auto-scroll {autoScroll ? 'on' : 'off'}
          </button>

          <button
            onClick={() => setLines([])}
            className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-[10px] font-semibold text-slate-500 hover:bg-slate-100 dark:border-navy-700 dark:text-slate-400 dark:hover:bg-navy-800"
          >
            Clear
          </button>

          <button
            onClick={copyAll}
            className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-[10px] font-semibold text-slate-500 hover:bg-slate-100 dark:border-navy-700 dark:text-slate-400 dark:hover:bg-navy-800"
          >
            Copy all
          </button>
        </div>
      </Card>

      {/* Reconnecting notice */}
      {status === 'reconnecting' && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs font-medium text-amber-700 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-400">
          ⚡ Server restarted or connection dropped — auto-reconnecting ({retryCount}/{MAX_RETRIES})…
        </div>
      )}
      {status === 'stopped' && retryCount > 0 && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs font-medium text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-400">
          Connection failed after {retryCount} attempts. Click <strong>Connect Live Stream</strong> to try again.
        </div>
      )}

      {/* Terminal window */}
      <div className="relative rounded-xl border border-slate-200 bg-[#0d1117] dark:border-navy-800 overflow-hidden">
        {/* Title bar */}
        <div className="flex items-center gap-2 border-b border-white/10 px-4 py-2">
          <span className="h-3 w-3 rounded-full bg-rose-500" />
          <span className="h-3 w-3 rounded-full bg-amber-500" />
          <span className="h-3 w-3 rounded-full bg-emerald-500" />
          <span className="ml-2 text-[11px] text-slate-400 font-mono truncate" title={sseUrl}>
            {sseUrl.replace(/\?.*/, '')} — live tail
          </span>
          <span className="ml-auto shrink-0 text-[10px] text-slate-500 font-mono">{visibleLines.length} lines</span>
        </div>

        <div
          ref={containerRef}
          className="h-[70vh] max-h-[500px] overflow-y-auto p-3 font-mono text-[11px] leading-relaxed sm:h-[500px]"
          onScroll={(e) => {
            const el = e.currentTarget;
            const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
            setAutoScroll(atBottom);
            if (el.scrollTop < 40 && !loadingHistory && hasMoreHistory) {
              loadHistoryLogs();
            }
          }}
        >
          {loadingHistory && (
            <div className="text-center text-[10px] text-amber-400 py-1 font-mono animate-pulse">
              ⏳ Loading historic server logs…
            </div>
          )}
          {visibleLines.length === 0 ? (
            <p className="text-slate-500 mt-8 text-center">
              {status === 'connecting' || status === 'reconnecting'
                ? '⏳ Connecting to server…'
                : isRunning
                  ? '⏳ Waiting for log lines… (server may be quiet)'
                  : '⬆ Click "Connect Live Stream" to start tailing the server log.'}
            </p>
          ) : (
            visibleLines.map((l, i) => (
              <div key={i} className={`hover:bg-white/5 px-1 py-0.5 rounded break-words ${terminalLineColor(l.level)}`}>
                {l.text}
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main ServerLogs page
// ---------------------------------------------------------------------------
export default function ServerLogs() {
  const { refreshSummary } = useErrorLogs();

  const [activeTab, setActiveTab] = useState('errors'); // 'errors' | 'terminal'
  const [logs, setLogs] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [expandedId, setExpandedId] = useState(null);

  const [level, setLevel] = useState('ALL');
  const [resolvedFilter, setResolvedFilter] = useState('unresolved');
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);

  const [autoRefresh, setAutoRefresh] = useState(true);
  const [testing, setTesting] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const timerRef = useRef(null);
  const listScrollRef = useRef(null);

  function buildParams(pageNum) {
    return {
      page: pageNum,
      limit: 20,
      q: search || undefined,
      level: level === 'ALL' ? undefined : level,
      resolved: resolvedFilter === 'all' ? undefined : resolvedFilter === 'resolved',
    };
  }

  // Full reset — used when filters/search change. Replaces the whole list.
  const resetAndLoad = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      const [logsData, summaryData] = await Promise.all([
        api.getSystemLogs(buildParams(1)),
        api.getSystemLogsSummary(),
      ]);
      setLogs(logsData.logs || []);
      setPage(1);
      setPages(logsData.pages || 1);
      setTotal(logsData.total || 0);
      setSummary(summaryData);
    } catch (err) {
      setLoadError(err.message || 'Could not load server logs.');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, level, resolvedFilter]);

  // Lightweight top-up — used by the 15s auto-refresh. Merges the latest
  // first page into whatever's already loaded instead of collapsing back
  // to page 1, so scrolling further down the list isn't reset.
  const refreshTop = useCallback(async () => {
    try {
      const [logsData, summaryData] = await Promise.all([
        api.getSystemLogs(buildParams(1)),
        api.getSystemLogsSummary(),
      ]);
      const fresh = logsData.logs || [];
      setLogs((prev) => {
        const freshIds = new Set(fresh.map((l) => l.id));
        const rest = prev.filter((l) => !freshIds.has(l.id));
        return [...fresh, ...rest];
      });
      setPages(logsData.pages || 1);
      setTotal(logsData.total || 0);
      setSummary(summaryData);
    } catch (err) {
      setLoadError(err.message || 'Could not refresh server logs.');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, level, resolvedFilter]);

  // Appends the next page — triggered when the list is scrolled near the bottom.
  const loadMore = useCallback(async () => {
    setPage((currentPage) => {
      if (loadingMore || currentPage >= pages) return currentPage;
      const nextPage = currentPage + 1;
      setLoadingMore(true);
      api.getSystemLogs(buildParams(nextPage))
        .then((logsData) => {
          const newItems = logsData.logs || [];
          setLogs((prev) => {
            const existingIds = new Set(prev.map((l) => l.id));
            return [...prev, ...newItems.filter((l) => !existingIds.has(l.id))];
          });
          setPages(logsData.pages || pages);
          setTotal(logsData.total || total);
        })
        .catch((err) => setLoadError(err.message || 'Could not load more server logs.'))
        .finally(() => setLoadingMore(false));
      return nextPage;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadingMore, pages, total, search, level, resolvedFilter]);

  function handleLogsScroll(e) {
    const el = e.currentTarget;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 200;
    if (nearBottom) loadMore();
  }

  useEffect(() => {
    resetAndLoad();
  }, [resetAndLoad]);

  useEffect(() => {
    if (!autoRefresh) {
      if (timerRef.current) clearInterval(timerRef.current);
      return;
    }
    timerRef.current = setInterval(refreshTop, 15000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [autoRefresh, refreshTop]);

  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput);
    }, 350);
    return () => clearTimeout(t);
  }, [searchInput]);

  const load = resetAndLoad; // kept as the name other handlers below already call

  async function handleResolve(id) {
    setBusyId(id);
    try {
      await api.resolveSystemLog(id);
      setLogs((prev) => resolvedFilter === 'unresolved' ? prev.filter((l) => l.id !== id) : prev.map((l) => l.id === id ? { ...l, resolved: true } : l));
      refreshSummary();
      load();
    } catch (err) {
      setLoadError(err.message || 'Could not resolve log entry.');
    } finally {
      setBusyId(null);
    }
  }

  async function handleUnresolve(id) {
    setBusyId(id);
    try {
      await api.unresolveSystemLog(id);
      load();
      refreshSummary();
    } catch (err) {
      setLoadError(err.message || 'Could not reopen log entry.');
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(id) {
    setBusyId(id);
    try {
      await api.deleteSystemLog(id);
      setLogs((prev) => prev.filter((l) => l.id !== id));
      refreshSummary();
    } catch (err) {
      setLoadError(err.message || 'Could not delete log entry.');
    } finally {
      setBusyId(null);
    }
  }

  async function handleTestError() {
    setTesting(true);
    try {
      await api.triggerTestSystemLog();
      setTimeout(load, 1200);
    } catch (err) {
      setLoadError(err.message || 'Could not trigger test error.');
    } finally {
      setTesting(false);
    }
  }

  async function handleClearAll() {
    if (!window.confirm('Are you sure you want to clear all server logs?')) {
      return;
    }
    setClearing(true);
    try {
      await api.clearSystemLogs('all');
      load();
      refreshSummary();
    } catch (err) {
      setLoadError(err.message || 'Could not clear all logs.');
    } finally {
      setClearing(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Server Logs"
        subtitle="Live backend errors, warnings, and tracebacks — captured automatically from every request."
        action={
          <div className="flex flex-wrap items-center gap-2">
            {activeTab === 'errors' && (
              <>
                <button
                  onClick={() => setAutoRefresh((a) => !a)}
                  className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold transition-colors ${
                    autoRefresh
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-400'
                      : 'border-slate-200 text-slate-500 dark:border-navy-700 dark:text-slate-400'
                  }`}
                  title="Toggle 15s auto-refresh"
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${autoRefresh ? 'animate-pulse bg-emerald-500' : 'bg-slate-300'}`} />
                  Auto-refresh {autoRefresh ? 'on' : 'off'}
                </button>
                <button
                  onClick={load}
                  className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-300 dark:hover:bg-navy-800"
                >
                  <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
                </button>
                <button
                  onClick={handleTestError}
                  disabled={testing}
                  className="flex items-center gap-1.5 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-xs font-semibold text-brand-700 hover:bg-brand-100 disabled:opacity-50 dark:border-brand-900 dark:bg-brand-950/40 dark:text-brand-400"
                  title="Emit a synthetic error to verify logging end-to-end"
                >
                  {testing ? <Loader2 size={13} className="animate-spin" /> : <FlaskConical size={13} />} Test pipeline
                </button>
              </>
            )}
          </div>
        }
      />

      {/* Tab switcher */}
      <div className="mb-5 flex gap-1 rounded-xl border border-slate-200 p-1 w-fit dark:border-navy-700">
        <button
          onClick={() => setActiveTab('errors')}
          className={`flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
            activeTab === 'errors'
              ? 'bg-navy-900 text-white dark:bg-white dark:text-navy-900'
              : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-navy-800'
          }`}
        >
          <AlertTriangle size={14} /> Error Logs
          {summary?.unresolved > 0 && (
            <span className="rounded-full bg-rose-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
              {summary.unresolved}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab('terminal')}
          className={`flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
            activeTab === 'terminal'
              ? 'bg-navy-900 text-white dark:bg-white dark:text-navy-900'
              : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-navy-800'
          }`}
        >
          <Terminal size={14} /> Live Terminal
        </button>
      </div>

      <div className={activeTab === 'terminal' ? '' : 'hidden'}>
        <LiveTerminal />
      </div>
      <div className={activeTab === 'terminal' ? 'hidden' : ''}>
        <>
          {/* Summary cards */}
          <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <StatCard label="Total logs" value={summary?.total} icon={Server} />
            <StatCard label="Unresolved" value={summary?.unresolved} icon={AlertTriangle} />
            <StatCard label="Critical" value={summary?.critical} tone="critical" icon={AlertOctagon} />
            <StatCard label="Errors" value={summary?.errors} tone="error" icon={AlertTriangle} />
            <StatCard label="Warnings" value={summary?.warnings} tone="warning" icon={Info} />
            <StatCard label="Last 24h" value={summary?.last24h} icon={Clock} />
          </div>

          {/* Filter bar */}
          <Card className="mb-4 !p-3">
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative flex-1 min-w-[200px]">
                <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  placeholder="Search message, traceback, source, path…"
                  className="w-full rounded-lg border border-slate-200 bg-slate-50/50 py-2 pl-9 pr-3 text-sm outline-none focus:border-brand-400 dark:border-navy-700 dark:bg-navy-800 dark:text-white"
                />
                {searchInput && (
                  <button onClick={() => setSearchInput('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                    <X size={13} />
                  </button>
                )}
              </div>

              <div className="flex items-center gap-1 rounded-lg border border-slate-200 p-0.5 dark:border-navy-700">
                {LEVELS.map((lvl) => (
                  <button
                    key={lvl}
                    onClick={() => { setLevel(lvl); setPage(1); }}
                    className={`rounded-md px-2.5 py-1.5 text-xs font-bold transition-colors ${
                      level === lvl
                        ? 'bg-brand-500 text-white'
                        : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-navy-800'
                    }`}
                  >
                    {lvl}
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-1 rounded-lg border border-slate-200 p-0.5 dark:border-navy-700">
                {[
                  { key: 'unresolved', label: 'Unresolved' },
                  { key: 'resolved', label: 'Resolved' },
                  { key: 'all', label: 'All' },
                ].map((opt) => (
                  <button
                    key={opt.key}
                    onClick={() => { setResolvedFilter(opt.key); setPage(1); }}
                    className={`rounded-md px-2.5 py-1.5 text-xs font-bold transition-colors ${
                      resolvedFilter === opt.key
                        ? 'bg-navy-900 text-white dark:bg-white dark:text-navy-900'
                        : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-navy-800'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>

              <button
                onClick={handleClearAll}
                disabled={clearing}
                className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-50 disabled:opacity-50 dark:text-rose-400 dark:hover:bg-rose-950/40"
                title="Delete all log entries"
              >
                <Trash2 size={13} /> Clear all
              </button>
            </div>
          </Card>

          {loadError && (
            <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-400">
              {loadError}
            </div>
          )}

          {loading && logs.length === 0 ? (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-400">
              <Loader2 size={16} className="animate-spin" /> Loading server logs…
            </div>
          ) : logs.length === 0 ? (
            <Card className="py-16 text-center">
              <CheckCircle2 size={28} className="mx-auto mb-2 text-emerald-500" />
              <p className="text-sm font-semibold text-navy-900 dark:text-white">No matching log entries</p>
              <p className="mt-1 text-xs text-slate-400">
                {resolvedFilter === 'unresolved' ? "Nothing unresolved — the backend is running clean." : 'Try a different filter or search term.'}
              </p>
            </Card>
          ) : (
            <div
              ref={listScrollRef}
              onScroll={handleLogsScroll}
              className="max-h-[70vh] space-y-2 overflow-y-auto pr-1"
            >
              {logs.map((log) => (
                <LogRow
                  key={log.id}
                  log={log}
                  expanded={expandedId === log.id}
                  onToggle={() => setExpandedId((id) => (id === log.id ? null : log.id))}
                  onResolve={handleResolve}
                  onUnresolve={handleUnresolve}
                  onDelete={handleDelete}
                  busy={busyId === log.id}
                />
              ))}

              {loadingMore && (
                <div className="flex items-center justify-center gap-2 py-4 text-xs text-slate-400">
                  <Loader2 size={14} className="animate-spin" /> Loading more…
                </div>
              )}
              {!loadingMore && page >= pages && (
                <p className="py-3 text-center text-[11px] text-slate-400">
                  {total} total · end of list
                </p>
              )}
            </div>
          )}
        </>
      </div>
    </div>
  );
}
