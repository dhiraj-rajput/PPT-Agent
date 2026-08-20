import { useEffect, useMemo, useState } from 'react';
import { FileText, Download, Eye, ChevronLeft, ChevronRight, Loader2, RefreshCw } from 'lucide-react';
import { api } from '../lib/api.jsx';

const PAGE_SIZE = 10;

/**
 * Reports page — lists generated proposals / RFP responses with client-side
 * pagination so long histories stay usable.
 *
 * Drop this file at Frontend/src/pages/Reports.jsx and wire the route/sidebar
 * to it if not already connected.
 */
export default function Reports() {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState('');
  const [busyFile, setBusyFile] = useState(null);

  async function load() {
    setLoading(true);
    setError('');
    try {
      const data = await api.getReports();
      const list = Array.isArray(data) ? data : data?.reports || data?.items || [];
      setReports(list);
      setPage(1);
    } catch (err) {
      setError(err.message || 'Failed to load reports.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return reports;
    return reports.filter((r) => {
      const blob = [
        r.filename,
        r.proposal_title,
        r.company_name,
        r.proposal_type,
        r.status,
        r.ref,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return blob.includes(q);
    });
  }, [reports, query]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const slice = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  async function handleDownload(filename) {
    setBusyFile(filename);
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
      setError(err.message || 'Download failed');
    } finally {
      setBusyFile(null);
    }
  }

  async function handleView(filename) {
    setBusyFile(filename);
    let objectUrl = null;
    try {
      const blob = await api.viewReportBlob(filename);
      objectUrl = window.URL.createObjectURL(blob);
      window.open(objectUrl, '_blank', 'noopener,noreferrer');
      // Revoke after a short delay to allow the new tab to load
      setTimeout(() => { if (objectUrl) window.URL.revokeObjectURL(objectUrl); }, 10000);
    } catch (err) {
      if (objectUrl) window.URL.revokeObjectURL(objectUrl);
      setError(err.message || 'Preview failed');
    } finally {
      setBusyFile(null);
    }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-white flex items-center gap-2">
            <FileText className="w-5 h-5 text-blue-500" /> Reports
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Generated proposals and RFP responses ({filtered.length} shown
            {query ? ` of ${reports.length}` : ''})
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          Refresh
        </button>
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(1);
          }}
          placeholder="Search by filename, company, type…"
          className="flex-1 min-w-[200px] text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
        />
      </div>

      {error && (
        <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      <div className="rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden bg-white dark:bg-slate-900">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800/80 text-left text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">Document</th>
                <th className="px-4 py-3 font-medium hidden md:table-cell">Type</th>
                <th className="px-4 py-3 font-medium hidden lg:table-cell">Company</th>
                <th className="px-4 py-3 font-medium hidden sm:table-cell">Status</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-slate-400">
                    <Loader2 className="w-5 h-5 animate-spin inline mr-2" />
                    Loading reports…
                  </td>
                </tr>
              )}
              {!loading && slice.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-slate-400">
                    No reports found.
                  </td>
                </tr>
              )}
              {!loading &&
                slice.map((r) => {
                  const name = r.filename || r.name || r.id || '—';
                  return (
                    <tr
                      key={name}
                      className="border-t border-slate-100 dark:border-slate-800 hover:bg-slate-50/80 dark:hover:bg-slate-800/40"
                    >
                      <td className="px-4 py-3">
                        <div className="font-medium text-slate-800 dark:text-slate-100 break-all">
                          {r.proposal_title || name}
                        </div>
                        <div className="text-xs text-slate-400 mt-0.5 break-all">{name}</div>
                      </td>
                      <td className="px-4 py-3 hidden md:table-cell text-slate-600 dark:text-slate-300">
                        {r.proposal_type || r.type || '—'}
                      </td>
                      <td className="px-4 py-3 hidden lg:table-cell text-slate-600 dark:text-slate-300">
                        {r.company_name || '—'}
                      </td>
                      <td className="px-4 py-3 hidden sm:table-cell">
                        <span className="inline-flex text-xs px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                          {r.status || 'ready'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <button
                          type="button"
                          disabled={busyFile === name}
                          onClick={() => handleView(name)}
                          className="inline-flex items-center gap-1 text-xs px-2 py-1.5 rounded-md border border-slate-200 dark:border-slate-700 mr-1 hover:bg-slate-50 dark:hover:bg-slate-800"
                          title="View"
                        >
                          <Eye className="w-3.5 h-3.5" /> View
                        </button>
                        <button
                          type="button"
                          disabled={busyFile === name}
                          onClick={() => handleDownload(name)}
                          className="inline-flex items-center gap-1 text-xs px-2 py-1.5 rounded-md bg-blue-600 text-white hover:bg-blue-700"
                          title="Download"
                        >
                          <Download className="w-3.5 h-3.5" /> Download
                        </button>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30">
          <div className="text-xs text-slate-500">
            Page {safePage} of {totalPages} · {PAGE_SIZE} per page
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              disabled={safePage <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-md border border-slate-200 dark:border-slate-700 disabled:opacity-40"
            >
              <ChevronLeft className="w-3.5 h-3.5" /> Prev
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter((n) => n === 1 || n === totalPages || Math.abs(n - safePage) <= 2)
              .reduce((acc, n, idx, arr) => {
                if (idx > 0 && n - arr[idx - 1] > 1) acc.push('…');
                acc.push(n);
                return acc;
              }, [])
              .map((n, idx) =>
                n === '…' ? (
                  <span key={`e${idx}`} className="px-1 text-slate-400 text-xs">
                    …
                  </span>
                ) : (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setPage(n)}
                    className={`w-8 h-8 rounded-md text-xs ${
                      n === safePage
                        ? 'bg-blue-600 text-white'
                        : 'border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300'
                    }`}
                  >
                    {n}
                  </button>
                )
              )}
            <button
              type="button"
              disabled={safePage >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-md border border-slate-200 dark:border-slate-700 disabled:opacity-40"
            >
              Next <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
