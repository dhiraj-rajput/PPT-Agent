import { Plus, Send, MousePointerClick, MailOpen, Reply, Clock, Globe } from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';
import { PageHeader, Card, StatusBadge } from '../components/ui/Common.jsx';
import { campaigns, emailPerformance, websiteEngagement } from '../data/misc.js';

const summary = [
  { label: 'Total Sent', value: '4,200', icon: Send, bg: 'bg-sky-50', fg: 'text-sky-600' },
  { label: 'Open Rate', value: '58.2%', icon: MailOpen, bg: 'bg-emerald-50', fg: 'text-emerald-600' },
  { label: 'Click Rate', value: '24.1%', icon: MousePointerClick, bg: 'bg-amber-50', fg: 'text-amber-600' },
  { label: 'Reply Rate', value: '8.4%', icon: Reply, bg: 'bg-rose-50', fg: 'text-rose-600' },
];

export default function EmailCampaign() {
  return (
    <div>
      <PageHeader
        title="Email Campaign"
        subtitle="Create, schedule, and track outbound email campaigns"
        action={
          <button className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft">
            <Plus size={16} /> New Campaign
          </button>
        }
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {summary.map((s) => (
          <Card key={s.label}>
            <div className={`flex h-9 w-9 items-center justify-center rounded-xl ${s.bg} ${s.fg}`}>
              <s.icon size={17} />
            </div>
            <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">{s.label}</p>
            <p className="text-xl font-extrabold text-navy-900 dark:text-white">{s.value}</p>
          </Card>
        ))}
      </div>

      <Card className="mt-5">
        <h3 className="text-sm font-bold text-navy-900 dark:text-white">Performance Trend</h3>
        <div className="mt-3 h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={emailPerformance}>
              <CartesianGrid vertical={false} stroke="#F1F3F9" />
              <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#94A3B8' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#94A3B8' }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 10, border: '1px solid #F1F3F9' }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="sent" name="Sent" stroke="#1c151e" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="opened" name="Opened" stroke="#2f879d" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="clicked" name="Clicked" stroke="#f7b708" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="replied" name="Replied" stroke="#e41b50" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card className="mt-5 !p-0">
        <div className="flex items-center justify-between p-5 pb-0">
          <h3 className="text-sm font-bold text-navy-900 dark:text-white">Campaigns</h3>
        </div>
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 dark:border-navy-800 text-left text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
              <th className="px-5 py-3 font-semibold">Campaign</th>
              <th className="px-5 py-3 font-semibold">Status</th>
              <th className="px-5 py-3 font-semibold">Sent</th>
              <th className="px-5 py-3 font-semibold">Opened</th>
              <th className="px-5 py-3 font-semibold">Clicked</th>
              <th className="px-5 py-3 font-semibold">Replied</th>
              <th className="px-5 py-3 font-semibold text-right">Created</th>
            </tr>
          </thead>
          <tbody>
            {campaigns.map((c) => (
              <tr key={c.id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60 dark:border-navy-800/40 dark:hover:bg-navy-800/40">
                <td className="px-5 py-3.5 font-semibold text-navy-900 dark:text-white">{c.name}</td>
                <td className="px-5 py-3.5"><StatusBadge status={c.status} /></td>
                <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{c.sent.toLocaleString()}</td>
                <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{c.opened.toLocaleString()}</td>
                <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{c.clicked.toLocaleString()}</td>
                <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{c.replied.toLocaleString()}</td>
                <td className="px-5 py-3.5 text-right text-slate-500 dark:text-slate-400">{c.created}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card className="mt-5 !p-0">
        <div className="flex items-center justify-between p-5 pb-0">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-bold text-navy-900 dark:text-white">
              <Globe size={15} className="text-brand-500" /> Website Engagement Tracking
            </h3>
            <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">Which companies clicked through and how long they spent on the site</p>
          </div>
        </div>
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 dark:border-navy-800 text-left text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
              <th className="px-5 py-3 font-semibold">Company</th>
              <th className="px-5 py-3 font-semibold">Campaign</th>
              <th className="px-5 py-3 font-semibold">Time Active</th>
              <th className="px-5 py-3 font-semibold">Pages Viewed</th>
              <th className="px-5 py-3 font-semibold text-right">Last Visit</th>
            </tr>
          </thead>
          <tbody>
            {websiteEngagement.map((w) => (
              <tr key={w.id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60 dark:border-navy-800/40 dark:hover:bg-navy-800/40">
                <td className="px-5 py-3.5 font-semibold text-navy-900 dark:text-white">{w.company}</td>
                <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{w.campaign}</td>
                <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">
                  <span className="flex items-center gap-1.5"><Clock size={12} /> {w.timeActive}</span>
                </td>
                <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">
                  <span className="font-semibold text-navy-900 dark:text-white">{w.pagesViewed}</span>
                  <span className="ml-1 text-xs text-slate-400 dark:text-slate-500">({w.pages.join(', ')})</span>
                </td>
                <td className="px-5 py-3.5 text-right text-slate-500 dark:text-slate-400">{w.lastVisit}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
