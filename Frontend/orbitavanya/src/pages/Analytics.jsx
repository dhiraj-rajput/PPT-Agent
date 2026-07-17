import { useState, useEffect } from 'react';
import { ResponsiveContainer, AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell, Legend } from 'recharts';
import { DollarSign, FolderOpen, Building2, Target, Loader2, RefreshCw } from 'lucide-react';
import { PageHeader, Card } from '../components/ui/Common.jsx';
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

  const { stats, matchDistribution, emailPerformance, pipelineStages } = data;

  const revVal = stats.find(s => s.label === "Revenue Pipeline")?.value || '$0.00M';
  const tendersVal = stats.find(s => s.label === "Active Tenders")?.value || '0';
  const companiesVal = stats.find(s => s.label === "Total Companies")?.value || '0';
  const highMatchVal = stats.find(s => s.label === "High Match")?.value || '0';

  const kpis = [
    { label: 'Total Revenue Pipeline', value: revVal, icon: DollarSign, bg: 'bg-emerald-50', fg: 'text-emerald-600' },
    { label: 'Active Tenders Tracked', value: tendersVal, icon: FolderOpen, bg: 'bg-brand-50', fg: 'text-brand-600' },
    { label: 'Prospect Companies Registered', value: companiesVal, icon: Building2, bg: 'bg-amber-50', fg: 'text-amber-600' },
    { label: 'Qualified High Match score', value: highMatchVal, icon: Target, bg: 'bg-violet-50', fg: 'text-violet-600' },
  ];

  // Map pipeline stages for the conversion funnel
  const funnelData = pipelineStages?.map(p => ({
    stage: p.label,
    value: p.count
  })) || [];

  return (
    <div className="space-y-6">
      <PageHeader title="Database Analytics" subtitle="Real-time company metrics, outbound conversions, and match analytics" />

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
          <h3 className="text-sm font-bold text-navy-900 dark:text-white">Pipeline stage Conversion</h3>
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
    </div>
  );
}
