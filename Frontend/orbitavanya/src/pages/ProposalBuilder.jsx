import { useState } from 'react';
import { Plus, Sparkles, FileDown, LayoutTemplate, Eye, MoreHorizontal } from 'lucide-react';
import { PageHeader, Card, StatusBadge } from '../components/ui/Common.jsx';
import { proposals } from '../data/misc.js';

const templates = ['Federal RFP Response', 'State & Local Bid', 'Healthcare IT Proposal', 'Defense Contract Response'];

export default function ProposalBuilder() {
  const [tab, setTab] = useState('all');

  return (
    <div>
      <PageHeader
        title="Proposal Builder"
        subtitle="Generate, edit, and export tender-winning proposals with AI"
        action={
          <button className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft">
            <Plus size={16} /> New Proposal
          </button>
        }
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <div className="flex items-center gap-2">
            <LayoutTemplate size={16} className="text-slate-400" />
            <h3 className="text-sm font-bold text-navy-900">Template Library</h3>
          </div>
          <div className="mt-3 flex flex-col gap-2">
            {templates.map((t) => (
              <button key={t} className="flex items-center justify-between rounded-xl border border-slate-100 p-3 text-left text-sm font-medium text-navy-900 hover:border-brand-200">
                {t}
                <Plus size={14} className="text-slate-400" />
              </button>
            ))}
          </div>

          <div className="mt-5 rounded-xl bg-brand-50 p-4">
            <div className="flex items-center gap-2">
              <Sparkles size={15} className="text-brand-600" />
              <p className="text-sm font-bold text-brand-700">AI Writer</p>
            </div>
            <p className="mt-2 text-xs text-brand-700/80">
              Describe the tender and let AI draft your executive summary, technical approach, and pricing narrative in minutes.
            </p>
            <button className="mt-3 w-full rounded-lg bg-brand-500 py-2 text-xs font-bold text-white">Start with AI</button>
          </div>
        </Card>

        <div className="flex flex-col gap-5 lg:col-span-2">
          <div className="flex gap-2">
            {['all', 'Draft', 'In Review', 'Submitted'].map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded-lg px-3.5 py-2 text-xs font-semibold ${tab === t ? 'bg-brand-500 text-white' : 'bg-white text-slate-500 border border-slate-200'}`}
              >
                {t === 'all' ? 'All Proposals' : t}
              </button>
            ))}
          </div>

          <div className="flex flex-col gap-3">
            {proposals
              .filter((p) => tab === 'all' || p.status === tab)
              .map((p) => (
                <Card key={p.id}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-bold text-navy-900">{p.title}</p>
                      <p className="mt-1 text-xs text-slate-400">{p.company} · {p.tender}</p>
                    </div>
                    <StatusBadge status={p.status} />
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                      <div className="h-full rounded-full bg-brand-500" style={{ width: `${p.progress}%` }} />
                    </div>
                    <span className="text-xs font-semibold text-slate-500">{p.progress}%</span>
                  </div>
                  <div className="mt-3 flex items-center justify-between">
                    <p className="text-xs text-slate-400">Updated {p.updated}</p>
                    <div className="flex items-center gap-1 text-slate-400">
                      <button className="rounded-lg p-1.5 hover:bg-slate-100"><Eye size={14} /></button>
                      <button className="rounded-lg p-1.5 hover:bg-slate-100"><FileDown size={14} /></button>
                      <button className="rounded-lg p-1.5 hover:bg-slate-100"><MoreHorizontal size={14} /></button>
                    </div>
                  </div>
                </Card>
              ))}
          </div>
        </div>
      </div>
    </div>
  );
}
