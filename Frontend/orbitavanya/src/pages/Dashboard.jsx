import { Link } from 'react-router-dom';
import {
  Building2, FolderOpen, Target, Send, Users, DollarSign, Plus, ChevronDown,
  Calendar, Eye, FileText, MoreHorizontal, ArrowUp, Users2, Search, Heart, Handshake, Trophy, ExternalLink
} from 'lucide-react';
import {
  ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts';
import { Card, ClosingAlertBadge } from '../components/ui/Common.jsx';
import { companies } from '../data/companies.js';
import { tenders, daysUntilClosing } from '../data/tenders.js';
import { pipelineStages, emailPerformance, matchDistribution } from '../data/misc.js';

const stats = [
  { label: 'Total Companies', value: '18,245', change: '+12.5%', period: 'vs last 7 days', icon: Building2, bg: 'bg-sky-50', fg: 'text-sky-600' },
  { label: 'Active Tenders', value: '8,954', change: '+8.3%', period: 'vs last 7 days', icon: FolderOpen, bg: 'bg-emerald-50', fg: 'text-emerald-600' },
  { label: 'High Match', value: '623', change: '+15.7%', period: 'vs last 7 days', icon: Target, bg: 'bg-violet-50', fg: 'text-violet-600' },
  { label: 'Emails Sent', value: '2,340', change: '+10.2%', period: 'vs last 7 days', icon: Send, bg: 'bg-amber-50', fg: 'text-amber-600' },
  { label: 'Meetings', value: '126', change: '+7.8%', period: 'vs last 7 days', icon: Users, bg: 'bg-rose-50', fg: 'text-rose-600' },
  { label: 'Revenue Pipeline', value: '$2.45M', change: '+18.6%', period: 'vs last 7 days', icon: DollarSign, bg: 'bg-cyan-50', fg: 'text-cyan-600' },
];

const pipelineIcons = { Users: Users2, Search, FileText, Heart, Handshake, Trophy };
const pipelineColors = {
  sky: 'bg-sky-50 text-sky-600',
  brand: 'bg-brand-50 text-brand-600',
  violet: 'bg-violet-50 text-violet-600',
  amber: 'bg-amber-50 text-amber-600',
  teal: 'bg-teal-50 text-teal-600',
  emerald: 'bg-emerald-50 text-emerald-600',
};

export default function Dashboard() {
  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold text-navy-900 dark:text-white">Good Morning, John! 👋</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Here's what's happening with your business today.</p>
        </div>
        <div className="flex items-center gap-3">
          <button className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700">
            <Calendar size={16} className="text-slate-400 dark:text-slate-500" />
            May 20 – May 27, 2026
          </button>
          <button className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft hover:bg-brand-600">
            <Plus size={16} /> New Proposal <ChevronDown size={14} />
          </button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
        {stats.map((s) => (
          <Card key={s.label} className="!p-4">
            <div className={`flex h-9 w-9 items-center justify-center rounded-xl ${s.bg} ${s.fg}`}>
              <s.icon size={17} />
            </div>
            <p className="mt-3 text-xs font-medium text-slate-500 dark:text-slate-400">{s.label}</p>
            <p className="mt-0.5 text-xl font-extrabold text-navy-900 dark:text-white">{s.value}</p>
            <p className="mt-1 flex items-center gap-1 text-[11px] font-semibold text-emerald-600">
              <ArrowUp size={11} /> {s.change} <span className="font-normal text-slate-400 dark:text-slate-500">{s.period}</span>
            </p>
          </Card>
        ))}
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
            {tenders.slice(0, 3).map((t) => {
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
                  <a
                    href={t.rfpUrl}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:text-white dark:hover:bg-navy-800"
                  >
                    <ExternalLink size={11} /> View RFP
                  </a>
                </div>
              );
            })}
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Email Performance</h3>
            <Link to="/email-campaign" className="text-xs font-semibold text-brand-600 dark:text-brand-400">View Report</Link>
          </div>
          <div className="mt-3 grid grid-cols-4 gap-2 text-center">
            {[['Sent', '2,340', ''], ['Opened', '1,234', '52.7%'], ['Clicked', '456', '19.5%'], ['Replied', '142', '6.1%']].map(([label, val, pct]) => (
              <div key={label}>
                <p className="text-[11px] text-slate-400 dark:text-slate-500">{label}</p>
                <p className="text-base font-extrabold text-navy-900 dark:text-white">{val}</p>
                {pct && <p className="text-[10px] text-slate-400 dark:text-slate-500">{pct}</p>}
              </div>
            ))}
          </div>
          <div className="mt-3 h-32">
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
              {companies.slice(0, 5).map((c) => (
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
                      <button className="rounded-lg p-1.5 hover:bg-slate-100 dark:hover:bg-navy-800"><Eye size={14} /></button>
                      <button className="rounded-lg p-1.5 hover:bg-slate-100 dark:hover:bg-navy-800"><FileText size={14} /></button>
                      <button className="rounded-lg p-1.5 hover:bg-slate-100 dark:hover:bg-navy-800"><MoreHorizontal size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
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
              {tenders.slice(0, 5).map((t) => (
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
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      {/* Pipeline overview */}
      <Card className="mt-5">
        <h3 className="text-sm font-bold text-navy-900 dark:text-white">Pipeline Overview</h3>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {pipelineStages.map((s, i) => {
            const Icon = pipelineIcons[s.icon];
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
