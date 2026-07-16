import { useState, useRef, useEffect, useCallback } from 'react';
import { UploadCloud, FileText, LayoutTemplate, X, Download, Sparkles } from 'lucide-react';
import { PageHeader, Card, ProgressBar } from '../components/ui/Common.jsx';

const API_BASE = 'http://localhost:8000/api';

function DropZone({ label, hint, file, onFile, accept, icon: Icon }) {
  const inputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onFile(f);
  };

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed p-8 text-center transition-colors ${
        dragOver ? 'border-brand-500 bg-brand-50 dark:bg-brand-500/10' : 'border-slate-200 dark:border-navy-800 hover:border-brand-400'
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
      />
      {file ? (
        <div className="flex items-center gap-2 rounded-full bg-brand-100 px-3 py-1.5 text-sm font-semibold text-brand-700 dark:bg-brand-500/20 dark:text-brand-300">
          <FileText size={14} />
          <span className="max-w-[220px] truncate">{file.name}</span>
          <button
            onClick={(e) => { e.stopPropagation(); onFile(null); }}
            className="ml-1 text-brand-700/60 hover:text-brand-700 dark:text-brand-300/60"
          >
            <X size={14} />
          </button>
        </div>
      ) : (
        <>
          <Icon size={28} className="text-slate-400" />
          <p className="text-sm font-semibold text-navy-900 dark:text-white">{label}</p>
          <p className="text-xs text-slate-500 dark:text-slate-400">{hint}</p>
        </>
      )}
    </div>
  );
}

export default function BidForgeUpload() {
  const [rfpFile, setRfpFile] = useState(null);
  const [templateFile, setTemplateFile] = useState(null);
  const [taskId, setTaskId] = useState(null);
  const [task, setTask] = useState(null);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  useEffect(() => () => stopPolling(), []);

  const pollStatus = useCallback((id) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/bidforge/status/${id}`);
        if (!res.ok) return;
        const data = await res.json();
        setTask(data);
        if (data.status === 'completed' || data.status === 'failed') {
          stopPolling();
        }
      } catch {
        // backend may be briefly unreachable — keep polling
      }
    }, 2000);
  }, []);

  const handleGenerate = async () => {
    if (!rfpFile) {
      setError('Please upload an RFP document first.');
      return;
    }
    setError(null);
    setTask({ progress: 0, status: 'processing', message: 'Uploading files...' });

    const formData = new FormData();
    formData.append('rfp_file', rfpFile);
    if (templateFile) formData.append('template_file', templateFile);

    try {
      const res = await fetch(`${API_BASE}/bidforge/upload`, { method: 'POST', body: formData });
      if (!res.ok) throw new Error('Upload failed. Is the backend running?');
      const data = await res.json();
      setTaskId(data.task_id);
      pollStatus(data.task_id);
    } catch (e) {
      setError(e.message || 'Something went wrong.');
      setTask(null);
    }
  };

  const reset = () => {
    stopPolling();
    setRfpFile(null);
    setTemplateFile(null);
    setTaskId(null);
    setTask(null);
    setError(null);
  };

  return (
    <div>
      <PageHeader
        title="BidForge — RFP Response Generator"
        subtitle="Upload an RFP directly (no email forwarding needed) and generate a full proposal — inventory check, competitor pricing, and a strategy-driven document, optionally rendered into your own template."
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <h3 className="mb-1 flex items-center gap-2 text-sm font-bold text-navy-900 dark:text-white">
            <FileText size={16} className="text-brand-500" /> 1. RFP Document <span className="text-rose-500">*</span>
          </h3>
          <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">PDF, DOCX, or plain text.</p>
          <DropZone
            label="Drop your RFP here"
            hint="or click to browse (.pdf, .docx, .txt)"
            file={rfpFile}
            onFile={setRfpFile}
            accept=".pdf,.docx,.doc,.txt"
            icon={UploadCloud}
          />
        </Card>

        <Card>
          <h3 className="mb-1 flex items-center gap-2 text-sm font-bold text-navy-900 dark:text-white">
            <LayoutTemplate size={16} className="text-brand-500" /> 2. Document Template <span className="text-xs font-normal text-slate-400">(optional)</span>
          </h3>
          <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
            Upload a .docx template and the proposal will be generated into it, keeping your headers/footers and branding. Leave blank to use the default OrbitAvanya template.
          </p>
          <DropZone
            label="Drop your template here"
            hint="or click to browse (.docx only)"
            file={templateFile}
            onFile={setTemplateFile}
            accept=".docx"
            icon={LayoutTemplate}
          />
        </Card>
      </div>

      {error && (
        <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700 dark:border-rose-900 dark:bg-rose-500/10">
          {error}
        </div>
      )}

      <div className="mt-6 flex items-center gap-3">
        <button
          onClick={handleGenerate}
          disabled={task?.status === 'processing'}
          className="inline-flex items-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 text-sm font-bold text-white shadow-soft transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Sparkles size={16} /> Generate Proposal
        </button>
        {(taskId || rfpFile || templateFile) && (
          <button
            onClick={reset}
            className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-50 dark:border-navy-800 dark:text-slate-300 dark:hover:bg-navy-800"
          >
            Start Over
          </button>
        )}
      </div>

      {task && (
        <div className="mt-6">
          <ProgressBar progress={task.progress} message={task.message} status={task.status} />
        </div>
      )}

      {task?.status === 'completed' && task.filename && (
        <div className="mt-4">
          <a
            href={`${API_BASE}/bidforge/download/${task.filename}`}
            className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-5 py-2.5 text-sm font-bold text-white shadow-soft hover:bg-emerald-600"
          >
            <Download size={16} /> Download Proposal
          </a>
        </div>
      )}
    </div>
  );
}
