import { useEffect, useState } from 'react';
import { X, Download, FileText, Loader2, AlertTriangle } from 'lucide-react';

/**
 * DocPreviewModal
 * ----------------
 * Renders a PDF or .docx file inline in the browser without forcing a
 * download. Give it either:
 *   - `blob`     : a Blob/File already in memory (e.g. a freshly-selected
 *                  upload before it's even sent to the server), or
 *   - `fetchBlob`: an async function that resolves to a Blob (e.g. an
 *                  authenticated fetch against a `/view/...` endpoint).
 *
 * PDFs render natively via an <iframe> pointed at a blob: URL. .docx files
 * are converted to styled HTML client-side with mammoth.js so no download
 * or server-side conversion is needed.
 */
export default function DocPreviewModal({ title, subtitle, filename, blob, fetchBlob, onClose }) {
  const [objectUrl, setObjectUrl] = useState(null);
  const [docxHtml, setDocxHtml] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const isDocx = (filename || '').toLowerCase().endsWith('.docx');
  const isPdf = (filename || '').toLowerCase().endsWith('.pdf');

  useEffect(() => {
    let cancelled = false;
    let localUrl = null;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const fileBlob = blob || (fetchBlob ? await fetchBlob() : null);
        if (!fileBlob) throw new Error('No file available to preview');
        if (cancelled) return;

        if (isDocx) {
          const mammoth = await import('mammoth');
          const arrayBuffer = await fileBlob.arrayBuffer();
          const result = await mammoth.convertToHtml({ arrayBuffer });
          if (!cancelled) setDocxHtml(result.value);
        } else {
          localUrl = URL.createObjectURL(fileBlob);
          if (!cancelled) setObjectUrl(localUrl);
        }
      } catch (e) {
        if (!cancelled) setError(e.message || 'Failed to load preview');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
      if (localUrl) URL.revokeObjectURL(localUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blob, fetchBlob, filename]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/80 p-4 md:p-6 backdrop-blur-md"
      onClick={onClose}
    >
      <div
        className="w-[94vw] md:w-[90vw] lg:w-[85vw] max-w-7xl h-[92vh] flex flex-col rounded-2xl bg-white dark:bg-navy-800 shadow-2xl overflow-hidden border border-slate-100 dark:border-navy-700"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-navy-700 p-5 shrink-0 bg-white dark:bg-navy-800">
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-navy-900 dark:text-brand-400 shrink-0">
              <FileText size={20} />
            </div>
            <div className="min-w-0">
              <h3 className="text-base font-extrabold text-navy-900 dark:text-white leading-tight truncate">
                {title || filename || 'Preview'}
              </h3>
              {subtitle && (
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 truncate">{subtitle}</p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 hover:text-navy-950 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-navy-900 transition-colors shrink-0"
          >
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 bg-slate-100 dark:bg-navy-900 p-4 md:p-6 flex flex-col overflow-hidden">
          {loading && (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <Loader2 className="animate-spin text-brand-500 mb-3" size={32} />
              <p className="text-sm text-slate-500 dark:text-slate-400">Loading preview…</p>
            </div>
          )}

          {!loading && error && (
            <div className="flex h-full flex-col items-center justify-center text-center p-8 bg-white dark:bg-navy-800 rounded-xl border border-slate-100 dark:border-navy-700 shadow-soft">
              <AlertTriangle className="text-amber-500 mb-4" size={40} />
              <h4 className="text-lg font-bold text-navy-900 dark:text-white">Couldn't load preview</h4>
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400 max-w-md">{error}</p>
            </div>
          )}

          {!loading && !error && isPdf && objectUrl && (
            <div className="flex-1 rounded-xl overflow-hidden border border-slate-200 dark:border-navy-700 bg-white">
              <iframe title={filename || 'PDF preview'} src={objectUrl} className="w-full h-full" />
            </div>
          )}

          {!loading && !error && isDocx && docxHtml && (
            <div className="flex-1 overflow-auto rounded-xl border border-slate-200 dark:border-navy-700 bg-white p-8">
              <div
                className="docx-preview mx-auto max-w-3xl prose prose-slate"
                dangerouslySetInnerHTML={{ __html: docxHtml }}
              />
            </div>
          )}

          {!loading && !error && !isPdf && !isDocx && objectUrl && (
            <div className="flex h-full flex-col items-center justify-center text-center p-8">
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Preview isn't supported for this file type.
              </p>
              <a
                href={objectUrl}
                download={filename}
                className="mt-4 flex items-center gap-2 rounded-xl bg-brand-500 px-5 py-3 text-sm font-bold text-white shadow-soft transition-all hover:bg-brand-600"
              >
                <Download size={16} /> Download instead
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
