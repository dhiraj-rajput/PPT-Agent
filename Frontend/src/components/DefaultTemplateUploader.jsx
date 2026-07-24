import { useEffect, useRef, useState } from 'react';
import { Upload, FileCheck2, Trash2, Eye, Loader2 } from 'lucide-react';
import api from '../lib/api';
import DocPreviewModal from './DocPreviewModal';

/**
 * DefaultTemplateUploader
 * -------------------------
 * Lets the user upload a .docx template and set it as the org-wide default
 * used by Proposal Builder, RFP Auto-Respond, and RFP upload whenever a
 * generation request doesn't attach a one-off template of its own.
 */
export default function DefaultTemplateUploader({ compact = false }) {
  const [meta, setMeta] = useState(null);
  const [loadingMeta, setLoadingMeta] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const fileInputRef = useRef(null);

  const refreshMeta = async () => {
    setLoadingMeta(true);
    try {
      const data = await api.getDefaultTemplate();
      setMeta(data?.has_template ? data : null);
    } catch (e) {
      setMeta(null);
    } finally {
      setLoadingMeta(false);
    }
  };

  useEffect(() => {
    refreshMeta();
  }, []);

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.docx')) {
      setError('Please choose a .docx file.');
      return;
    }
    setUploading(true);
    setError(null);
    try {
      await api.uploadDefaultTemplate(file);
      await refreshMeta();
    } catch (e) {
      setError(e.message || 'Upload failed');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleRemove = async () => {
    setUploading(true);
    try {
      await api.deleteDefaultTemplate();
      setMeta(null);
    } catch (e) {
      setError(e.message || 'Failed to remove template');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className={`rounded-xl border border-dashed ${meta ? 'border-brand-300 bg-brand-50/40 dark:bg-navy-900/40' : 'border-slate-300 dark:border-navy-700'} p-4 ${compact ? '' : 'mb-6'}`}>
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3 min-w-0">
          <div className={`flex h-10 w-10 items-center justify-center rounded-lg shrink-0 ${meta ? 'bg-brand-100 text-brand-600 dark:bg-navy-800' : 'bg-slate-100 text-slate-500 dark:bg-navy-800'}`}>
            {meta ? <FileCheck2 size={18} /> : <Upload size={18} />}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-bold text-navy-900 dark:text-white">
              Default Proposal Template
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
              {loadingMeta
                ? 'Checking for a saved default…'
                : meta
                ? `Using "${meta.original_filename}" as the default .docx template for all generations.`
                : 'Upload a .docx to use as the default template whenever you don\'t attach one to a specific request.'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {meta && (
            <>
              <button
                onClick={() => setPreviewing(true)}
                className="flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-navy-700 px-3 py-2 text-xs font-semibold text-navy-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-navy-900 transition-colors"
              >
                <Eye size={14} /> View
              </button>
              <button
                onClick={handleRemove}
                disabled={uploading}
                className="flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-navy-700 px-3 py-2 text-xs font-semibold text-red-600 hover:bg-red-50 dark:hover:bg-navy-900 transition-colors disabled:opacity-50"
              >
                <Trash2 size={14} /> Remove
              </button>
            </>
          )}
          <label className="flex items-center gap-1.5 rounded-lg bg-brand-500 px-3 py-2 text-xs font-bold text-white hover:bg-brand-600 transition-colors cursor-pointer disabled:opacity-50">
            {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
            {meta ? 'Replace' : 'Upload .docx'}
            <input
              ref={fileInputRef}
              type="file"
              accept=".docx"
              className="hidden"
              onChange={handleFileChange}
              disabled={uploading}
            />
          </label>
        </div>
      </div>

      {error && <p className="mt-2 text-xs font-semibold text-red-600">{error}</p>}

      {previewing && (
        <DocPreviewModal
          title={meta?.original_filename || 'Default Template'}
          subtitle="Org-wide default proposal template"
          filename={meta?.original_filename || 'template.docx'}
          fetchBlob={() => api.viewDefaultTemplateBlob()}
          onClose={() => setPreviewing(false)}
        />
      )}
    </div>
  );
}
