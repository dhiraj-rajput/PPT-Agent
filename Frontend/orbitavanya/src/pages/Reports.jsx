import { useState } from 'react';
import { FileBarChart, Download, Calendar, Eye, X } from 'lucide-react';
import { PageHeader, Card } from '../components/ui/Common.jsx';

const reports = [
  { name: 'Monthly Pipeline Summary', type: 'PDF', size: '1.2 MB', date: 'Jun 01, 2026', summary: 'A roll-up of every open, won, and lost opportunity across the pipeline for the month, broken down by stage and agency.' },
  { name: 'Tender Match Accuracy Report', type: 'XLSX', size: '640 KB', date: 'Jun 05, 2026', summary: 'Compares AI-predicted match scores against actual win/loss outcomes to track model accuracy over time.' },
  { name: 'Email Campaign Performance - May 2026', type: 'PDF', size: '890 KB', date: 'Jun 01, 2026', summary: 'Open, click, and reply rates for every campaign sent in May, with week-over-week trend lines.' },
  { name: 'Win/Loss Analysis Q2 2026', type: 'PDF', size: '2.1 MB', date: 'May 28, 2026', summary: 'A breakdown of won vs. lost proposals in Q2, including the most commonly cited reasons for each outcome.' },
  { name: 'Company Engagement Export', type: 'CSV', size: '310 KB', date: 'May 20, 2026', summary: 'Raw export of company-level engagement data - site visits, email opens, and meeting history.' },
];

export default function Reports() {
  const [previewing, setPreviewing] = useState(null);

  return (
    <div>
      <PageHeader title="Reports" subtitle="Generated reports and exports" />
      <Card className="!p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wide text-slate-400">
              <th className="px-5 py-3 font-semibold">Report</th>
              <th className="px-5 py-3 font-semibold">Type</th>
              <th className="px-5 py-3 font-semibold">Size</th>
              <th className="px-5 py-3 font-semibold">Generated</th>
              <th className="px-5 py-3 font-semibold text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {reports.map((r) => (
              <tr key={r.name} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60">
                <td className="px-5 py-3.5">
                  <div className="flex items-center gap-3 font-semibold text-navy-900">
                    <FileBarChart size={16} className="text-brand-500" /> {r.name}
                  </div>
                </td>
                <td className="px-5 py-3.5 text-slate-500">{r.type}</td>
                <td className="px-5 py-3.5 text-slate-500">{r.size}</td>
                <td className="px-5 py-3.5 text-slate-500">
                  <span className="flex items-center gap-1.5"><Calendar size={13} /> {r.date}</span>
                </td>
                <td className="px-5 py-3.5 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={() => setPreviewing(r)}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-navy-900 hover:bg-slate-50"
                    >
                      <Eye size={13} /> View
                    </button>
                    <button className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-navy-900 hover:bg-slate-50">
                      <Download size={13} /> Download
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {previewing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/50 p-4" onClick={() => setPreviewing(null)}>
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-soft" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                  <FileBarChart size={18} />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-navy-900">{previewing.name}</h3>
                  <p className="text-xs text-slate-400">{previewing.type} · {previewing.size} · Generated {previewing.date}</p>
                </div>
              </div>
              <button onClick={() => setPreviewing(null)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100">
                <X size={16} />
              </button>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-slate-600">{previewing.summary}</p>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setPreviewing(null)} className="rounded-lg border border-slate-200 px-3.5 py-2 text-xs font-semibold text-navy-900 hover:bg-slate-50">
                Close
              </button>
              <button className="flex items-center gap-1.5 rounded-lg bg-brand-500 px-3.5 py-2 text-xs font-bold text-white">
                <Download size={13} /> Download
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
