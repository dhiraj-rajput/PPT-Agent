import { useState, useEffect } from 'react';
import { FileBarChart, Download, Calendar, Eye, X, Loader2, AlertCircle, ShieldAlert, Filter, ChevronDown, SortAsc, SortDesc } from 'lucide-react';
import { PageHeader, Card } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';

const DOCUMENT_TYPES = [
  { value: 'all', label: 'All Types' },
  { value: 'Prime RFP Response', label: 'Prime Contract' },
  { value: 'Subcontract Response', label: 'Subcontract' },
  { value: 'other', label: 'Other' },
];

const FALLBACK_REPORTS = [
  { 
    filename: 'N00164-26-R-0001_prime_proposal.pdf', 
    title: 'Product Suitability & Match Report', 
    company_name: 'Booz Allen Hamilton Inc.', 
    solicitation_number: 'N00164-26-R-0001', 
    proposal_type: 'Prime RFP Response', 
    ref: 'N00164-26-R-0001', 
    type: 'PDF', 
    size: '305 KB', 
    date: 'Jul 13, 2026',
    mtime: 1752364800,
  },
  { 
    filename: 'N00164-26-R-0001_subcontract_proposal.pdf', 
    title: 'Subcontract Proposal', 
    company_name: 'Booz Allen Hamilton Inc.', 
    solicitation_number: 'N00164-26-R-0001', 
    proposal_type: 'Subcontract Response', 
    ref: 'N00164-26-R-0001', 
    type: 'PDF', 
    size: '304 KB', 
    date: 'Jul 13, 2026',
    mtime: 1752364700,
  },
];

function TypeFilterBadge({ type, active, onClick }) {
  return (
    <button
      onClick={() => onClick(type.value)}
      className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold transition-all ${
        active
          ? 'bg-brand-500 text-white shadow-sm'
          : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700'
      }`}
    >
      {type.label}
    </button>
  );
}

export default function Reports() {
  const [reports, setReports] = useState(FALLBACK_REPORTS);
  const [previewing, setPreviewing] = useState(null);
  const [loading, setLoading] = useState(false);
  const [backendOffline, setBackendOffline] = useState(false);
  const [previewUrl, setPreviewUrl] = useState(null);

  // Filter & Sort States
  const [typeFilter, setTypeFilter] = useState('all');
  const [sortOrder, setSortOrder] = useState('newest'); // 'newest' | 'oldest'

  useEffect(() => {
    if (previewing && !backendOffline) {
      api.viewReportBlob(previewing.filename)
        .then((blob) => {
          const url = URL.createObjectURL(blob);
          setPreviewUrl(url);
        })
        .catch((err) => {
          console.error('Error creating preview URL:', err);
          setPreviewUrl(null);
        });
    } else {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        setPreviewUrl(null);
      }
    }
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewing, backendOffline]);

  const handleDownload = async (e, filename) => {
    e.preventDefault();
    try {
      const blob = await api.downloadReport(filename);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Download failed:', err);
      alert('Failed to download file.');
    }
  };

  useEffect(() => {
    setLoading(true);
    api.getReports()
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setReports(data);
        }
        setBackendOffline(false);
        setLoading(false);
      })
      .catch((err) => {
        console.warn('Using fallback reports because API server is not running.', err);
        setBackendOffline(true);
        setLoading(false);
      });
  }, []);

  // Filter and sort reports
  const filteredReports = reports
    .filter(r => {
      if (typeFilter === 'all') return true;
      if (typeFilter === 'other') {
        const type = (r.proposal_type || '').toLowerCase();
        return !type.includes('prime') && !type.includes('subcontract');
      }
      return (r.proposal_type || '').toLowerCase().includes(typeFilter.toLowerCase());
    })
    .sort((a, b) => {
      if (sortOrder === 'newest') return (b.mtime || 0) - (a.mtime || 0);
      return (a.mtime || 0) - (b.mtime || 0);
    });

  const proposalTypeBadgeColor = (type) => {
    const t = (type || '').toLowerCase();
    if (t.includes('prime')) return 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300';
    if (t.includes('subcontract')) return 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300';
    if (t.includes('capability')) return 'bg-purple-50 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300';
    if (t.includes('grant')) return 'bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300';
    return 'bg-slate-100 text-slate-700 dark:bg-navy-800 dark:text-slate-300';
  };

  return (
    <div>
      <PageHeader title="Reports" subtitle="Generated business proposals and evaluation summaries" />

      {backendOffline && (
        <div className="mb-5 flex items-center gap-2 rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-700 dark:bg-amber-950/30 dark:border-amber-900/30 dark:text-amber-400">
          <AlertCircle size={18} className="shrink-0" />
          <div>
            <p className="font-bold">Backend Server Offline</p>
            <p className="text-xs mt-0.5">Please start the python server using <code className="bg-amber-100/50 dark:bg-amber-950/50 px-1 rounded">uv run server.py</code> to view real-time generated PDF reports from the output folder.</p>
          </div>
        </div>
      )}

      {/* Filters & Sort Controls */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 flex items-center gap-1">
            <Filter size={13} /> Filter:
          </span>
          {DOCUMENT_TYPES.map(type => (
            <TypeFilterBadge
              key={type.value}
              type={type}
              active={typeFilter === type.value}
              onClick={setTypeFilter}
            />
          ))}
        </div>
        <button
          onClick={() => setSortOrder(s => s === 'newest' ? 'oldest' : 'newest')}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors"
        >
          {sortOrder === 'newest' ? <SortDesc size={13} /> : <SortAsc size={13} />}
          {sortOrder === 'newest' ? 'Newest First' : 'Oldest First'}
        </button>
      </div>

      <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
        {filteredReports.length} document{filteredReports.length !== 1 ? 's' : ''}
        {typeFilter !== 'all' ? ` · Filtered by "${DOCUMENT_TYPES.find(t => t.value === typeFilter)?.label}"` : ''}
      </p>

      {loading ? (
        <Card className="flex flex-col items-center justify-center py-20">
          <Loader2 className="animate-spin text-brand-500" size={32} />
          <p className="mt-4 text-sm text-slate-500 dark:text-slate-400 font-medium">Fetching reports database...</p>
        </Card>
      ) : filteredReports.length === 0 ? (
        <Card className="flex flex-col items-center justify-center py-16 text-center">
          <FileBarChart className="text-slate-300 dark:text-slate-600 mb-3" size={40} />
          <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">No reports found</p>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
            {typeFilter !== 'all' ? 'Try changing the filter.' : 'Generate a proposal from the Proposal Builder.'}
          </p>
        </Card>
      ) : (
        <Card className="!p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wide text-slate-400 dark:border-navy-800 dark:text-slate-400">
                  <th className="px-5 py-3 font-semibold">Intended Company & Details</th>
                  <th className="px-5 py-3 font-semibold">Type</th>
                  <th className="px-5 py-3 font-semibold">Source</th>
                  <th className="px-5 py-3 font-semibold">Solicitation Number</th>
                  <th className="px-5 py-3 font-semibold">Size</th>
                  <th className="px-5 py-3 font-semibold">Generated</th>
                  <th className="px-5 py-3 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredReports.map((r) => (
                  <tr key={r.filename} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60 dark:border-navy-800/40 dark:hover:bg-navy-800/40">
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-navy-800 dark:text-brand-400">
                          <FileBarChart size={18} />
                        </div>
                        <div>
                          <p className="font-bold text-navy-900 dark:text-white leading-tight text-sm">
                            {r.company_name}
                          </p>
                          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1 flex items-center gap-1.5">
                            <span className="font-semibold text-slate-600 dark:text-slate-400">{r.proposal_type}</span>
                            <span>•</span>
                            <span className="font-mono">{r.solicitation_number || r.ref || 'N/A'}</span>
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${proposalTypeBadgeColor(r.proposal_type)}`}>
                        {r.proposal_type}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 dark:bg-navy-800 px-2.5 py-0.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
                        {r.source || (r.filename.toLowerCase().includes('prime') ? 'SAM.gov' : 'RFP Auto-Respond')}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400 font-mono text-sm">
                      {r.solicitation_number || r.ref || 'N/A'}
                    </td>
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
                        <button
                          onClick={(e) => handleDownload(e, r.filename)}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700"
                        >
                          <Download size={13} /> Download
                        </button>
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/80 p-4 md:p-6 backdrop-blur-md" onClick={() => setPreviewing(null)}>
          <div className="w-[94vw] md:w-[90vw] lg:w-[85vw] max-w-7xl h-[92vh] flex flex-col rounded-2xl bg-white dark:bg-navy-800 shadow-2xl overflow-hidden border border-slate-100 dark:border-navy-700" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-navy-700 p-5 shrink-0 bg-white dark:bg-navy-800">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-navy-900 dark:text-brand-400">
                  <FileBarChart size={20} />
                </div>
                <div>
                  <h3 className="text-base font-extrabold text-navy-900 dark:text-white leading-tight">{previewing.company_name}</h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${proposalTypeBadgeColor(previewing.proposal_type)}`}>{previewing.proposal_type}</span>
                    <span>•</span>
                    <span className="font-mono bg-slate-100 dark:bg-navy-900 px-1.5 py-0.5 rounded text-[10px]">{previewing.solicitation_number || previewing.ref || 'N/A'}</span>
                    <span>•</span>
                    <span>{previewing.size}</span>
                    <span>•</span>
                    <span>Generated {previewing.date}</span>
                  </p>
                </div>
              </div>
              <button onClick={() => setPreviewing(null)} className="rounded-lg p-2 text-slate-400 hover:text-navy-950 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-navy-900 transition-colors">
                <X size={20} />
              </button>
            </div>
            
            <div className="flex-1 bg-slate-100 dark:bg-navy-900 p-4 md:p-6 flex flex-col overflow-hidden">
              {backendOffline ? (
                <div className="flex h-full flex-col items-center justify-center text-center p-8 bg-white dark:bg-navy-800 rounded-xl border border-slate-100 dark:border-navy-700 shadow-soft">
                  <ShieldAlert className="text-amber-500 mb-4" size={48} />
                  <h4 className="text-lg font-bold text-navy-900 dark:text-white">Direct PDF Viewer Disabled</h4>
                  <p className="mt-2 text-sm text-slate-500 dark:text-slate-400 max-w-md">
                    To render the PDF directly inside this window, the backend server must be running. You can still download the file using the button below.
                  </p>
                  <button
                    onClick={(e) => handleDownload(e, previewing.filename)}
                    className="mt-5 flex items-center gap-2 rounded-xl bg-brand-500 px-5 py-3 text-sm font-bold text-white shadow-soft transition-all hover:bg-brand-600"
                  >
                    <Download size={16} /> Download PDF File
                  </button>
                </div>
              ) : (
                <iframe
                  src={previewUrl || ''}
                  className="w-full h-full border-0 rounded-xl bg-white shadow-lg"
                  title={previewing.title}
                />
              )}
            </div>

            <div className="flex justify-end gap-3 border-t border-slate-100 dark:border-navy-700 p-5 shrink-0 bg-white dark:bg-navy-800">
              <button onClick={() => setPreviewing(null)} className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700 transition-colors">
                Close
              </button>
              <button
                onClick={(e) => handleDownload(e, previewing.filename)}
                className="flex items-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 text-xs font-bold text-white shadow-soft hover:bg-brand-600 transition-colors"
              >
                <Download size={14} /> Download PDF
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
