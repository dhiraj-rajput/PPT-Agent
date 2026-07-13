import { useState } from 'react';
import { Sparkles, Search, Building2, TrendingUp, ShieldCheck, Target } from 'lucide-react';
import { PageHeader, Card, MatchBadge } from '../components/ui/Common.jsx';
import { companies } from '../data/companies.js';

export default function AIResearch() {
  const [selected, setSelected] = useState(companies[0]);

  return (
    <div>
      <PageHeader title="AI Research" subtitle="AI-powered company research and opportunity analysis" />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5">
            <Search size={16} className="text-slate-400" />
            <input placeholder="Search a company to research..." className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400" />
          </div>
          <div className="mt-4 flex flex-col gap-2">
            {companies.map((c) => (
              <button
                key={c.id}
                onClick={() => setSelected(c)}
                className={`flex items-center justify-between rounded-xl border p-3 text-left transition-colors ${
                  selected.id === c.id ? 'border-brand-300 bg-brand-50/50' : 'border-slate-100 hover:border-slate-200'
                }`}
              >
                <div>
                  <p className="text-sm font-semibold text-navy-900">{c.name}</p>
                  <p className="text-xs text-slate-400">{c.industry}</p>
                </div>
                <MatchBadge score={c.matchScore} />
              </button>
            ))}
          </div>
        </Card>

        <div className="flex flex-col gap-5 lg:col-span-2">
          <Card>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles size={16} className="text-brand-500" />
                <h3 className="text-sm font-bold text-navy-900">AI Research Summary — {selected.name}</h3>
              </div>
              <button className="rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-bold text-white">Regenerate</button>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-slate-600">
              {selected.name} is a {selected.size} employee organization operating in the {selected.industry.toLowerCase()} sector
              out of {selected.location}, with estimated annual revenue of {selected.revenue}. Public procurement activity
              suggests consistent engagement with federal and state contracts, particularly in areas aligned with your
              service offerings. Sentiment across recent news mentions is neutral to positive, with no adverse risk flags
              detected in the last 12 months.
            </p>
          </Card>

          <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
            <Card>
              <TrendingUp size={18} className="text-emerald-600" />
              <p className="mt-2 text-xs text-slate-400">Growth Signal</p>
              <p className="text-lg font-extrabold text-navy-900">Strong</p>
            </Card>
            <Card>
              <ShieldCheck size={18} className="text-brand-600" />
              <p className="mt-2 text-xs text-slate-400">Risk Level</p>
              <p className="text-lg font-extrabold text-navy-900">Low</p>
            </Card>
            <Card>
              <Target size={18} className="text-amber-600" />
              <p className="mt-2 text-xs text-slate-400">Opportunity Fit</p>
              <p className="text-lg font-extrabold text-navy-900">{selected.matchScore}%</p>
            </Card>
          </div>

          <Card>
            <div className="flex items-center gap-2">
              <Building2 size={16} className="text-slate-400" />
              <h3 className="text-sm font-bold text-navy-900">Service Mapping</h3>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {selected.tags.map((t) => (
                <span key={t} className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600">{t}</span>
              ))}
              <span className="rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700">Recommended: Cloud Advisory</span>
              <span className="rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700">Recommended: AI Integration</span>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
