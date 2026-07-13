import { ResponsiveContainer, AreaChart, Area, LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import { DollarSign, TrendingUp, Target, Brain } from 'lucide-react';
import { PageHeader, Card } from '../components/ui/Common.jsx';
import { revenueTrend, aiAccuracy, conversionFunnel } from '../data/misc.js';

const kpis = [
  { label: 'Total Revenue Pipeline', value: '$2.45M', icon: DollarSign, bg: 'bg-emerald-50', fg: 'text-emerald-600' },
  { label: 'Win Rate', value: '31.2%', icon: TrendingUp, bg: 'bg-brand-50', fg: 'text-brand-600' },
  { label: 'Avg. Match Score', value: '84%', icon: Target, bg: 'bg-amber-50', fg: 'text-amber-600' },
  { label: 'AI Accuracy', value: '96%', icon: Brain, bg: 'bg-violet-50', fg: 'text-violet-600' },
];

export default function Analytics() {
  return (
    <div>
      <PageHeader title="Analytics" subtitle="Revenue, conversion, and AI performance insights" />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {kpis.map((k) => (
          <Card key={k.label}>
            <div className={`flex h-9 w-9 items-center justify-center rounded-xl ${k.bg} ${k.fg}`}>
              <k.icon size={17} />
            </div>
            <p className="mt-3 text-xs text-slate-500">{k.label}</p>
            <p className="text-xl font-extrabold text-navy-900">{k.value}</p>
          </Card>
        ))}
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card>
          <h3 className="text-sm font-bold text-navy-900">Revenue Trend</h3>
          <div className="mt-3 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={revenueTrend}>
                <defs>
                  <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#1c151e" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#1c151e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke="#F1F3F9" />
                <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#94A3B8' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: '#94A3B8' }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}M`} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 10, border: '1px solid #F1F3F9' }} formatter={(v) => [`$${v}M`, 'Revenue']} />
                <Area type="monotone" dataKey="revenue" stroke="#1c151e" strokeWidth={2.5} fill="url(#rev)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-bold text-navy-900">AI Match Accuracy</h3>
          <div className="mt-3 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={aiAccuracy}>
                <CartesianGrid vertical={false} stroke="#F1F3F9" />
                <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#94A3B8' }} axisLine={false} tickLine={false} />
                <YAxis domain={[80, 100]} tick={{ fontSize: 11, fill: '#94A3B8' }} axisLine={false} tickLine={false} tickFormatter={(v) => `${v}%`} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 10, border: '1px solid #F1F3F9' }} formatter={(v) => [`${v}%`, 'Accuracy']} />
                <Line type="monotone" dataKey="accuracy" stroke="#2f879d" strokeWidth={2.5} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="lg:col-span-2">
          <h3 className="text-sm font-bold text-navy-900">Conversion Funnel</h3>
          <div className="mt-3 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={conversionFunnel} layout="vertical" margin={{ left: 20 }}>
                <CartesianGrid horizontal={false} stroke="#F1F3F9" />
                <XAxis type="number" tick={{ fontSize: 11, fill: '#94A3B8' }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="stage" tick={{ fontSize: 12, fill: '#1c151e' }} axisLine={false} tickLine={false} width={100} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 10, border: '1px solid #F1F3F9' }} />
                <Bar dataKey="value" fill="#1c151e" radius={[0, 6, 6, 0]} barSize={22} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
    </div>
  );
}
