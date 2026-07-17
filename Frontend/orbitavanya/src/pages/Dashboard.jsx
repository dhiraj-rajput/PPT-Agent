import { Link } from 'react-router-dom';
import { useState, useEffect } from 'react';
import {
  Building2, FolderOpen, Target, Send, Users, DollarSign, Plus, ChevronDown,
  Calendar, Eye, FileText, MoreHorizontal, ArrowUp, Users2, Search, Heart, Handshake, Trophy, ExternalLink, Loader2
} from 'lucide-react';
import {
  ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts';
import { Card, ClosingAlertBadge } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';

const pipelineIcons = { Users: Users2, Search, FileText, Heart, Handshake, Trophy };
const pipelineColors = {
  sky: 'bg-sky-50 text-sky-600',
  brand: 'bg-brand-50 text-brand-600',
  violet: 'bg-violet-50 text-violet-600',
  amber: 'bg-amber-50 text-amber-600',
  teal: 'bg-teal-50 text-teal-600',
  emerald: 'bg-emerald-50 text-emerald-600',
};

const STAT_ICONS = {
  Building2: Building2,
  FolderOpen: FolderOpen,
  Target: Target,
  Send: Send,
  Users: Users,
  DollarSign: DollarSign
};

function daysUntilClosing(dateStr) {
  if (!dateStr) return 0;
  const closing = new Date(dateStr);
  const now = new Date();
  const diffTime = closing - now;
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
  return diffDays > 0 ? diffDays : 0;
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchDashboardData = () => {
    setLoading(true);
    setError('');
    api.getDashboardData()
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || 'Failed to load dashboard data.');
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  if (loading) {
    return (
      <div className="flex h-[70vh] flex-col items-center justify-center">
        <Loader2 className="animate-spin text-brand-500" size={36} />
        <p className="mt-4 text-sm text-slate-500 font-medium">Gathering real-time database intelligence...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-[50vh] flex-col items-center justify-center text-center p-4">
        <p className="text-sm font-semibold text-rose-600">{error}</p>
        <button 
          onClick={fetchDashboardData} 
          className="mt-4 rounded-xl bg-brand-500 px-4 py-2 text-xs font-bold text-white shadow-soft"
        >
          Retry
        </button>
      </div>
    );
  }

  const {
    stats,
    matchDistribution,
    tendersClosingSoon,
    emailPerformance,
    recentCompanies,
    recentlyMatchedTenders,
    pipelineStages
  } = data;

  const totalSent = emailPerformance?.reduce((acc, t) => acc + (t.sent || 0), 0) || 0;
  const totalOpened = emailPerformance?.reduce((acc, t) => acc + (t.opened || 0), 0) || 0;
  const totalClicked = emailPerformance?.reduce((acc, t) => acc + (t.clicked || 0), 0) || 0;
  const totalReplied = emailPerformance?.reduce((acc, t) => acc + (t.replied || 0), 0) || 0;

  const openPct = totalSent > 0 ? ((totalOpened / totalSent) * 100).toFixed(1) + '%' : '0%';
  const clickPct = totalSent > 0 ? ((totalClicked / totalSent) * 100).toFixed(1) + '%' : '0%';
  const replyPct = totalSent > 0 ? ((totalReplied / totalSent) * 100).toFixed(1) + '%' : '0%';

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold text-navy-900 dark:text-white">Good Morning! 👋</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Here's what's happening with your business today.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-white">
            <Calendar size={16} className="text-slate-400 dark:text-slate-500" />
            Live Database Sync
          </div>
          <Link to="/proposal-builder" className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft hover:bg-brand-600">
            <Plus size={16} /> New Proposal
          </Link>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
        {stats.map((s) => {
          const Icon = STAT_ICONS[s.icon] || Building2;
          return (
            <Card key={s.label} className="!p-4">
              <div className={`flex h-9 w-9 items-center justify-center rounded-xl ${s.bg} ${s.fg}`}>
                <Icon size={17} />
              </div>
              <p className="mt-3 text-xs font-medium text-slate-500 dark:text-slate-400">{s.label}</p>
              <p className="mt-0.5 text-xl font-extrabold text-navy-900 dark:text-white">{s.value}</p>
              <p className="mt-1 flex items-center gap-1 text-[11px] font-semibold text-emerald-600">
                <ArrowUp size={11} /> {s.change} <span className="font-normal text-slate-400 dark:text-slate-500">{s.period}</span>
              </p>
            </Card>
          );
        })}
      </div>

      {/* Middle row */}
      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-3">
        <Card>
          <h3 className="text-sm font-bold text-navy-900 dark:text-white">Match Score Distribution</h3>
          <div className="mt-2 flex items-center gap-4">
            <div className="h-40 w-40 shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={matchDistribution} dataKey="value" innerRadius={45} outerRadius={70} paddingAngle={2}>
                    {matchDistribution.map((entry) => (
                      <Cell key={entry.label} fill={entry.color} stroke="none" />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex flex-1 flex-col gap-2.5">
              {matchDistribution.map((d) => (
                <div key={d.label} className="flex items-center justify-between text-xs">
                  <span className="flex items-center gap-2 text-slate-500 dark:text-slate-400">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: d.color }} />
                    {d.label}
                  </span>
                  <span className="font-semibold text-navy-900 dark:text-white">{d.value}</span>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Tenders Closing Soon</h3>
            <Link to="/tenders" className="text-xs font-semibold text-brand-600 dark:text-brand-400">View All</Link>
          </div>
          <div className="mt-3 flex flex-col gap-3">
            {tendersClosingSoon.length === 0 ? (
              <div className="py-8 text-center text-xs text-slate-400 dark:text-slate-500">No tenders closing soon.</div>
            ) : (
              tendersClosingSoon.map((t) => {
                const daysLeft = daysUntilClosing(t.closingDate);
                return (
                  <div key={t.id} className="rounded-xl border border-slate-100 p-3 dark:border-navy-800">
                    <Link to={`/tenders/${t.id}`} className="block hover:border-brand-200">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-semibold leading-tight text-navy-900 dark:text-white">{t.title}</p>
                        <ClosingAlertBadge daysLeft={daysLeft} />
                      </div>
                      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">{t.agency}</p>
                      <p className="mt-1 text-xs font-medium text-slate-500 dark:text-slate-400">
                        {t.value} &nbsp;•&nbsp; {t.postedDate} → {t.closingDate}
                      </p>
                    </Link>
                    {t.rfpUrl && (
                      <a
                        href={t.rfpUrl}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:text-white dark:hover:bg-navy-800"
                      >
                        <ExternalLink size={11} /> View RFP
                      </a>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Email Performance</h3>
            <Link to="/email-campaign" className="text-xs font-semibold text-brand-600 dark:text-brand-400">View Report</Link>
          </div>
          <div className="mt-3 grid grid-cols-4 gap-2 text-center">
            {[
              ['Sent', totalSent.toLocaleString(), ''],
              ['Opened', totalOpened.toLocaleString(), openPct],
              ['Clicked', totalClicked.toLocaleString(), clickPct],
              ['Replied', totalReplied.toLocaleString(), replyPct]
            ].map(([label, val, pct]) => (
              <div key={label}>
                <p className="text-[11px] text-slate-400 dark:text-slate-500">{label}</p>
                <p className="text-base font-extrabold text-navy-900 dark:text-white">{val}</p>
                {pct && <p className="text-[10px] text-slate-400 dark:text-slate-500">{pct}</p>}
              </div>
            ))}
          </div>
          <div className="mt-3 h-32">
            {emailPerformance && emailPerformance.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={emailPerformance} margin={{ left: -20, top: 5 }}>
                  <CartesianGrid vertical={false} stroke="#F1F3F9" className="dark:stroke-navy-800" />
                  <XAxis dataKey="day" tick={{ fontSize: 9, fill: '#94A3B8' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 9, fill: '#94A3B8' }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 10, border: '1px solid #F1F3F9' }} />
                  <Line type="monotone" dataKey="sent" stroke="#1c151e" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="opened" stroke="#2f879d" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="clicked" stroke="#f7b708" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="replied" stroke="#e41b50" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-slate-400">No email trend data yet.</div>
            )}
          </div>
        </Card>
      </div>

      {/* Lower row: tables */}
      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card>
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Recent Companies</h3>
            <Link to="/companies" className="text-xs font-semibold text-brand-600 dark:text-brand-400">View All</Link>
          </div>
          <table className="mt-3 w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
                <th className="pb-2 font-semibold">Company</th>
                <th className="pb-2 font-semibold">Industry</th>
                <th className="pb-2 font-semibold">Match Score</th>
                <th className="pb-2 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {recentCompanies.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-xs text-slate-400 dark:text-slate-500">No companies registered in SAM database.</td>
                </tr>
              ) : (
                recentCompanies.map((c) => (
                  <tr key={c.id} className="border-t border-slate-50 dark:border-navy-800">
                    <td className="py-2.5 font-semibold text-navy-900 dark:text-white">
                      <Link to={`/companies/${c.uei || c.id}`} className="hover:text-brand-600 dark:hover:text-brand-400">{c.name}</Link>
                    </td>
                    <td className="py-2.5 text-slate-500 dark:text-slate-400">{c.industry}</td>
                    <td className="py-2.5">
                      <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-bold text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400">{c.matchScore}%</span>
                    </td>
                    <td className="py-2.5">
                      <div className="flex items-center justify-end gap-1 text-slate-400 dark:text-slate-500">
                        <Link to={`/companies/${c.uei || c.id}`} title="View Details" className="rounded-lg p-1.5 hover:bg-slate-100 dark:hover:bg-navy-800">
                          <Eye size={14} />
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Recently Matched Tenders</h3>
            <Link to="/tenders" className="text-xs font-semibold text-brand-600 dark:text-brand-400">View All</Link>
          </div>
          <table className="mt-3 w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
                <th className="pb-2 font-semibold">Tender</th>
                <th className="pb-2 font-semibold">Agency</th>
                <th className="pb-2 font-semibold">Match</th>
                <th className="pb-2 font-semibold text-right">Closing Date</th>
              </tr>
            </thead>
            <tbody>
              {recentlyMatchedTenders.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-xs text-slate-400 dark:text-slate-500">No matched tenders found.</td>
                </tr>
              ) : (
                recentlyMatchedTenders.map((t) => (
                  <tr key={t.id} className="border-t border-slate-50 dark:border-navy-800">
                    <td className="py-2.5 font-semibold text-navy-900 dark:text-white">
                      <Link to={`/tenders/${t.id}`} className="hover:text-brand-600 dark:hover:text-brand-400">{t.title}</Link>
                    </td>
                    <td className="py-2.5 text-slate-500 dark:text-slate-400">{t.agency}</td>
                    <td className="py-2.5">
                      <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-bold text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400">{t.match}%</span>
                    </td>
                    <td className="py-2.5 text-right text-slate-500 dark:text-slate-400">{t.closingDate}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </Card>
      </div>

      {/* Pipeline overview */}
      <Card className="mt-5">
        <h3 className="text-sm font-bold text-navy-900 dark:text-white">Pipeline Overview</h3>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {pipelineStages.map((s, i) => {
            const Icon = pipelineIcons[s.icon] || Search;
            return (
              <div key={s.key} className="flex items-center gap-2">
                <div className="flex items-center gap-3 rounded-xl border border-slate-100 px-4 py-3 dark:border-navy-800">
                  <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${pipelineColors[s.color]}`}>
                    <Icon size={16} />
                  </div>
                  <div>
                    <p className="text-xs text-slate-400 dark:text-slate-500">{s.label}</p>
                    <p className="text-base font-extrabold text-navy-900 dark:text-white">{s.count.toLocaleString()}</p>
                  </div>
                </div>
                {i < pipelineStages.length - 1 && <span className="text-slate-300 dark:text-slate-600">→</span>}
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
