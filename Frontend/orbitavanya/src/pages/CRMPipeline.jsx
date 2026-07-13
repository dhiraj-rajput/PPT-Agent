import { Plus, MoreHorizontal } from 'lucide-react';
import { PageHeader, Card } from '../components/ui/Common.jsx';
import { companies } from '../data/companies.js';

const columns = [
  { key: 'leads', label: 'New Leads', color: 'border-t-sky-400', items: companies.slice(0, 3) },
  { key: 'research', label: 'Research', color: 'border-t-brand-400', items: companies.slice(2, 5) },
  { key: 'proposal', label: 'Proposal Sent', color: 'border-t-violet-400', items: companies.slice(1, 3) },
  { key: 'interested', label: 'Interested', color: 'border-t-amber-400', items: companies.slice(4, 6) },
  { key: 'negotiation', label: 'Negotiation', color: 'border-t-teal-400', items: companies.slice(0, 2) },
  { key: 'won', label: 'Won', color: 'border-t-emerald-400', items: companies.slice(3, 4) },
];

export default function CRMPipeline() {
  return (
    <div>
      <PageHeader
        title="CRM Pipeline"
        subtitle="Track deals as they move from lead to won"
        action={
          <button className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft">
            <Plus size={16} /> Add Deal
          </button>
        }
      />

      <div className="flex gap-4 overflow-x-auto pb-4">
        {columns.map((col) => (
          <div key={col.key} className="w-72 shrink-0">
            <div className="mb-3 flex items-center justify-between px-1">
              <h3 className="text-sm font-bold text-navy-900">{col.label}</h3>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-500">{col.items.length}</span>
            </div>
            <div className={`flex flex-col gap-3 rounded-2xl border-t-4 ${col.color} bg-slate-50/60 p-2`}>
              {col.items.map((c) => (
                <Card key={c.id} className="!p-3 cursor-grab">
                  <div className="flex items-start justify-between">
                    <p className="text-sm font-semibold text-navy-900">{c.name}</p>
                    <button className="text-slate-300"><MoreHorizontal size={15} /></button>
                  </div>
                  <p className="mt-1 text-xs text-slate-400">{c.industry}</p>
                  <div className="mt-3 flex items-center justify-between">
                    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-700">{c.matchScore}% Match</span>
                    <img src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${c.contact}`} className="h-6 w-6 rounded-full" alt={c.contact} />
                  </div>
                </Card>
              ))}
              {col.items.length === 0 && (
                <p className="p-4 text-center text-xs text-slate-400">No deals here yet.</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
