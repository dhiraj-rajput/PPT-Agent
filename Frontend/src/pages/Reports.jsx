import { useState, useEffect } from 'react';
import { FileBarChart, Download, Calendar, Eye, X, Loader2, AlertCircle, ShieldAlert, Filter, SortAsc, SortDesc, Mail, ExternalLink, Send, CheckCircle2 } from 'lucide-react';
import { PageHeader, Card } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';

const DOCUMENT_TYPES = [
  { value: 'all', label: 'All Types' },
  { value: 'Prime RFP Response', label: 'Prime Contract' },
  { value: 'Subcontract Response', label: 'Subcontract' },
  { value: 'other', label: 'Other' },
];

const REPORT_STATUSES = [
  { value: 'Generated', label: 'Generated', color: 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 border-blue-200' },
  { value: 'Draft', label: 'Draft', color: 'bg-slate-100 text-slate-700 dark:bg-navy-800 dark:text-slate-300 border-slate-200' },
  { value: 'Sent', label: 'Sent', color: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 border-emerald-200' },
  { value: 'Submitted', label: 'Submitted (SAM)', color: 'bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300 border-indigo-200' },
  { value: 'Downloaded', label: 'Downloaded', color: 'bg-purple-50 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300 border-purple-200' },
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
    status: 'Generated',
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
    status: 'Generated',
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

  // Send Email Modal States
  const [emailModalReport, setEmailModalReport] = useState(null);
  const [emailForm, setEmailForm] = useState({
    to_email: '',
    subject: '',
    body: '',
  });
  const [sendingEmail, setSendingEmail] = useState(false);
  const [emailNotice, setEmailNotice] = useState(null);

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

  const loadReports = () => {
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
  };

  useEffect(() => {
    loadReports();
  }, []);

  const handleDownload = async (e, filename) => {
    if (e) e.preventDefault();
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

      // Update local report status
      setReports(prev => prev.map(r => r.filename === filename ? { ...r, status: r.status === 'Sent' || r.status === 'Submitted' ? r.status : 'Downloaded' } : r));
    } catch (err) {
      console.error('Download failed:', err);
      alert('Failed to download file.');
    }
  };

  const handleStatusChange = async (filename, newStatus) => {
    try {
      setReports(prev => prev.map(r => r.filename === filename ? { ...r, status: newStatus } : r));
      await api.updateReportStatus(filename, newStatus);
    } catch (err) {
      console.error('Failed to update report status:', err);
    }
  };

  const openEmailModal = (report) => {
    setEmailModalReport(report);
    const isPrime = (report.proposal_type || '').toLowerCase().includes('prime');
    const isSub = (report.proposal_type || '').toLowerCase().includes('subcontract');
    const typeLabel = isPrime ? 'Prime Proposal' : isSub ? 'Subcontract Teaming Proposal' : 'Partnership Proposal';

    const escapeHtml = (s) => String(s || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#x27;');

    setEmailForm({
      to_email: report.sentTo || 'procurement@' + (report.company_name || 'company').toLowerCase().replace(/[^a-z0-9]/g, '') + '.com',
      subject: `[${typeLabel}] ${report.title || report.company_name} — Solicitation ${report.solicitation_number || report.ref || 'Ref'}`,
      body: `<p>Dear Team at ${escapeHtml(report.company_name)},</p>
<p>Please find attached our generated <strong>${typeLabel}</strong> for solicitation <strong>${escapeHtml(report.solicitation_number || report.ref || '')}</strong>.</p>
<p>We welcome the opportunity to discuss our technical approach, capabilities, and delivery timeline.</p>
<p>Best regards,<br/>OrbitAvanya Tech LLP Teaming & Contracting Team</p>`,
    });
    setEmailNotice(null);
  };

  const handleSendEmailSubmit = async (e) => {
    e.preventDefault();
    if (!emailForm.to_email) return;

    setSendingEmail(true);
    setEmailNotice(null);

    try {
      await api.sendReportEmail({
        filename: emailModalReport.filename,
        to_email: emailForm.to_email,
        subject: emailForm.subject,
        body: emailForm.body,
        company_name: emailModalReport.company_name,
      });

      setReports(prev => prev.map(r => r.filename === emailModalReport.filename ? { ...r, status: 'Sent' } : r));
      setEmailNotice({ type: 'success', text: `Proposal email successfully sent to ${emailForm.to_email} and logged in Campaign & CRM!` });
      setTimeout(() => {
        setEmailModalReport(null);
        setSendingEmail(false);
      }, 1500);
    } catch (err) {
      console.error('Email send failed:', err);
      setEmailNotice({ type: 'error', text: err.message || 'Failed to send email' });
      setSendingEmail(false);
    }
  };

  const handleSamUploadRedirect = async (report) => {
    const samUrl = report.solicitation_number && report.solicitation_number !== 'N/A'
      ? `https://sam.gov/search/?index=opp&q=${encodeURIComponent(report.solicitation_number)}`
      : 'https://sam.gov/workspace/opportunities';
    const newWindow = window.open('about:blank', '_blank');
    try {
      // 1. Download file locally
      await handleDownload(null, report.filename);

      // 2. Update status to Submitted
      await handleStatusChange(report.filename, 'Submitted');

      // 3. Open SAM.gov workspace in new tab
      if (newWindow) newWindow.location.href = samUrl;
    } catch (e) {
      if (newWindow) newWindow.close();
      console.error(e.message);
    }
  };

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

  const getStatusBadge = (status) => {
    const found = REPORT_STATUSES.find(s => s.value === status) || REPORT_STATUSES[0];
    return found;
  };

  return (
    <div>
      <PageHeader title="Reports & Proposals" subtitle="Generated business proposals, teaming agreements, and submission status tracking" />

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
          {/* Desktop Table View */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wide text-slate-400 dark:border-navy-800 dark:text-slate-400">
                  <th className="px-5 py-3 font-semibold">Intended Company & Details</th>
                  <th className="px-5 py-3 font-semibold">Type</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                  <th className="px-5 py-3 font-semibold">Solicitation Ref</th>
                  <th className="px-5 py-3 font-semibold">Generated</th>
                  <th className="px-5 py-3 font-semibold text-right">Actions & Outreach</th>
                </tr>
              </thead>
              <tbody>
                {filteredReports.map((r) => {
                  const statusInfo = getStatusBadge(r.status || 'Generated');
                  const isPrime = (r.proposal_type || '').toLowerCase().includes('prime');
                  
                  return (
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
                              <span className="font-semibold text-slate-600 dark:text-slate-400">{r.title || r.filename}</span>
                              <span>•</span>
                              <span>{r.size}</span>
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${proposalTypeBadgeColor(r.proposal_type)}`}>
                          {r.proposal_type}
                        </span>
                      </td>
                      {/* Status Column */}
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-2">
                          <select
                            value={r.status || 'Generated'}
                            onChange={(e) => handleStatusChange(r.filename, e.target.value)}
                            className={`rounded-lg px-2.5 py-1 text-xs font-bold border ${statusInfo.color} cursor-pointer outline-none transition-all`}
                          >
                            {REPORT_STATUSES.map(st => (
                              <option key={st.value} value={st.value}>{st.label}</option>
                            ))}
                          </select>
                        </div>
                      </td>
                      <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400 font-mono text-xs">
                        {r.solicitation_number || r.ref || 'N/A'}
                      </td>
                      <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400 text-xs">
                        <span className="flex items-center gap-1.5"><Calendar size={13} /> {r.date}</span>
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        <div className="flex items-center justify-end gap-1.5 flex-wrap">
                          {/* Send Email Action */}
                          <button
                            onClick={() => openEmailModal(r)}
                            title="Send Proposal Email (Logs to Campaign & CRM)"
                            className="inline-flex items-center gap-1 rounded-lg bg-emerald-50 px-2.5 py-1.5 text-xs font-bold text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-950/40 dark:text-emerald-300 dark:hover:bg-emerald-900/60 transition-colors"
                          >
                            <Mail size={13} /> Email
                          </button>

                          {/* SAM.gov Submission Action */}
                          {isPrime && (
                            <button
                              onClick={() => handleSamUploadRedirect(r)}
                              title="Submit on SAM.gov (Downloads locally & redirects)"
                              className="inline-flex items-center gap-1 rounded-lg bg-indigo-50 px-2.5 py-1.5 text-xs font-bold text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-950/40 dark:text-indigo-300 dark:hover:bg-indigo-900/60 transition-colors"
                            >
                              <ExternalLink size={13} /> SAM.gov
                            </button>
                          )}

                          {/* Download Button */}
                          <button
                            onClick={(e) => handleDownload(e, r.filename)}
                            title="Download PDF file locally"
                            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700"
                          >
                            <Download size={13} /> PDF
                          </button>

                          {/* View Preview Button */}
                          <button
                            onClick={() => setPreviewing(r)}
                            title="Preview PDF inline"
                            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700"
                          >
                            <Eye size={13} /> View
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Mobile Card List View */}
          <div className="block md:hidden divide-y divide-slate-100 dark:divide-navy-800">
            {filteredReports.map((r) => {
              const statusInfo = getStatusBadge(r.status || 'Generated');
              const isPrime = (r.proposal_type || '').toLowerCase().includes('prime');
              
              return (
                <div key={r.filename} className="p-4 space-y-3.5 hover:bg-slate-50/40 dark:hover:bg-navy-800/40 transition-colors">
                  <div className="flex items-start justify-between gap-2.5">
                    <div className="flex gap-2.5 min-w-0">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600 dark:bg-navy-850 dark:text-brand-400">
                        <FileBarChart size={16} />
                      </div>
                      <div className="min-w-0">
                        <p className="font-bold text-navy-900 dark:text-white leading-snug text-sm">
                          {r.company_name}
                        </p>
                        <p className="text-xs text-slate-500 mt-0.5 truncate font-medium">
                          {r.title || r.filename}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-semibold ${proposalTypeBadgeColor(r.proposal_type)}`}>
                      {r.proposal_type}
                    </span>
                    <span className="text-[10px] bg-slate-100 text-slate-600 dark:bg-navy-800 dark:text-slate-400 font-mono px-2 py-0.5 rounded-full">
                      Ref: {r.solicitation_number || r.ref || 'N/A'}
                    </span>
                    <span className="text-[10px] text-slate-400 flex items-center gap-1.5 ml-auto">
                      <Calendar size={11} /> {r.date} ({r.size})
                    </span>
                  </div>

                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2.5 border-t border-slate-100/60 dark:border-navy-800/40">
                    <div className="flex items-center">
                      <select
                        value={r.status || 'Generated'}
                        onChange={(e) => handleStatusChange(r.filename, e.target.value)}
                        className={`rounded-lg px-2.5 py-1 text-xs font-bold border ${statusInfo.color} cursor-pointer outline-none transition-all`}
                      >
                        {REPORT_STATUSES.map(st => (
                          <option key={st.value} value={st.value}>{st.label}</option>
                        ))}
                      </select>
                    </div>

                    <div className="flex items-center gap-1.5 self-end sm:self-auto">
                      {/* Send Email Action */}
                      <button
                        onClick={() => openEmailModal(r)}
                        className="inline-flex items-center gap-1 rounded-lg bg-emerald-50 px-2 py-1 text-[11px] font-bold text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-950/40 dark:text-emerald-300 dark:hover:bg-emerald-900/60 transition-colors"
                      >
                        <Mail size={12} /> Email
                      </button>

                      {/* SAM.gov Submission Action */}
                      {isPrime && (
                        <button
                          onClick={() => handleSamUploadRedirect(r)}
                          className="inline-flex items-center gap-1 rounded-lg bg-indigo-50 px-2 py-1 text-[11px] font-bold text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-950/40 dark:text-indigo-300 dark:hover:bg-indigo-900/60 transition-colors"
                        >
                          <ExternalLink size={12} /> SAM
                        </button>
                      )}

                      {/* Download Button */}
                      <button
                        onClick={(e) => handleDownload(e, r.filename)}
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700"
                      >
                        <Download size={12} /> PDF
                      </button>

                      {/* View Preview Button */}
                      <button
                        onClick={() => setPreviewing(r)}
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700"
                      >
                        <Eye size={12} /> View
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* Send Email Modal */}
      {emailModalReport && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/70 p-4 backdrop-blur-sm" onClick={() => setEmailModalReport(null)}>
          <div className="w-full max-w-lg rounded-2xl bg-white dark:bg-navy-800 p-6 shadow-2xl border border-slate-100 dark:border-navy-700" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between gap-3 pb-4 border-b border-slate-100 dark:border-navy-700 mb-4">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400">
                  <Mail size={18} />
                </div>
                <div className="min-w-0">
                  <h3 className="text-base font-extrabold text-navy-900 dark:text-white leading-tight truncate">Send Proposal Email</h3>
                  <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5 truncate">Logs outreach to Email Campaign & CRM pipeline</p>
                </div>
              </div>
              <button onClick={() => setEmailModalReport(null)} className="shrink-0 rounded-lg p-1.5 text-slate-400 hover:text-navy-900 dark:hover:text-white">
                <X size={18} />
              </button>
            </div>

            {emailNotice && (
              <div className={`mb-4 flex items-center gap-2 rounded-xl p-3 text-xs font-semibold ${
                emailNotice.type === 'success' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200'
              }`}>
                {emailNotice.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                <span>{emailNotice.text}</span>
              </div>
            )}

            <form onSubmit={handleSendEmailSubmit} className="space-y-4 text-xs">
              <div>
                <label className="font-bold text-slate-600 dark:text-slate-300 block mb-1">To Email Address</label>
                <input
                  type="email"
                  required
                  value={emailForm.to_email}
                  onChange={(e) => setEmailForm({ ...emailForm, to_email: e.target.value })}
                  placeholder="recipient@company.com"
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 p-2.5 text-xs text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white outline-none focus:border-brand-500"
                />
              </div>

              <div>
                <label className="font-bold text-slate-600 dark:text-slate-300 block mb-1">Subject</label>
                <input
                  type="text"
                  required
                  value={emailForm.subject}
                  onChange={(e) => setEmailForm({ ...emailForm, subject: e.target.value })}
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 p-2.5 text-xs text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white outline-none focus:border-brand-500"
                />
              </div>

              <div>
                <label className="font-bold text-slate-600 dark:text-slate-300 block mb-1">Attached PDF Proposal</label>
                <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-100 p-2.5 text-xs font-mono text-slate-700 dark:border-navy-700 dark:bg-navy-900 dark:text-slate-300">
                  <FileBarChart size={14} className="text-brand-500" />
                  <span className="truncate">{emailModalReport.filename}</span>
                </div>
              </div>

              <div>
                <label className="font-bold text-slate-600 dark:text-slate-300 block mb-1">Email Body</label>
                <textarea
                  rows={5}
                  value={emailForm.body}
                  onChange={(e) => setEmailForm({ ...emailForm, body: e.target.value })}
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 p-2.5 text-xs text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white outline-none focus:border-brand-500 font-sans"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-100 dark:border-navy-700">
                <button
                  type="button"
                  onClick={() => setEmailModalReport(null)}
                  className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-300"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={sendingEmail}
                  className="flex items-center gap-1.5 rounded-xl bg-emerald-500 px-5 py-2 text-xs font-bold text-white shadow-soft hover:bg-emerald-600 disabled:opacity-50"
                >
                  {sendingEmail ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                  Send Proposal Email
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* PDF Inline Preview Modal */}
      {previewing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/80 p-4 md:p-6 backdrop-blur-md" onClick={() => setPreviewing(null)}>
          <div className="w-[94vw] md:w-[90vw] lg:w-[85vw] max-w-7xl h-[92vh] flex flex-col rounded-2xl bg-white dark:bg-navy-800 shadow-2xl overflow-hidden border border-slate-100 dark:border-navy-700" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between gap-3 border-b border-slate-100 dark:border-navy-700 p-5 shrink-0 bg-white dark:bg-navy-800">
              <div className="flex items-center gap-3 min-w-0">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-navy-900 dark:text-brand-400">
                  <FileBarChart size={20} />
                </div>
                <div className="min-w-0">
                  <h3 className="text-base font-extrabold text-navy-900 dark:text-white leading-tight truncate">{previewing.company_name}</h3>
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
              <button onClick={() => setPreviewing(null)} className="shrink-0 rounded-lg p-2 text-slate-400 hover:text-navy-950 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-navy-900 transition-colors">
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
