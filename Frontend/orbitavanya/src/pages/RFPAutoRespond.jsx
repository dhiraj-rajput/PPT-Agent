import { useState, useRef, useEffect } from 'react';
import { Upload, FileText, Loader2, CheckCircle, AlertCircle, Download, X, Zap, FileCheck } from 'lucide-react';
import { api } from '../lib/api.jsx';
import PreGenerationWizard from '../components/PreGenerationWizard.jsx';
/**
 * RFPAutoRespond.jsx
 * -------------------
 * Upload an RFP document (PDF / DOCX / TXT) and optionally a .docx template.
 * The OrbitAvanya AI pipeline (Parse → Inventory → Competitor Intel → Strategy → Generate)
 * runs in the background and produces a ready-to-send proposal document.
 *
 * Equivalent to the standalone "BidForge" pipeline, now integrated into the
 * main OrbitAvanya platform with the same AI fallback chain used everywhere else.
 */

const POLL_INTERVAL_MS = 2500;

export default function RFPAutoRespond() {
  const [rfpFiles, setRfpFiles] = useState([]);
  const [templateFile, setTemplateFile] = useState(null);
  const [taskId, setTaskId] = useState(null);
  const [taskState, setTaskState] = useState(null); // { progress, status, message, filename }
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [wizardModal, setWizardModal] = useState(null);
  const rfpRef = useRef(null);
  const tplRef = useRef(null);
  const pollRef = useRef(null);

  // -------------------------------------------------------------------------
  // Polling
  // -------------------------------------------------------------------------

  useEffect(() => {
    const savedTaskId = localStorage.getItem('rfp_active_task_id');
    if (savedTaskId) {
      setTaskId(savedTaskId);
      api.getRfpRespondStatus(savedTaskId)
        .then((state) => {
          setTaskState(state);
        })
        .catch(() => {
          localStorage.removeItem('rfp_active_task_id');
        });
    }
  }, []);

  useEffect(() => {
    if (!taskId) return;
    pollRef.current = setInterval(async () => {
      try {
        const state = await api.getRfpRespondStatus(taskId);
        setTaskState(state);
        if (state.status === 'completed' || state.status === 'failed') {
          clearInterval(pollRef.current);
        }
      } catch {
        clearInterval(pollRef.current);
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(pollRef.current);
  }, [taskId]);

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  async function handleSubmit(e) {
    e.preventDefault();
    if (rfpFiles.length === 0) {
      setError('Please select at least one RFP file to upload.');
      return;
    }
    setError('');
    
    // Open the pre-generation wizard
    setWizardModal({
      mode: 'prime', // Assuming direct RFP response is acting as prime
      solicitation: rfpFiles.map(f => f.name).join(', '),
      tender_title: 'RFP Auto-Respond',
    });
  }

  async function handleWizardConfirm(wizardConfig) {
    setWizardModal(null);
    setUploading(true);
    setTaskId(null);
    setTaskState(null);
    try {
      const { task_id } = await api.uploadRfp(rfpFiles, templateFile, wizardConfig);
      setTaskId(task_id);
      localStorage.setItem('rfp_active_task_id', task_id);
      setTaskState({ progress: 0, status: 'processing', message: 'Upload received, queuing pipeline...', filename: null });
    } catch (err) {
      setError(err.message || 'Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  }

  function reset() {
    clearInterval(pollRef.current);
    localStorage.removeItem('rfp_active_task_id');
    setRfpFiles([]);
    setTemplateFile(null);
    setTaskId(null);
    setTaskState(null);
    setError('');
  }

  // -------------------------------------------------------------------------
  // Derived state & helpers
  // -------------------------------------------------------------------------

  const isRunning = taskState && taskState.status === 'processing';
  const isCompleted = taskState && taskState.status === 'completed';
  const isFailed = taskState && taskState.status === 'failed';
  const progress = taskState?.progress ?? 0;

  const handleDownload = async (e) => {
    e.preventDefault();
    if (!taskState?.filename) return;
    try {
      const blob = await api.downloadRfpRespond(taskState.filename);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = taskState.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Download failed:", err);
      alert("Failed to download file.");
    }
  };

  const getStepStatus = (index) => {
    if (!taskState) return 'pending';
    const bounds = [15, 35, 65, 100];
    const prevBound = index === 0 ? 0 : bounds[index - 1];
    const currentBound = bounds[index];
    
    if (isCompleted) return 'completed';
    
    if (isFailed) {
      if (progress > prevBound && progress <= currentBound) {
        return 'failed';
      }
      if (progress > currentBound) return 'completed';
      return 'pending';
    }
    
    if (isRunning) {
      if (progress > prevBound && progress <= currentBound) {
        return 'active';
      }
      if (progress > currentBound) {
        return 'completed';
      }
    }
    
    return 'pending';
  };

  const getStepStyles = (index, defaultIcon) => {
    const status = getStepStatus(index);
    if (status === 'completed') {
      return {
        card: 'border-emerald-500/30 dark:border-emerald-500/20 bg-emerald-50/10 dark:bg-emerald-950/5',
        container: 'bg-emerald-50 dark:bg-emerald-900/30',
        icon: CheckCircle,
        iconClass: 'text-emerald-500 dark:text-emerald-400',
        statusText: 'Completed',
        statusClass: 'text-emerald-500 font-bold',
      };
    }
    if (status === 'active') {
      return {
        card: 'border-brand-500/30 dark:border-brand-500/20 ring-1 ring-brand-500/20 bg-brand-50/20 dark:bg-brand-950/10 animate-pulse',
        container: 'bg-brand-100 dark:bg-brand-900/40',
        icon: Loader2,
        iconClass: 'text-brand-600 dark:text-brand-400 animate-spin',
        statusText: 'Processing...',
        statusClass: 'text-brand-500 font-bold',
      };
    }
    if (status === 'failed') {
      return {
        card: 'border-rose-500/30 dark:border-rose-500/20 bg-rose-50/10 dark:bg-rose-950/5',
        container: 'bg-rose-50 dark:bg-rose-900/30',
        icon: AlertCircle,
        iconClass: 'text-rose-500 dark:text-rose-400',
        statusText: 'Failed',
        statusClass: 'text-rose-500 font-bold',
      };
    }
    return {
      card: 'border-slate-100 dark:border-navy-800 bg-white dark:bg-navy-900',
      container: 'bg-brand-50 dark:bg-brand-900/30',
      icon: defaultIcon,
      iconClass: 'text-brand-600 dark:text-brand-400',
      statusText: '',
      statusClass: '',
    };
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-extrabold text-navy-900 dark:text-white flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-accent-orange shadow-soft">
            <Zap size={20} className="text-white" />
          </span>
          RFP Auto-Respond
        </h1>
        <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400">
          Upload an RFP document and let OrbitAvanya AI write a complete, ready-to-send proposal for you —
          automatically checking our inventory, researching market pricing, and generating a professional document.
        </p>
      </div>

      {/* Pipeline steps overview */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { icon: FileText, label: 'Parse RFP', desc: 'Extract requirements & scope' },
          { icon: FileCheck, label: 'Inventory Check', desc: 'Match our offerings' },
          { icon: Zap, label: 'Market Intel', desc: 'Competitor pricing analysis' },
          { icon: Download, label: 'Generate Proposal', desc: 'Professional PDF' },
        ].map(({ icon: Icon, label, desc }, i) => {
          const styles = getStepStyles(i, Icon);
          const RenderedIcon = styles.icon;
          return (
            <div
              key={i}
              className={`flex items-start gap-3 rounded-xl border p-4 shadow-card transition-all ${styles.card}`}
            >
              <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${styles.container}`}>
                <RenderedIcon size={16} className={styles.iconClass} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-bold text-navy-900 dark:text-white truncate">{i + 1}. {label}</p>
                <p className="text-[11px] text-slate-400 dark:text-slate-500 truncate">{desc}</p>
                {styles.statusText && (
                  <p className={`text-[10px] mt-0.5 ${styles.statusClass}`}>{styles.statusText}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Upload form */}
      {!taskId && (
        <form
          onSubmit={handleSubmit}
          className="rounded-2xl border border-slate-100 dark:border-navy-800 bg-white dark:bg-navy-900 p-6 shadow-card space-y-5"
        >
          <h2 className="text-sm font-bold text-navy-900 dark:text-white">Upload Documents</h2>

          {/* RFP File */}
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-slate-500 dark:text-slate-400">
              RFP Document <span className="text-rose-500">*</span>
            </label>
            <div
              className="group flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-200 dark:border-navy-700 bg-slate-50 dark:bg-navy-950/50 px-6 py-8 text-center transition-colors hover:border-brand-400 hover:bg-brand-50/40 dark:hover:bg-brand-900/10"
              onClick={() => rfpRef.current?.click()}
            >
              {rfpFiles.length > 0 ? (
                <div className="w-full space-y-2 px-2" onClick={(e) => e.stopPropagation()}>
                  <p className="text-xs font-semibold text-slate-500 mb-2">Selected RFP Documents:</p>
                  {rfpFiles.map((file, idx) => (
                    <div key={idx} className="flex items-center justify-between gap-2 p-2 bg-white dark:bg-navy-900 border border-slate-200 dark:border-navy-800 rounded-lg">
                      <div className="flex items-center gap-2">
                        <FileText size={16} className="text-brand-600 shrink-0" />
                        <span className="text-xs font-semibold text-navy-900 dark:text-white truncate max-w-[250px]">{file.name}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setRfpFiles(prev => prev.filter((_, i) => i !== idx))}
                        className="rounded-full p-0.5 text-slate-400 hover:text-rose-500"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() => rfpRef.current?.click()}
                    className="mt-3 text-xs font-bold text-brand-600 hover:underline inline-block"
                  >
                    + Add more files
                  </button>
                </div>
              ) : (
                <>
                  <Upload size={28} className="text-slate-300 dark:text-slate-600 group-hover:text-brand-500 transition-colors" />
                  <p className="text-sm font-semibold text-navy-900 dark:text-white">
                    Drop your RFP files here or <span className="text-brand-600">browse</span>
                  </p>
                  <p className="text-xs text-slate-400 dark:text-slate-500">Supports PDF, DOCX, TXT (Multiple files allowed)</p>
                </>
              )}
            </div>
            <input
              ref={rfpRef}
              type="file"
              accept=".pdf,.docx,.doc,.txt"
              className="hidden"
              multiple
              onChange={(e) => {
                if (e.target.files) {
                  setRfpFiles(prev => [...prev, ...Array.from(e.target.files)]);
                }
              }}
            />
          </div>

          {/* Template (optional) */}
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-slate-500 dark:text-slate-400">
              Proposal Template <span className="text-slate-400">(optional .docx)</span>
            </label>
            <div
              className="group flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 dark:border-navy-700 bg-slate-50 dark:bg-navy-950/50 px-4 py-3 hover:border-brand-400 transition-colors"
              onClick={() => tplRef.current?.click()}
            >
              <FileText size={16} className="text-slate-400 dark:text-slate-500 group-hover:text-brand-500" />
              {templateFile ? (
                <div className="flex flex-1 items-center gap-2">
                  <span className="text-sm text-navy-900 dark:text-white font-medium">{templateFile.name}</span>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); setTemplateFile(null); }}
                    className="ml-auto rounded-full p-0.5 text-slate-400 hover:text-rose-500"
                  >
                    <X size={14} />
                  </button>
                </div>
              ) : (
                <span className="text-sm text-slate-400 dark:text-slate-500">
                  Upload your company's .docx template (headers, logo, branding preserved)
                </span>
              )}
            </div>
            <input
              ref={tplRef}
              type="file"
              accept=".docx"
              className="hidden"
              onChange={(e) => setTemplateFile(e.target.files?.[0] || null)}
            />
            <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">
              Leave empty to use the default OrbitAvanya-branded proposal template.
            </p>
          </div>

          {error && (
            <div className="flex items-center gap-2 rounded-lg bg-rose-50 dark:bg-rose-900/20 px-3.5 py-2.5 text-sm text-rose-700 dark:text-rose-400">
              <AlertCircle size={16} className="shrink-0" />
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={uploading || rfpFiles.length === 0}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-500 to-accent-orange py-3 text-sm font-bold text-white shadow-soft transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            {uploading ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
            {uploading ? 'Uploading…' : 'Generate Proposal'}
          </button>
        </form>
      )}

      {/* Progress card */}
      {taskState && (
        <div className="rounded-2xl border border-slate-100 dark:border-navy-800 bg-white dark:bg-navy-900 p-6 shadow-card space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-navy-900 dark:text-white">
              {isCompleted ? '✅ Proposal Ready!' : isFailed ? '❌ Pipeline Failed' : '⚙️ Generating Proposal…'}
            </h2>
            {(isCompleted || isFailed) && (
              <button
                onClick={reset}
                className="rounded-lg border border-slate-200 dark:border-navy-700 px-3 py-1.5 text-xs font-semibold text-navy-900 dark:text-white hover:bg-slate-50 dark:hover:bg-navy-800"
              >
                Start New
              </button>
            )}
          </div>

          {/* Progress bar */}
          <div className="space-y-1.5">
            <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-navy-800">
              <div
                className={`h-full rounded-full transition-all duration-700 ${
                  isFailed
                    ? 'bg-rose-500'
                    : isCompleted
                    ? 'bg-emerald-500'
                    : 'bg-gradient-to-r from-brand-500 to-accent-orange'
                }`}
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="flex items-center justify-between">
              <p className="text-xs text-slate-500 dark:text-slate-400">{taskState.message}</p>
              <span className="text-xs font-bold text-navy-900 dark:text-white">{progress}%</span>
            </div>
          </div>

          {/* Status indicators */}
          {isRunning && (
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <Loader2 size={14} className="animate-spin text-brand-500" />
              Pipeline running — this usually takes 1–3 minutes…
            </div>
          )}

          {isFailed && (
            <div className="flex items-start gap-2 rounded-lg bg-rose-50 dark:bg-rose-900/20 px-3.5 py-2.5 text-sm text-rose-700 dark:text-rose-400">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              <div>
                <p className="font-semibold">Pipeline failed</p>
                <p className="text-xs mt-0.5">{taskState.message}</p>
              </div>
            </div>
          )}

          {isCompleted && taskState.filename && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 rounded-lg bg-emerald-50 dark:bg-emerald-900/20 px-3.5 py-2.5 text-sm text-emerald-700 dark:text-emerald-400">
                <CheckCircle size={16} className="shrink-0" />
                Your proposal has been generated and is ready to download.
              </div>
              <button
                onClick={handleDownload}
                className="w-full flex items-center justify-center gap-2 rounded-xl bg-emerald-500 py-3 text-sm font-bold text-white shadow-soft hover:bg-emerald-600 transition-colors"
              >
                <Download size={16} />
                Download Proposal ({taskState.filename})
              </button>
            </div>
          )}
        </div>
      )}

      {wizardModal && (
        <PreGenerationWizard
          mode={wizardModal.mode}
          solicitation={wizardModal.solicitation}
          tender_title={wizardModal.tender_title}
          onClose={() => setWizardModal(null)}
          onConfirmGenerate={handleWizardConfirm}
        />
      )}
    </div>
  );
}
