import { useState, useEffect } from 'react';
import { ResponsiveContainer, AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell, Legend } from 'recharts';
import { FolderOpen, Building2, Target, Users2, Loader2, RefreshCw, Clock, Star, TrendingUp } from 'lucide-react';
import { PageHeader, Card, StatusBadge } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';

export default function Analytics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchAnalytics = () => {
    setLoading(true);
    setError('');
    api.getDashboardData()
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Error fetching analytics:', err);
        setError('Failed to load database analytics.');
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchAnalytics();
  }, []);

  if (loading) {
    return (
      <div className="flex h-[70vh] flex-col items-center justify-center">
        <Loader2 className="animate-spin text-brand-500" size={36} />
        <p className="mt-4 text-sm text-slate-500 font-medium">Gathering database analytics...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-[50vh] flex-col items-center justify-center text-center p-4">
        <p className="text-sm font-semibold text-rose-600">{error}</p>
        <button 
          onClick={fetchAnalytics} 
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
    emailPerformance,
    pipelineStages,
    tendersClosingSoon = [],
    recentCompanies = [],
    recentlyMatchedTenders = [],
  } = data;

  const tendersVal = stats.find(s => s.label === "Active Tenders")?.value || '0';
  const companiesVal = stats.find(s => s.label === "Total Companies")?.value || '0';
  const highMatchVal = stats.find(s => s.label === "High Match")?.value || '0';
  const contactedVal = stats.find(s => s.label === "Companies Contacted")?.value
    || stats.find(s => s.label === "Emails Sent")?.value
    || '0';

  const kpis = [
    { label: 'Active Tenders Tracked', value: tendersVal, icon: FolderOpen, bg: 'bg-brand-50', fg: 'text-brand-600' },
    { label: 'Prospect Companies Registered', value: companiesVal, icon: Building2, bg: 'bg-amber-50', fg: 'text-amber-600' },
    { label: 'Qualified High Match Score', value: highMatchVal, icon: Target, bg: 'bg-violet-50', fg: 'text-violet-600' },
    { label: 'Companies Contacted', value: contactedVal, icon: Users2, bg: 'bg-cyan-50', fg: 'text-cyan-600' },
  ];

  // Map pipeline stages for the conversion funnel
  const funnelData = pipelineStages?.map(p => ({
    stage: p.label,
    value: p.count
  })) || [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Database Analytics"
        subtitle="Real-time company metrics, outbound conversions, and match analytics"
        action={
          <button
            onClick={fetchAnalytics}
            disabled={loading}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 hover:bg-slate-50 hover:text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-400 dark:hover:bg-navy-700"
            title="Refresh data"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        }
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {kpis.map((k) => (
          <Card key={k.label}>
            <div className={`flex h-9 w-9 items-center justify-center rounded-xl ${k.bg} ${k.fg}`}>
              <k.icon size={17} />
            </div>
            <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">{k.label}</p>
            <p className="text-xl font-extrabold text-navy-900 dark:text-white">{k.value}</p>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* Email Outreach Performance trend over the week */}
        <Card>
          <h3 className="text-sm font-bold text-navy-900 dark:text-white">Outbound Campaign Trends</h3>
          <div className="mt-3 h-64">
            {emailPerformance && emailPerformance.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={emailPerformance}>
                  <defs>
                    <linearGradient id="emailSent" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#1c151e" stopOpacity={0.25} />
                      <stop offset="100%" stopColor="#1c151e" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid vertical={false} stroke="#F1F3F9" />
                  <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#94A3B8' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: '#94A3B8' }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 10, border: '1px solid #F1F3F9' }} />
                  <Area type="monotone" dataKey="sent" stroke="#1c151e" strokeWidth={2} fill="url(#emailSent)" name="Sent" />
                  <Area type="monotone" dataKey="opened" stroke="#2f879d" strokeWidth={2} fill="none" name="Opened" />
                  <Area type="monotone" dataKey="clicked" stroke="#f7b708" strokeWidth={2} fill="none" name="Clicked" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-slate-400">No email outreach data recorded.</div>
            )}
          </div>
        </Card>

        {/* Match Scoring Distribution */}
        <Card>
          <h3 className="text-sm font-bold text-navy-900 dark:text-white">AI Target Match Scoring</h3>
          <div className="mt-3 flex h-64 items-center justify-center gap-4">
            <div className="h-48 w-48">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={matchDistribution} dataKey="value" innerRadius={50} outerRadius={75} paddingAngle={3}>
                    {matchDistribution.map((entry) => (
                      <Cell key={entry.label} fill={entry.color} stroke="none" />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => [`${value} Companies`, 'Count']} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex flex-col gap-3">
              {matchDistribution.map((d) => (
                <div key={d.label} className="flex items-center gap-2 text-xs">
                  <span className="h-3 w-3 rounded-full" style={{ backgroundColor: d.color }} />
                  <span className="font-bold text-navy-900 dark:text-white">{d.value}</span>
                  <span className="text-slate-500 dark:text-slate-400">{d.label}</span>
                </div>
              ))}
            </div>
          </div>
        </Card>

        {/* Pipeline Stage Funnel */}
        <Card className="lg:col-span-2">
          <h3 className="text-sm font-bold text-navy-900 dark:text-white">Pipeline Stage Conversion</h3>
          <div className="mt-3 h-64">
            {funnelData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={funnelData} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid horizontal={false} stroke="#F1F3F9" />
                  <XAxis type="number" tick={{ fontSize: 11, fill: '#94A3B8' }} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="stage" tick={{ fontSize: 12, fill: '#1c151e' }} axisLine={false} tickLine={false} width={130} />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 10, border: '1px solid #F1F3F9' }} />
                  <Bar dataKey="value" fill="#2f879d" radius={[0, 6, 6, 0]} barSize={20} name="Count" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-slate-400">No stage metrics recorded.</div>
            )}
          </div>
        </Card>
      </div>

      {/* Data-centric detail tables */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {/* Tenders closing soon */}
        <Card className="!p-0">
          <div className="flex items-center gap-2 p-5 pb-3">
            <Clock size={15} className="text-amber-500" />
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Tenders Closing Soon</h3>
          </div>
          <div className="divide-y divide-slate-50 dark:divide-navy-800/40">
            {tendersClosingSoon.length === 0 && (
              <p className="px-5 pb-5 text-xs text-slate-400">No tenders closing soon.</p>
            )}
            {tendersClosingSoon.map((t) => (
              <div key={t.id} className="px-5 py-3">
                <p className="text-xs font-semibold text-navy-900 dark:text-white line-clamp-1">{t.title || 'Untitled tender'}</p>
                <p className="mt-0.5 text-[11px] text-slate-400">{t.agency}</p>
                <div className="mt-1.5 flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
                  <span>{t.value}</span>
                  <span>Closes {t.closingDate || '—'}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Recently added companies */}
        <Card className="!p-0">
          <div className="flex items-center gap-2 p-5 pb-3">
            <Building2 size={15} className="text-sky-500" />
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Recently Added Companies</h3>
          </div>
          <div className="divide-y divide-slate-50 dark:divide-navy-800/40">
            {recentCompanies.length === 0 && (
              <p className="px-5 pb-5 text-xs text-slate-400">No companies recorded yet.</p>
            )}
            {recentCompanies.map((c) => (
              <div key={c.id} className="flex items-center justify-between px-5 py-3">
                <div>
                  <p className="text-xs font-semibold text-navy-900 dark:text-white">{c.name || 'Unnamed company'}</p>
                  <p className="mt-0.5 text-[11px] text-slate-400">{c.industry}</p>
                </div>
                <span className="rounded-full bg-violet-50 px-2 py-1 text-[10px] font-bold text-violet-600 dark:bg-violet-950/30 dark:text-violet-400">
                  {c.matchScore || 0}% match
                </span>
              </div>
            ))}
          </div>
        </Card>

        {/* Recently matched tenders */}
        <Card className="!p-0">
          <div className="flex items-center gap-2 p-5 pb-3">
            <Star size={15} className="text-emerald-500" />
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Top Matched Tenders</h3>
          </div>
          <div className="divide-y divide-slate-50 dark:divide-navy-800/40">
            {recentlyMatchedTenders.length === 0 && (
              <p className="px-5 pb-5 text-xs text-slate-400">No matched tenders yet.</p>
            )}
            {recentlyMatchedTenders.map((t) => (
              <div key={t.id} className="px-5 py-3">
                <p className="text-xs font-semibold text-navy-900 dark:text-white line-clamp-1">{t.title || 'Untitled tender'}</p>
                <p className="mt-0.5 text-[11px] text-slate-400">{t.agency}</p>
                <div className="mt-1.5 flex items-center justify-between text-[11px]">
                  <span className="inline-flex items-center gap-1 font-semibold text-emerald-600 dark:text-emerald-400">
                    <TrendingUp size={11} /> {t.match || 0}% match
                  </span>
                  <span className="text-slate-500 dark:text-slate-400">Closes {t.closingDate || '—'}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
