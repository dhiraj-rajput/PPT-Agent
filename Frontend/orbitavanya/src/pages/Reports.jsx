import { useState, useEffect } from 'react';
import { FileBarChart, Download, Calendar, Eye, X, Loader2, AlertCircle } from 'lucide-react';
import { PageHeader, Card } from '../components/ui/Common.jsx';

const FALLBACK_REPORTS = [
  { filename: 'N00164-26-R-0001_prime_proposal.pdf', title: 'Prime Proposal', company_name: 'Booz Allen Hamilton Inc.', ref: 'N00164-26-R-0001', type: 'PDF', size: '305 KB', date: 'Jul 13, 2026' },
  { filename: 'N00164-26-R-0001_subcontract_proposal.pdf', title: 'Subcontract Proposal', company_name: 'Booz Allen Hamilton Inc.', ref: 'N00164-26-R-0001', type: 'PDF', size: '304 KB', date: 'Jul 13, 2026' },
];

export default function Reports() {
  const [reports, setReports] = useState(FALLBACK_REPORTS);
  const [previewing, setPreviewing] = useState(null);
  const [loading, setLoading] = useState(false);
  const [backendOffline, setBackendOffline] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch('http://localhost:8000/api/reports')
      .then((res) => {
        if (!res.ok) throw new Error('API server unreachable');
        return res.json();
      })
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setReports(data);
        }
        setBackendOffline(false);
        setLoading(false);
      })
      .catch((err) => {
        console.warn("Using fallback reports because API server is not running.", err);
        setBackendOffline(true);
        setLoading(false);
      });
  }, []);

  return (
    <div>
      <PageHeader title="Reports" subtitle="Generated business proposals and evaluation summaries" />
      
      {backendOffline && (
        <div className="mb-5 flex items-center gap-2 rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-700 dark:bg-amber-950/30 dark:border-amber-900/30 dark:text-amber-400">
          <AlertCircle size={18} className="shrink-0" />
          <div>
            <p className="font-bold">Backend Server Offline</p>
            <p className="text-xs mt-0.5">Please start the python server using <code className="bg-amber-100/50 dark:bg-amber-950/50 px-1 rounded">uvicorn server:app --reload</code> to view real-time generated PDF reports from the output folder.</p>
          </div>
        </div>
      )}

      {loading ? (
        <Card className="flex flex-col items-center justify-center py-20">
          <Loader2 className="animate-spin text-brand-500" size={32} />
          <p className="mt-4 text-sm text-slate-500 dark:text-slate-400 font-medium">Fetching reports database...</p>
        </Card>
      ) : (
        <Card className="!p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wide text-slate-400 dark:border-navy-800 dark:text-slate-400">
                  <th className="px-5 py-3 font-semibold">Report / Proposal</th>
                  <th className="px-5 py-3 font-semibold">Target Company</th>
                  <th className="px-5 py-3 font-semibold">RFP Reference</th>
                  <th className="px-5 py-3 font-semibold">Size</th>
                  <th className="px-5 py-3 font-semibold">Generated</th>
                  <th className="px-5 py-3 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((r) => (
                  <tr key={r.filename} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60 dark:border-navy-800/40 dark:hover:bg-navy-800/40">
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-600 dark:bg-navy-800 dark:text-brand-400">
                          <FileBarChart size={16} />
                        </div>
                        <div>
                          <p className="font-semibold text-navy-900 dark:text-white leading-tight">{r.title}</p>
                          <p className="text-xs text-slate-400 mt-0.5">{r.filename}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-slate-700 dark:text-slate-300 font-medium">{r.company_name}</td>
                    <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400 font-mono text-xs">{r.ref || 'N/A'}</td>
                    <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{r.size}</td>
                    <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">
                      <span className="flex items-center gap-1.5"><Calendar size={13} /> {r.date}</span>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => setPreviewing(r)}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700"
                        >
                          <Eye size={13} /> View
                        </button>
                        <a
                          href={`http://localhost:8000/api/reports/download/${r.filename}`}
                          download
                          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700"
                        >
                          <Download size={13} /> Download
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {previewing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/60 p-4 backdrop-blur-xs" onClick={() => setPreviewing(null)}>
          <div className="w-full max-w-5xl h-[85vh] flex flex-col rounded-2xl bg-white dark:bg-navy-800 shadow-soft overflow-hidden border border-slate-100 dark:border-navy-700" onClick={(e) => e.stopPropagation()}>
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-navy-700 p-5 shrink-0">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-navy-900 dark:text-brand-400">
                  <FileBarChart size={18} />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-navy-900 dark:text-white">{previewing.title}</h3>
                  <p className="text-xs text-slate-400 mt-0.5">{previewing.company_name} · Ref: {previewing.ref || 'N/A'} · {previewing.size}</p>
                </div>
              </div>
              <button onClick={() => setPreviewing(null)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-navy-900">
                <X size={18} />
              </button>
            </div>
            
            {/* Modal Body: Embedded PDF Viewer */}
            <div className="flex-1 bg-slate-50 dark:bg-navy-900 p-4">
              {backendOffline ? (
                <div className="flex h-full flex-col items-center justify-center text-center p-6 bg-white dark:bg-navy-800 rounded-xl border border-slate-100 dark:border-navy-700">
                  <AlertCircle className="text-amber-500 mb-3 animate-pulse" size={40} />
                  <h4 className="text-base font-bold text-navy-900 dark:text-white">Direct PDF Viewer Disabled</h4>
                  <p className="mt-2 text-sm text-slate-500 dark:text-slate-400 max-w-md">
                    To render the PDF directly inside this window, the backend server must be running. You can still download the file using the button below.
                  </p>
                  <a
                    href={`http://localhost:8000/api/reports/download/${previewing.filename}`}
                    download
                    className="mt-4 flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft"
                  >
                    <Download size={15} /> Download PDF File
                  </a>
                </div>
              ) : (
                <iframe
                  src={`http://localhost:8000/api/reports/view/${previewing.filename}`}
                  className="w-full h-full border-0 rounded-xl bg-white shadow-inner"
                  title={previewing.title}
                />
              )}
            </div>

            {/* Modal Footer */}
            <div className="flex justify-end gap-2 border-t border-slate-100 dark:border-navy-700 p-4 shrink-0 bg-white dark:bg-navy-800">
              <button onClick={() => setPreviewing(null)} className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700">
                Close
              </button>
              <a
                href={`http://localhost:8000/api/reports/download/${previewing.filename}`}
                download
                className="flex items-center gap-1.5 rounded-lg bg-brand-500 px-4 py-2 text-xs font-bold text-white shadow-soft hover:bg-brand-600"
              >
                <Download size={13} /> Download Report
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

