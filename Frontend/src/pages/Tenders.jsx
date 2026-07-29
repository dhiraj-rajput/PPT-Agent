import { useState, useMemo, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Search, DollarSign, Calendar, Building2, MapPin, Mail,
  RefreshCw, AlertCircle, Loader2, Database, CheckCircle2,
  ChevronLeft, ChevronRight, X, Filter, Trophy, Clock, AlertOctagon, SlidersHorizontal, Eye, FileText, Check, HelpCircle
} from 'lucide-react';
import { PageHeader, Card, MatchBadge, StatusBadge, renderSafeText } from '../components/ui/Common.jsx';
import { tenders as staticTenders, daysUntilClosing } from '../data/tenders.jsx';
import { api } from '../lib/api.jsx';

const SET_ASIDE_OPTIONS = [
  { value: '', label: 'All Set-Asides' },
  { value: 'SBA', label: 'Small Business (SBA)' },
  { value: 'WOSB', label: 'Women-Owned Small Business' },
  { value: 'SDVOSBC', label: 'Service-Disabled Veteran' },
  { value: '8A', label: '8(a) Program' },
  { value: 'HZC', label: 'HUBZone' },
  { value: 'VSB', label: 'Veteran-Owned Small Business' },
];

export default function Tenders() {
  const navigate = useNavigate();
  // ----- Data States -----
  const [tenders, setTenders] = useState([]);
  const [total, setTotal] = useState(0);
  const [naicsCodes, setNaicsCodes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [backendOffline, setBackendOffline] = useState(false);
  const [cacheEmpty, setCacheEmpty] = useState(false);

  // ----- Filter States (local search against cached data) -----
  const [query, setQuery] = useState('');
  const [naicsFilter, setNaicsFilter] = useState('');
  const [setAsideFilter, setSetAsideFilter] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 20;

  // Status counts for summary bar
  const [statusCounts, setStatusCounts] = useState({});
  const [statusFilter, setStatusFilter] = useState('All');
  const [urgencyFilter, setUrgencyFilter] = useState('All');

  // Sync States
  const [syncOpen, setSyncOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [syncMeta, setSyncMeta] = useState(null);

  // Document viewer states
  const [docsModal, setDocsModal] = useState(null); // noticeId | null
  const [tenderDocs, setTenderDocs] = useState([]);
  const [docsLoading, setDocsLoading] = useState(false);

  // Sync Form -----
  const [syncForm, setSyncForm] = useState({
    naicsCode: '',
    keyword: '',
    typeOfSetAsideCode: '',
    active: 'Yes',
    limit: 25,
    offset: 0,
    api_source: 'sam_gov', // 'sam_gov' | 'companies_house_uk'
  });

  // ----- Fetch cached tenders from backend -----
  const fetchTenders = useCallback(() => {
    setLoading(true);
    const params = { page: currentPage, limit: itemsPerPage };
    if (query) params.query = query;
    if (naicsFilter) params.naics = naicsFilter;
    if (setAsideFilter) params.set_aside = setAsideFilter;
    if (statusFilter !== 'All') params.status = statusFilter;
    if (urgencyFilter !== 'All') params.urgency = urgencyFilter;

    api.getTenders(params)
      .then(data => {
        setBackendOffline(false);
        setCacheEmpty(data.cache_empty || false);
        setTenders(data.tenders || []);
        setTotal(data.total || 0);
        if (data.naics_codes?.length) setNaicsCodes(data.naics_codes);
        if (data.status_counts) setStatusCounts(data.status_counts);
        setLoading(false);
      })
      .catch(() => {
        setBackendOffline(true);
        // Fall back to static data
        const q = query.toLowerCase();
        const filtered = staticTenders.filter(t =>
          !q || t.title.toLowerCase().includes(q)
        );
        setTenders(filtered);
        setTotal(filtered.length);
        setLoading(false);
      });
  }, [currentPage, query, naicsFilter, setAsideFilter, statusFilter, urgencyFilter]);

  // ----- Fetch sync metadata -----
  const fetchMeta = () => {
    api.getTendersMeta()
      .then(data => setSyncMeta(data))
      .catch(() => {});
  };

  const fetchTenderDocs = async (noticeId) => {
    setDocsLoading(true);
    setTenderDocs([]);
    setDocsModal(noticeId);
    try {
      const data = await api.getTenderDocuments(noticeId);
      setTenderDocs(data.documents || []);
    } catch (err) {
      console.warn('Could not fetch tender documents:', err);
      setTenderDocs([]);
    } finally {
      setDocsLoading(false);
    }
  };

  useEffect(() => { fetchTenders(); fetchMeta(); }, [fetchTenders]);
  useEffect(() => { setCurrentPage(1); }, [query, naicsFilter, setAsideFilter, statusFilter, urgencyFilter]);

  // ----- Trigger SAM.gov Sync -----
  const handleSync = (e) => {
    e.preventDefault();
    setSyncing(true);
    setSyncResult(null);
    const body = { ...syncForm };
    // Clean empty strings
    Object.keys(body).forEach(k => { if (body[k] === '') delete body[k]; });

    api.syncTenders(body)
      .then(data => {
        setSyncResult({ ok: true, message: data.message, fetched: data.fetched });
        setSyncing(false);
        fetchTenders();
        fetchMeta();
      })
      .catch(err => {
        setSyncResult({ ok: false, message: err.message });
        setSyncing(false);
      });
  };

  const pageCount = Math.ceil(total / itemsPerPage);

  return (
    <div>
      <PageHeader
        title="Tenders"
        subtitle={
          backendOffline
            ? `${tenders.length} tenders (static demo data — backend offline)`
            : cacheEmpty
            ? 'No tenders cached yet — use Sync to fetch from SAM.gov'
            : `${total.toLocaleString()} tenders cached from SAM.gov`
        }
        action={
          !backendOffline && (
            <button
              onClick={() => setSyncOpen(true)}
              className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft hover:bg-brand-600 transition-colors"
            >
              <RefreshCw size={15} /> Sync from SAM.gov
            </button>
          )
        }
      />

      {/* ── Backend-offline banner ── */}
      {backendOffline && (
        <div className="mb-5 flex items-start gap-3 rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-700 dark:bg-amber-950/30 dark:border-amber-900/30 dark:text-amber-400">
          <AlertCircle size={18} className="shrink-0 mt-0.5" />
          <div>
            <p className="font-bold">Backend Offline — Showing Static Demo Data</p>
            <p className="text-xs mt-0.5">
              Start the server with <code className="bg-amber-100/60 dark:bg-amber-950/40 px-1 rounded">uv run server.py</code> to
              fetch live tenders from SAM.gov and enable the Sync feature.
            </p>
          </div>
        </div>
      )}

      {/* ── Cache-empty prompt ── */}
      {!backendOffline && cacheEmpty && (
        <div className="mb-5 flex items-start gap-3 rounded-xl bg-sky-50 border border-sky-200 p-4 text-sm text-sky-700 dark:bg-sky-950/30 dark:border-sky-900/30 dark:text-sky-400">
          <Database size={18} className="shrink-0 mt-0.5" />
          <div>
            <p className="font-bold">Tenders Cache is Empty</p>
            <p className="text-xs mt-0.5">
              Click <strong>Sync from SAM.gov</strong> above to pull live federal opportunities. Enter a NAICS code or keyword to target specific sectors.
              <br />
              <span className="opacity-75">SAM.gov free tier allows 10 requests/day — results are cached permanently in MongoDB.</span>
            </p>
          </div>
        </div>
      )}

      {/* ── Sync metadata strip ── */}
      {syncMeta?.last_synced && !backendOffline && (
        <div className="mb-4 flex items-center gap-2 text-xs text-slate-400 dark:text-slate-500">
          <CheckCircle2 size={13} className="text-emerald-500" />
          Last synced {syncMeta.last_synced.replace('T', ' ').replace('Z', ' UTC')} ·{' '}
          {syncMeta.total_cached.toLocaleString()} cached ·{' '}
          {syncMeta.quota_used_today}/10 API calls used today
          <span className="opacity-60">· Register a SAM.gov role for 1,000/day</span>
        </div>
      )}

      {/* ── Lifecycle status summary bar ── */}
      {!backendOffline && !cacheEmpty && Object.keys(statusCounts).length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {[
            { key: 'All', label: 'All', color: 'bg-slate-100 text-slate-600 dark:bg-navy-800 dark:text-slate-300', icon: null },
            { key: 'Open', label: 'Open', color: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400', icon: null },
            { key: 'Closing Soon', label: 'Closing Soon', color: 'bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400', icon: Clock },
            { key: 'Expired', label: 'Expired', color: 'bg-slate-100 text-slate-500 dark:bg-navy-800 dark:text-slate-500', icon: AlertOctagon },
            { key: 'Won', label: 'Won', color: 'bg-violet-50 text-violet-700 dark:bg-violet-950/30 dark:text-violet-400', icon: Trophy },
          ].map(({ key, label, color, icon: Icon }) => {
            const count = key === 'All' ? Object.values(statusCounts).reduce((a, b) => a + b, 0) : (statusCounts[key] || 0);
            return (
              <button
                key={key}
                onClick={() => setStatusFilter(key)}
                className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold transition-all ${
                  statusFilter === key
                    ? color + ' ring-2 ring-offset-1 ring-brand-400'
                    : color + ' opacity-70 hover:opacity-100'
                }`}
              >
                {Icon && <Icon size={11} />}
                {label} <span className="font-bold ml-0.5">{count}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* ── Filters Bar ── */}
      <Card className="!p-4">
        <div className="flex flex-wrap items-center gap-3">
          {/* Search */}
          <div className="flex flex-1 min-w-[220px] items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 dark:border-navy-700 dark:bg-navy-800">
            <Search size={16} className="text-slate-400 dark:text-slate-500" />
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search title, agency, solicitation #..."
              className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400 dark:placeholder:text-slate-500 dark:text-white"
            />
            {query && (
              <button onClick={() => setQuery('')} className="text-slate-300 hover:text-slate-500">
                <X size={14} />
              </button>
            )}
          </div>

          {/* NAICS filter */}
          {naicsCodes.length > 0 ? (
            <select
              value={naicsFilter}
              onChange={e => setNaicsFilter(e.target.value)}
              className="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-white cursor-pointer"
            >
              <option value="">All NAICS Codes</option>
              {naicsCodes.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          ) : (
            <input
              value={naicsFilter}
              onChange={e => setNaicsFilter(e.target.value)}
              placeholder="NAICS code filter…"
              className="w-36 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-navy-900 placeholder:text-slate-400 dark:border-navy-700 dark:bg-navy-800 dark:text-white"
            />
          )}

          {/* Set-aside filter */}
          <select
            value={setAsideFilter}
            onChange={e => setSetAsideFilter(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-white cursor-pointer"
          >
            {SET_ASIDE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>

          {/* Urgency filter */}
          <select
            value={urgencyFilter}
            onChange={e => setUrgencyFilter(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-white cursor-pointer"
          >
            <option value="All">All Urgency</option>
            <option value="critical">Critical (&lt;7 days)</option>
            <option value="warning">Warning (&lt;30 days)</option>
            <option value="normal">Normal</option>
            <option value="expired">Expired</option>
            <option value="won">Won</option>
          </select>
        </div>
      </Card>

      {/* ── Tenders Grid ── */}
      {loading ? (
        <Card className="mt-5 flex flex-col items-center justify-center py-20">
          <Loader2 className="animate-spin text-brand-500" size={32} />
          <p className="mt-4 text-sm text-slate-500 dark:text-slate-400 font-medium">Loading tenders...</p>
        </Card>
      ) : tenders.length === 0 ? (
        <Card className="mt-5 flex flex-col items-center justify-center py-20 text-center">
          <Database size={36} className="text-slate-300 dark:text-slate-600 mb-3" />
          <p className="text-sm font-semibold text-navy-900 dark:text-white">No tenders found</p>
          <p className="mt-1 text-xs text-slate-400 max-w-xs">
            {cacheEmpty
              ? 'Click "Sync from SAM.gov" to fetch live federal opportunities.'
              : 'Try adjusting your search and filter criteria.'}
          </p>
        </Card>
      ) : (
        <>
          <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
            {tenders.map(t => {
              const id = t.id || t.noticeId;
              const daysLeft = t.days_until_close ?? daysUntilClosing(t.closingDate || t.closing_date);
              const closingStr = t.closing_date || t.closingDate || '';

              // Urgency → card border accent
              const urgencyBorder = {
                critical: 'border-rose-300 dark:border-rose-800',
                warning:  'border-amber-300 dark:border-amber-800',
                won:      'border-violet-300 dark:border-violet-800',
                expired:  'border-slate-200 dark:border-navy-800 opacity-75',
                normal:   '',
              }[t.urgency] || '';

              // Status badge colours
              const statusColour = {
                'Open':          'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400',
                'Closing Soon':  'bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400',
                'Expired':       'bg-slate-100 text-slate-500 dark:bg-navy-900 dark:text-slate-500',
                'Won':           'bg-violet-50 text-violet-700 dark:bg-violet-950/30 dark:text-violet-400',
                'Closed':        'bg-slate-100 text-slate-400',
              }[t.status] || 'bg-slate-100 text-slate-500';

              return (
                <div onClick={() => navigate(`/tenders/${id}`)} className="cursor-pointer" key={id}>
                  <Card className={`h-full transition-all hover:shadow-soft dark:hover:border-brand-500/50 ${urgencyBorder}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="rounded-full bg-brand-50 px-2.5 py-1 text-[11px] font-semibold text-brand-600 dark:bg-navy-800 dark:text-brand-400">
                          {t.category || t.type || 'Solicitation'}
                        </span>
                        {t.set_aside && (
                          <span className="rounded-full bg-violet-50 px-2.5 py-1 text-[11px] font-semibold text-violet-600 dark:bg-navy-800 dark:text-violet-400">
                            {t.set_aside_code || t.set_aside}
                          </span>
                        )}
                        {t.naics_code && (
                          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-mono text-slate-500 dark:bg-navy-800 dark:text-slate-400">
                            {t.naics_code}
                          </span>
                        )}
                      </div>
                      <MatchBadge score={t.match || t.matchScore} />
                    </div>

                    <h3 className="mt-3 text-sm font-bold leading-snug text-navy-900 dark:text-white line-clamp-2">
                       {t.title}
                    </h3>
                    {t.solicitation_number && (
                      <p className="mt-0.5 text-[11px] text-slate-400 font-mono">{t.solicitation_number}</p>
                    )}
                    <p className="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400 line-clamp-2">
                      {t.description}
                    </p>

                    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-slate-500 dark:text-slate-400">
                      <span className="flex items-center gap-1"><Building2 size={12} />{renderSafeText(t.agency)}</span>
                      <span className="flex items-center gap-1"><DollarSign size={12} />{renderSafeText(t.value || t.award_amount)}</span>
                      {t.place_of_performance && (
                        <span className="flex items-center gap-1"><MapPin size={12} />{renderSafeText(t.place_of_performance)}</span>
                      )}
                    </div>

                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        {/* Lifecycle badge */}
                        <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold ${statusColour}`}>
                          {t.status}
                        </span>
                        {/* Days remaining / overdue */}
                        {t.status === 'Won' && t.award_awardee && (
                          <span className="text-[10px] text-violet-600 dark:text-violet-400 font-medium">
                            → {t.award_awardee}
                          </span>
                        )}
                        {t.status !== 'Won' && t.status !== 'Expired' && daysLeft !== null && daysLeft >= 0 && (
                          <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                            daysLeft <= 7
                              ? 'bg-rose-50 text-rose-600 dark:bg-rose-950/30 dark:text-rose-400'
                              : daysLeft <= 30
                              ? 'bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400'
                              : 'bg-slate-100 text-slate-500 dark:bg-navy-900 dark:text-slate-400'
                          }`}>
                            {daysLeft}d left
                          </span>
                        )}
                        {t.status === 'Expired' && closingStr && (
                          <span className="text-[10px] text-slate-400">Closed {closingStr}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-1 text-[10px] text-slate-400">
                        <Calendar size={11} />
                        <span>{t.posted_date || t.postedDate}</span>
                        {closingStr && <><span>→</span><span>{closingStr}</span></>}
                      </div>
                    </div>

                    {/* POC email if available */}
                    {t.poc_email && (
                      <div className="mt-2 flex items-center gap-1 text-[10px] text-slate-400 dark:text-slate-500">
                        <Mail size={11} />
                        <a href={`mailto:${t.poc_email}`} onClick={e => e.stopPropagation()} className="hover:text-brand-500">
                          {t.poc_email}
                        </a>
                      </div>
                    )}
                    
                    <div className="mt-4 pt-3 border-t border-slate-100 dark:border-navy-700/50 flex justify-end">
                      <button
                        onClick={(e) => { e.stopPropagation(); fetchTenderDocs(id); }}
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-200 dark:hover:bg-navy-700 transition-colors"
                        title="View downloaded documents"
                      >
                        <FileText size={12} /> Docs
                      </button>
                    </div>
                  </Card>
                </div>
              );
            })}
          </div>

          {/* Pagination */}
          {pageCount > 1 && (
            <div className="mt-5 flex items-center justify-between">
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Showing <span className="font-semibold text-navy-900 dark:text-white">{(currentPage - 1) * itemsPerPage + 1}</span> –{' '}
                <span className="font-semibold text-navy-900 dark:text-white">{Math.min(currentPage * itemsPerPage, total)}</span> of{' '}
                <span className="font-semibold text-navy-900 dark:text-white">{total.toLocaleString()}</span> tenders
              </p>
              <div className="flex gap-2">
                <button
                  disabled={currentPage === 1}
                  onClick={() => setCurrentPage(p => p - 1)}
                  className="flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 disabled:opacity-50 dark:border-navy-700 dark:text-white dark:hover:bg-navy-800"
                >
                  <ChevronLeft size={14} /> Prev
                </button>
                <button
                  disabled={currentPage === pageCount}
                  onClick={() => setCurrentPage(p => p + 1)}
                  className="flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 disabled:opacity-50 dark:border-navy-700 dark:text-white dark:hover:bg-navy-800"
                >
                  Next <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Sync Modal ── */}
      {syncOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/70 p-4 backdrop-blur-md"
          onClick={() => { setSyncOpen(false); setSyncResult(null); }}
        >
          <div
            className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl bg-white dark:bg-navy-800 shadow-2xl border border-slate-100 dark:border-navy-700"
            onClick={e => e.stopPropagation()}
          >
            {/* Modal header */}
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-navy-700 p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-navy-900 dark:text-brand-400">
                  <RefreshCw size={18} />
                </div>
                <div>
                  <h3 className="text-sm font-extrabold text-navy-900 dark:text-white">Sync from SAM.gov</h3>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Uses 1 of your 10 daily API calls · Results cached permanently
                  </p>
                </div>
              </div>
              <button
                onClick={() => { setSyncOpen(false); setSyncResult(null); }}
                className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-navy-900"
              >
                <X size={16} />
              </button>
            </div>

            {/* Sync result */}
            {syncResult && (
              <div className={`mx-5 mt-4 rounded-xl px-4 py-3 text-sm font-medium ${
                syncResult.ok
                  ? 'bg-emerald-50 border border-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400'
                  : 'bg-rose-50 border border-rose-100 text-rose-600 dark:bg-rose-950/20 dark:text-rose-400'
              }`}>
                {syncResult.ok ? '✓ ' : '✗ '}{syncResult.message}
                {syncResult.ok && syncResult.fetched > 0 && (
                  <span className="ml-1 opacity-70">({syncResult.fetched} fetched)</span>
                )}
              </div>
            )}

            {/* Sync form */}
            <form onSubmit={handleSync} className="p-5 space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">
                    NAICS Code
                    <span className="ml-1 font-normal text-slate-400">(e.g. 541511)</span>
                  </label>
                  <input
                    value={syncForm.naicsCode}
                    onChange={e => setSyncForm(f => ({ ...f, naicsCode: e.target.value }))}
                    placeholder="541511"
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm font-mono outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">
                    Set-Aside Type
                  </label>
                  <select
                    value={syncForm.typeOfSetAsideCode}
                    onChange={e => setSyncForm(f => ({ ...f, typeOfSetAsideCode: e.target.value }))}
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white cursor-pointer"
                  >
                    {SET_ASIDE_OPTIONS.map(o => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">
                  Keyword / Title Search
                </label>
                <input
                  value={syncForm.keyword}
                  onChange={e => setSyncForm(f => ({ ...f, keyword: e.target.value }))}
                  placeholder="e.g. AI software, cybersecurity, cloud migration"
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">Status</label>
                  <select
                    value={syncForm.active}
                    onChange={e => setSyncForm(f => ({ ...f, active: e.target.value }))}
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white cursor-pointer"
                  >
                    <option value="Yes">Active Only</option>
                    <option value="No">Archived Only</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">
                    Max Results
                    <span className="ml-1 font-normal text-slate-400">(max 25)</span>
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={25}
                    value={syncForm.limit}
                    onChange={e => setSyncForm(f => ({ ...f, limit: Number(e.target.value) }))}
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">
                    Offset
                    <span className="ml-1 font-normal text-slate-400">(pagination)</span>
                  </label>
                  <input
                    type="number"
                    min={0}
                    value={syncForm.offset}
                    onChange={e => setSyncForm(f => ({ ...f, offset: Number(e.target.value) }))}
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                  />
                </div>
              </div>

              <div className="rounded-xl bg-slate-50 dark:bg-navy-900 border border-slate-100 dark:border-navy-700 p-3 text-xs text-slate-500 dark:text-slate-400">
                <Filter size={12} className="inline mr-1.5 text-brand-500" />
                All fields are optional. Leave blank to fetch the 25 most recently posted active opportunities.
                Results are <strong>upserted</strong> into MongoDB — existing records are refreshed, not duplicated.
              </div>

              <div className="mb-4">
                <label className="block text-xs font-semibold text-slate-600 dark:text-slate-300 mb-1.5">
                  Data Source
                </label>
                <select
                  id="sync-api-source"
                  value={syncForm.api_source}
                  onChange={e => setSyncForm(f => ({ ...f, api_source: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3 py-2 text-sm text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-400"
                >
                  <option value="sam_gov">SAM.gov (USA Federal Tenders)</option>
                  <option value="companies_house_uk" disabled>Companies House UK (Coming Soon)</option>
                  <option value="find_a_tender_uk" disabled>Find a Tender UK (Coming Soon)</option>
                </select>
                <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">
                  Additional sources (UK, EU) will be available in future updates.
                </p>
              </div>

              <div className="flex justify-end gap-3 pt-1 border-t border-slate-100 dark:border-navy-700">
                <button
                  type="button"
                  onClick={() => { setSyncOpen(false); setSyncResult(null); }}
                  className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={syncing}
                  className="flex items-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 text-xs font-bold text-white shadow-soft hover:bg-brand-600 disabled:opacity-70 transition-colors"
                >
                  {syncing ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
                  {syncing ? 'Fetching from SAM.gov…' : 'Sync Now'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Tender Documents Modal */}
      {docsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/80 p-4 backdrop-blur-md" onClick={() => setDocsModal(null)}>
          <div className="w-full max-w-2xl rounded-2xl bg-white dark:bg-navy-800 shadow-2xl overflow-hidden border border-slate-100 dark:border-navy-700" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-navy-700 p-5">
              <div>
                <h3 className="text-base font-extrabold text-navy-900 dark:text-white">Tender Documents</h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">Downloaded attachments and requirements</p>
              </div>
              <button onClick={() => setDocsModal(null)} className="rounded-lg p-2 text-slate-400 hover:text-navy-950 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-navy-900 transition-colors">
                <X size={20} />
              </button>
            </div>
            <div className="p-5 max-h-[60vh] overflow-y-auto">
              {docsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="animate-spin text-brand-500" size={28} />
                  <p className="ml-3 text-sm text-slate-500">Loading documents...</p>
                </div>
              ) : tenderDocs.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-center">
                  <FileText className="text-slate-300 dark:text-slate-600 mb-3" size={36} />
                  <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">No documents downloaded yet</p>
                  <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                    Documents are downloaded when you sync this tender. Try syncing again.
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {tenderDocs.map((doc) => (
                    <div key={doc.filename} className="flex items-center justify-between rounded-xl border border-slate-100 dark:border-navy-700 bg-slate-50 dark:bg-navy-900 p-3.5 hover:bg-slate-100 dark:hover:bg-navy-800 transition-colors">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600 dark:bg-navy-800 dark:text-brand-400">
                          <FileText size={16} />
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-navy-900 dark:text-white truncate">{doc.filename}</p>
                          <p className="text-xs text-slate-400 dark:text-slate-500">{doc.type} · {doc.size}</p>
                        </div>
                      </div>
                      <a
                        href={api.getTenderDocumentUrl ? api.getTenderDocumentUrl(docsModal, doc.filename) : '#'}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="ml-3 shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-bold text-white hover:bg-brand-600 transition-colors"
                      >
                        <Eye size={12} /> View
                      </a>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
