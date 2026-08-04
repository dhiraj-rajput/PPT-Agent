import { Link } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { useNotifications } from '../context/NotificationContext.jsx';
import {
  Building2, FolderOpen, Target, Send, Users, DollarSign, Plus, ChevronDown,
  Calendar, Eye, FileText, MoreHorizontal, ArrowUp, Users2, Search, Heart, Handshake, Trophy, ExternalLink, Loader2, RefreshCw
} from 'lucide-react';
import { Card, ClosingAlertBadge } from '../components/ui/Common.jsx';
import DataSourceSelect from '../components/ui/DataSourceSelect.jsx';
import { api } from '../lib/api.jsx';

const pipelineIcons = { Users: Users2, Search, FileText, Heart, Handshake, Trophy };
const pipelineColors = {
  sky: 'bg-sky-50 text-sky-600 dark:bg-sky-500/10 dark:text-sky-400',
  brand: 'bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400',
  violet: 'bg-violet-50 text-violet-600 dark:bg-violet-500/10 dark:text-violet-400',
  amber: 'bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400',
  teal: 'bg-teal-50 text-teal-600 dark:bg-teal-500/10 dark:text-teal-400',
  emerald: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400',
};

function daysUntilClosing(dateStr) {
  if (!dateStr) return 0;
  const toMidnight = (d) => { const n = new Date(d); n.setHours(0,0,0,0); return n; };
  const diffMs = toMidnight(dateStr) - toMidnight(new Date());
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  return diffDays > 0 ? diffDays : 0;
}

function getDynamicGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return { text: 'Good Morning!', icon: '☀️' };
  if (hour < 17) return { text: 'Good Afternoon!', icon: '🌤️' };
  return { text: 'Good Evening!', icon: '🌙' };
}

export default function Dashboard() {
  const greeting = getDynamicGreeting();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [syncing, setSyncing] = useState(false);
  const [sourceFilter, setSourceFilter] = useState('All');
  const [lastSynced, setLastSynced] = useState(null);
  const { createAlert } = useNotifications();

  const fetchDashboardData = (source = sourceFilter) => {
    setLoading(true);
    setError('');
    const params = source && source !== 'All' ? { source } : {};
    api.getDashboardData(params)
      .then((res) => {
        setData(res);
        setLoading(false);
        setLastSynced(new Date());
      })
      .catch((err) => {
        setError(err.message || 'Failed to load dashboard data.');
        setLoading(false);
      });
  };

  const [syncDropdownOpen, setSyncDropdownOpen] = useState(false);

  const handleSyncSource = async (targetSource = 'all') => {
    if (syncing) return;
    setSyncing(true);
    setSyncDropdownOpen(false);
    setError('');

    try {
      if (targetSource === 'sam_gov') {
        await api.syncTendersFromSource('sam_gov');
        createAlert('SAM.gov Synced', 'Successfully synced US Federal Tenders from SAM.gov!', '/dashboard');
      } else if (targetSource === 'companies_house_uk') {
        await api.syncTendersFromSource('companies_house_uk');
        createAlert('Companies House Synced', 'Successfully synced UK Tenders from Companies House!', '/dashboard');
      } else {
        await Promise.all([
          api.syncTendersFromSource('sam_gov'),
          api.syncTendersFromSource('companies_house_uk'),
          api.getReports(),
          api.getAllDraftRequests(),
          api.getCompanies(),
          api.getCRMPipeline(),
        ]);
        createAlert('Data Synced', 'Data synced successfully across SAM.gov, Companies House, Tenders, Reports, and CRM!', '/dashboard');
      }

      await fetchDashboardData(sourceFilter);
      setLastSynced(new Date());
    } catch (err) {
      setError(err.message || 'Failed to sync data.');
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    fetchDashboardData(sourceFilter);
  }, [sourceFilter]);

  if (loading) {
    return (
      <div className="flex h-[70vh] flex-col items-center justify-center">
        <Loader2 className="animate-spin text-brand-500" size={36} />
        <p className="mt-4 text-sm text-slate-500 font-medium">Gathering real-time database intelligence...</p>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="flex h-[50vh] flex-col items-center justify-center text-center p-4">
        <p className="text-sm font-semibold text-rose-600">{error}</p>
        <button 
          onClick={() => fetchDashboardData(sourceFilter)} 
          className="mt-4 rounded-xl bg-brand-500 px-4 py-2 text-xs font-bold text-white shadow-soft"
        >
          Retry
        </button>
      </div>
    );
  }

  const {
    tendersClosingSoon,
    recentCompanies,
    recentlyMatchedTenders,
    pipelineStages
  } = data;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-navy-900 dark:text-white sm:text-3xl">
            {greeting.text} {greeting.icon}
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Real-time business intelligence, tenders, and multi-source analytics.
          </p>
        </div>

        {/* Compact, tightly-grouped control bar */}
        <div className="flex flex-wrap items-center gap-2 sm:gap-2.5">
          {/* Grouped Source Filter & Sync Actions */}
          <div className="inline-flex items-center gap-1.5 p-1 bg-slate-100/90 dark:bg-navy-800/90 rounded-2xl border border-slate-200/80 dark:border-navy-700/80 shadow-xs">
            <DataSourceSelect value={sourceFilter} onChange={setSourceFilter} includeAll={true} className="!border-0 !bg-transparent !p-0" />

            <div className="h-4 w-px bg-slate-200 dark:bg-navy-700 mx-0.5" />

            <div className="relative">
              <button
                type="button"
                onClick={() => setSyncDropdownOpen(!syncDropdownOpen)}
                disabled={syncing}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-xl bg-white dark:bg-navy-900 text-navy-900 dark:text-white shadow-sm border border-slate-200/80 dark:border-navy-700 hover:bg-slate-50 dark:hover:bg-navy-850 disabled:opacity-60 transition-all"
              >
                <RefreshCw size={13} className={syncing ? 'animate-spin text-brand-500' : 'text-brand-500'} />
                <span>{syncing ? 'Syncing…' : 'Sync Data'}</span>
                <ChevronDown size={12} className={`transition-transform text-slate-400 ${syncDropdownOpen ? 'rotate-180' : ''}`} />
              </button>

              {syncDropdownOpen && (
                <div className="absolute right-0 mt-2 w-56 rounded-2xl border border-slate-100 dark:border-navy-700 bg-white dark:bg-navy-900 shadow-2xl z-30 overflow-hidden py-1 border-t-2 border-t-brand-500">
                  <button
                    type="button"
                    onClick={() => handleSyncSource('all')}
                    className="w-full text-left px-3.5 py-2 text-xs font-semibold text-navy-900 dark:text-white hover:bg-slate-50 dark:hover:bg-navy-800 flex items-center justify-between transition-colors"
                  >
                    <span>Sync All Sources</span>
                    <span className="text-[10px] font-bold text-indigo-500 bg-indigo-50 dark:bg-indigo-950/40 px-1.5 py-0.5 rounded">SAM + CH</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSyncSource('sam_gov')}
                    className="w-full text-left px-3.5 py-2 text-xs font-semibold text-blue-600 dark:text-blue-400 hover:bg-slate-50 dark:hover:bg-navy-800 flex items-center justify-between transition-colors"
                  >
                    <span>Sync SAM.gov (US)</span>
                    <span className="text-[10px] font-bold text-blue-500 bg-blue-50 dark:bg-blue-950/40 px-1.5 py-0.5 rounded">Federal</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSyncSource('companies_house_uk')}
                    className="w-full text-left px-3.5 py-2 text-xs font-semibold text-emerald-600 dark:text-emerald-400 hover:bg-slate-50 dark:hover:bg-navy-800 flex items-center justify-between transition-colors"
                  >
                    <span>Sync Companies House (UK)</span>
                    <span className="text-[10px] font-bold text-emerald-500 bg-emerald-50 dark:bg-emerald-950/40 px-1.5 py-0.5 rounded">UK FTS</span>
                  </button>
                </div>
              )}
            </div>
          </div>

          <Link
            to="/proposal-builder"
            className="flex items-center gap-1.5 rounded-2xl bg-brand-500 hover:bg-brand-600 px-4 py-2 text-xs font-bold text-white shadow-soft transition-all shrink-0"
          >
            <Plus size={15} />
            <span>New Proposal</span>
          </Link>
        </div>
      </div>

      {error && data && (
        <div className="rounded-xl bg-tomato-50 dark:bg-tomato-500/10 px-3.5 py-2.5 text-sm text-tomato-700 dark:text-tomato-400">
          {error}
        </div>
      )}

      {/* Middle row (Urgent Tenders & Actions) */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {/* Tenders Closing Soon Card */}
        <Card className="lg:col-span-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Tenders Closing Soon</h3>
            <Link to="/tenders" className="text-xs font-semibold text-brand-600 dark:text-brand-400">View All</Link>
          </div>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
            {tendersClosingSoon.length === 0 ? (
              <div className="col-span-2 py-8 text-center text-xs text-slate-400 dark:text-slate-500">No active tenders closing soon.</div>
            ) : (
              tendersClosingSoon.slice(0, 2).map((t) => {
                const daysLeft = daysUntilClosing(t.closingDate);
                return (
                  <div key={t.id} className="rounded-xl border border-slate-100 p-3.5 dark:border-navy-800 flex flex-col justify-between h-full bg-slate-50/20">
                    <Link to={`/tenders/${t.id}`} className="block hover:opacity-90 space-y-1">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-xs font-bold leading-tight text-navy-900 dark:text-white line-clamp-2">{t.title}</p>
                        <ClosingAlertBadge daysLeft={daysLeft} />
                      </div>
                      <p className="text-[10px] text-slate-400 dark:text-slate-500 truncate">{t.agency}</p>
                      <p className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 mt-1">
                        {t.value} &nbsp;•&nbsp; {t.closingDate}
                      </p>
                    </Link>
                    {t.rfpUrl && (
                      <a
                        href={t.rfpUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-2.5 py-1 text-[10px] font-bold text-navy-900 dark:text-white hover:bg-slate-50 self-start"
                      >
                        <ExternalLink size={10} /> View RFP Link
                      </a>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </Card>

        {/* Quick Shortcuts Actions Card */}
        <Card className="lg:col-span-1">
          <h3 className="text-sm font-bold text-navy-900 dark:text-white">Quick Shortcuts</h3>
          <div className="mt-3.5 flex flex-col gap-3">
            <Link to="/proposal-builder" className="flex items-center gap-3 rounded-xl border border-slate-100 p-3 hover:border-brand-200 hover:bg-slate-50/50 transition-all dark:border-navy-800 dark:hover:bg-navy-950">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400">
                <FileText size={15} />
              </span>
              <div className="text-left">
                <p className="text-xs font-bold text-navy-900 dark:text-white">Generate Proposal</p>
                <p className="text-[9px] text-slate-400">Auto-build prime or subcontract drafts</p>
              </div>
            </Link>
            <Link to="/rfp-auto-respond" className="flex items-center gap-3 rounded-xl border border-slate-100 p-3 hover:border-brand-200 hover:bg-slate-50/50 transition-all dark:border-navy-800 dark:hover:bg-navy-950">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400">
                <RefreshCw size={15} />
              </span>
              <div className="text-left">
                <p className="text-xs font-bold text-navy-900 dark:text-white">RFP Auto-Responder</p>
                <p className="text-[9px] text-slate-400">Match active tenders to capability matrix</p>
              </div>
            </Link>
            <Link to="/meetings" className="flex items-center gap-3 rounded-xl border border-slate-100 p-3 hover:border-brand-200 hover:bg-slate-50/50 transition-all dark:border-navy-800 dark:hover:bg-navy-950">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400">
                <Calendar size={15} />
              </span>
              <div className="text-left">
                <p className="text-xs font-bold text-navy-900 dark:text-white">Book Client Meeting</p>
                <p className="text-[9px] text-slate-400">Schedule Google Meet video rooms</p>
              </div>
            </Link>
          </div>
        </Card>
      </div>

      {/* Tables row */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* Recent Companies */}
        <Card>
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Recent Companies</h3>
            <Link to="/companies" className="text-xs font-semibold text-brand-600 dark:text-brand-400">View All</Link>
          </div>
          <div className="overflow-x-auto mt-3">
            <table className="w-full text-sm min-w-[500px]">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500 border-b border-slate-100 dark:border-navy-800 pb-2">
                  <th className="pb-2 font-bold w-[45%]">Company</th>
                  <th className="pb-2 font-bold w-[35%]">Industry</th>
                  <th className="pb-2 font-bold w-[20%] text-right">Match Score</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50 dark:divide-navy-850">
                {recentCompanies.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="py-6 text-center text-xs text-slate-400 dark:text-slate-500">No registered companies found in DB.</td>
                  </tr>
                ) : (
                  recentCompanies.slice(0, 5).map((c) => (
                    <tr key={c.id} className="hover:bg-slate-50/50 dark:hover:bg-navy-950/25">
                      <td className="py-2.5 pr-2 font-semibold text-navy-900 dark:text-white truncate max-w-[200px]">
                        <Link to={`/companies/${c.uei || c.id}`} className="hover:text-brand-600 dark:hover:text-brand-400">{c.name}</Link>
                      </td>
                      <td className="py-2.5 pr-2 text-slate-500 dark:text-slate-400 truncate max-w-[150px]">{c.industry}</td>
                      <td className="py-2.5 text-right font-bold text-emerald-600 dark:text-emerald-400">
                        {c.matchScore}%
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Recently Matched Tenders */}
        <Card>
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Recently Matched Tenders</h3>
            <Link to="/tenders" className="text-xs font-semibold text-brand-600 dark:text-brand-400">View All</Link>
          </div>
          <div className="overflow-x-auto mt-3">
            <table className="w-full text-sm min-w-[500px]">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500 border-b border-slate-100 dark:border-navy-800 pb-2">
                  <th className="pb-2 font-bold w-[45%]">Tender</th>
                  <th className="pb-2 font-bold w-[35%]">Agency</th>
                  <th className="pb-2 font-bold w-[20%] text-right">Closing Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50 dark:divide-navy-850">
                {recentlyMatchedTenders.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="py-6 text-center text-xs text-slate-400 dark:text-slate-500">No matched tenders found.</td>
                  </tr>
                ) : (
                  recentlyMatchedTenders.slice(0, 5).map((t) => (
                    <tr key={t.id} className="hover:bg-slate-50/50 dark:hover:bg-navy-950/25">
                      <td className="py-2.5 pr-2 font-semibold text-navy-900 dark:text-white truncate max-w-[200px]">
                        <Link to={`/tenders/${t.id}`} className="hover:text-brand-600 dark:hover:text-brand-400">{t.title}</Link>
                      </td>
                      <td className="py-2.5 pr-2 text-slate-500 dark:text-slate-400 truncate max-w-[150px]">{t.agency}</td>
                      <td className="py-2.5 text-right text-slate-500 dark:text-slate-400 whitespace-nowrap">{t.closingDate}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {/* Pipeline overview */}
      <Card>
        <h3 className="text-sm font-bold text-navy-900 dark:text-white">Pipeline Overview</h3>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          {pipelineStages.map((s, i) => {
            const Icon = pipelineIcons[s.icon] || Search;
            return (
              <div key={s.key} className="flex items-center gap-3">
                <div className="flex items-center gap-3 rounded-xl border border-slate-100 px-4 py-3 dark:border-navy-800 bg-slate-50/30">
                  <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${pipelineColors[s.color]}`}>
                    <Icon size={16} />
                  </div>
                  <div>
                    <p className="text-xs text-slate-400 dark:text-slate-500">{s.label}</p>
                    <p className="text-base font-extrabold text-navy-900 dark:text-white">{s.count.toLocaleString()}</p>
                  </div>
                </div>
                {i < pipelineStages.length - 1 && <span className="text-slate-300 dark:text-slate-600 font-bold">→</span>}
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
