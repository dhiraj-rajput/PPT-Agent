/**
 * EmailBeautifyModal.jsx
 * ─────────────────────────────────────────────────────────────────────────
 * Shared AI-powered HTML email builder modal.
 *
 * Props:
 *   subject    {string}   — current email subject (pre-fills prompt)
 *   body       {string}   — current email body text (pre-fills editor)
 *   onConfirm  {fn}       — called with final HTML string
 *   onClose    {fn}       — close without saving
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import {
  X, Sparkles, Loader2, Upload, Image, Copy, Check, Eye,
  Wand2, Code2, RefreshCw, Trash2,
} from 'lucide-react';
import { api } from '../lib/api.jsx';

const STYLES = [
  { id: 'professional', label: 'Professional', desc: 'Corporate, navy & white' },
  { id: 'friendly',     label: 'Friendly',     desc: 'Warm, conversational' },
  { id: 'bold',         label: 'Bold',          desc: 'High-impact, dark theme' },
];

const FALLBACK_HTML = (subject, body) => `<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:30px 0;">
<table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08);">
<tr><td style="background:#1a237e;padding:30px 40px;">
  <h1 style="color:#fff;margin:0;font-size:24px;">${subject || 'Important Message'}</h1>
</td></tr>
<tr><td style="padding:30px 40px;color:#333;font-size:15px;line-height:1.7;">
  ${(body || '').replace(/\n/g, '<br>')}
</td></tr>
<tr><td style="background:#f8f8f8;padding:20px 40px;color:#999;font-size:12px;">
  <p>You received this email because you opted in. <a href="#" style="color:#1a237e;">Unsubscribe</a></p>
</td></tr>
</table></td></tr></table>
</body></html>`;

export default function EmailBeautifyModal({ subject = '', body = '', onConfirm, onClose }) {
  const [html, setHtml]                 = useState(() => body || FALLBACK_HTML(subject, body));
  const [style, setStyle]               = useState('professional');
  const [generating, setGenerating]     = useState(false);
  const [genError, setGenError]         = useState('');
  const [images, setImages]             = useState([]); // [{filename, url, name}]
  const [uploading, setUploading]       = useState(false);
  const [copied, setCopied]             = useState(false);
  const [activePanel, setActivePanel]   = useState('editor'); // 'editor' | 'preview' (mobile)
  const textareaRef                     = useRef(null);
  const fileInputRef                    = useRef(null);

  // ── AI Generate ─────────────────────────────────────────────────────────
  const handleGenerate = useCallback(async (customBody) => {
    setGenerating(true);
    setGenError('');
    const bodyStr = typeof customBody === 'string' ? customBody : '';
    const targetBody = bodyStr || (html.includes('<') ? body || html : html);
    try {
      const res = await api.beautifyEmail({ subject, body: targetBody, style });
      setHtml(res.html || html);
      if (res.usedFallback) {
        setGenError(`AI generation unavailable, showing a basic template instead${res.error ? ` (${res.error})` : ''}.`);
      } else {
        setGenError('');
      }
    } catch (err) {
      setGenError(err?.message || 'AI generation failed — check your API key.');
      // still show fallback
      setHtml(FALLBACK_HTML(subject, targetBody));
    } finally {
      setGenerating(false);
    }
  }, [subject, body, html, style]);

  // Auto-generate on first open if body is plain text or empty
  useEffect(() => {
    const isPlainOrEmpty = !body || !body.includes('<');
    if (isPlainOrEmpty) {
      const draftText = body || "Welcome to our newsletter! We are excited to share some updates with you today.";
      handleGenerate(draftText);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Image Upload ─────────────────────────────────────────────────────────
  const handleImageUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const res = await api.uploadEmailImage(file);
      setImages(prev => [...prev, { filename: res.filename, url: res.url, name: file.name }]);
    } catch {
      // silently fail — user sees no image added
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // ── Insert image tag at cursor ────────────────────────────────────────────
  const insertImage = (img) => {
    const tag = `<img src="${img.url}" alt="${img.name}" style="max-width:100%;height:auto;display:block;margin:16px auto;" />`;
    const ta = textareaRef.current;
    if (ta) {
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const newHtml = html.slice(0, start) + tag + html.slice(end);
      setHtml(newHtml);
      setTimeout(() => {
        ta.selectionStart = ta.selectionEnd = start + tag.length;
        ta.focus();
      }, 0);
    } else {
      setHtml(prev => prev + '\n' + tag);
    }
  };

  // ── Copy HTML ─────────────────────────────────────────────────────────────
  const copyHtml = () => {
    navigator.clipboard.writeText(html).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-navy-950/80 backdrop-blur-md p-3"
      onClick={onClose}
    >
      <div
        className="w-full max-w-6xl bg-white dark:bg-navy-800 rounded-2xl shadow-2xl border border-slate-100 dark:border-navy-700 flex flex-col overflow-hidden"
        style={{ height: '90vh' }}
        onClick={e => e.stopPropagation()}
      >
        {/* ─── Header ─────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-navy-700 px-5 py-3.5 shrink-0">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-brand-500 shadow">
              <Wand2 size={17} className="text-white" />
            </div>
            <div>
              <h3 className="text-sm font-extrabold text-navy-900 dark:text-white">✨ Email Builder</h3>
              <p className="text-[11px] text-slate-400">AI-powered HTML email designer</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Mobile panel toggle */}
            <div className="flex rounded-lg border border-slate-200 dark:border-navy-700 overflow-hidden sm:hidden">
              {['editor', 'preview'].map(p => (
                <button key={p} onClick={() => setActivePanel(p)}
                  className={`px-3 py-1.5 text-[11px] font-semibold transition-colors ${activePanel === p ? 'bg-brand-500 text-white' : 'bg-white dark:bg-navy-800 text-slate-500'}`}>
                  {p === 'editor' ? <Code2 size={13} /> : <Eye size={13} />}
                </button>
              ))}
            </div>
            <button onClick={onClose} className="rounded-lg p-2 text-slate-400 hover:text-navy-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-navy-700 transition-colors">
              <X size={17} />
            </button>
          </div>
        </div>

        {/* ─── Body ────────────────────────────────────────────────────────── */}
        <div className="flex flex-1 overflow-hidden">

          {/* LEFT — Editor panel */}
          <div className={`flex flex-col border-r border-slate-100 dark:border-navy-700 overflow-hidden ${activePanel === 'preview' ? 'hidden sm:flex' : 'flex'} sm:w-[44%] w-full`}>

            {/* Style + Generate */}
            <div className="p-4 border-b border-slate-100 dark:border-navy-700 space-y-3 shrink-0">
              <p className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Style Theme</p>
              <div className="grid grid-cols-3 gap-2">
                {STYLES.map(s => (
                  <button key={s.id} type="button" onClick={() => setStyle(s.id)}
                    className={`rounded-xl border p-2.5 text-left transition-all ${style === s.id ? 'border-brand-500 bg-brand-50 dark:bg-brand-950/30' : 'border-slate-200 dark:border-navy-700 hover:border-brand-300'}`}>
                    <p className={`text-[11px] font-bold ${style === s.id ? 'text-brand-600 dark:text-brand-400' : 'text-navy-900 dark:text-white'}`}>{s.label}</p>
                    <p className="text-[10px] text-slate-400 mt-0.5 leading-tight">{s.desc}</p>
                  </button>
                ))}
              </div>
              <button type="button" onClick={() => handleGenerate()} disabled={generating}
                className="w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-violet-500 to-brand-500 py-2.5 text-xs font-bold text-white shadow hover:opacity-90 disabled:opacity-70 transition-opacity">
                {generating ? <><Loader2 size={14} className="animate-spin" /> Generating…</> : <><Sparkles size={14} /> Generate with AI</>}
              </button>
              {genError && <p className="text-[11px] text-rose-500">{genError}</p>}
            </div>

            {/* Images */}
            <div className="p-4 border-b border-slate-100 dark:border-navy-700 shrink-0">
              <div className="flex items-center justify-between mb-2">
                <p className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Images</p>
                <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploading}
                  className="flex items-center gap-1.5 text-[11px] font-bold text-brand-600 hover:text-brand-700 disabled:opacity-50">
                  {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
                  {uploading ? 'Uploading…' : 'Upload Image'}
                </button>
                <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/gif,image/webp" className="hidden" onChange={handleImageUpload} />
              </div>
              {images.length === 0 ? (
                <p className="text-[11px] text-slate-400 italic">No images uploaded yet. Upload one to insert into your email.</p>
              ) : (
                <div className="space-y-1.5 max-h-28 overflow-y-auto">
                  {images.map((img, i) => (
                    <div key={i} className="flex items-center gap-2 rounded-lg border border-slate-100 dark:border-navy-700 bg-slate-50 dark:bg-navy-900 px-2.5 py-1.5">
                      <Image size={12} className="text-slate-400 shrink-0" />
                      <span className="text-[11px] text-slate-600 dark:text-slate-300 flex-1 truncate">{img.name}</span>
                      <button type="button" onClick={() => insertImage(img)}
                        className="text-[11px] font-bold text-brand-600 hover:text-brand-700 shrink-0">Insert</button>
                      <button type="button" onClick={() => setImages(prev => prev.filter((_, j) => j !== i))}
                        className="text-slate-300 hover:text-rose-500 shrink-0"><Trash2 size={11} /></button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* HTML Editor */}
            <div className="flex-1 flex flex-col overflow-hidden p-4">
              <div className="flex items-center justify-between mb-2">
                <p className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">HTML Editor</p>
                <button type="button" onClick={copyHtml} className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
                  {copied ? <><Check size={12} className="text-emerald-500" /> Copied!</> : <><Copy size={12} /> Copy HTML</>}
                </button>
              </div>
              <textarea
                ref={textareaRef}
                value={html}
                onChange={e => setHtml(e.target.value)}
                className="flex-1 w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-slate-50 dark:bg-navy-900 px-3 py-2.5 font-mono text-[11px] text-slate-700 dark:text-slate-300 resize-none outline-none focus:border-brand-400 dark:focus:border-brand-500 transition-colors"
                spellCheck={false}
                placeholder="<html>...</html>"
              />
            </div>
          </div>

          {/* RIGHT — Preview panel */}
          <div className={`flex flex-col overflow-hidden ${activePanel === 'editor' ? 'hidden sm:flex' : 'flex'} flex-1`}>
            <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100 dark:border-navy-700 shrink-0">
              <div className="flex items-center gap-2">
                <Eye size={14} className="text-slate-400" />
                <p className="text-xs font-bold text-navy-900 dark:text-white">Live Preview</p>
              </div>
              <button type="button" onClick={() => setHtml(FALLBACK_HTML(subject, body))}
                className="flex items-center gap-1.5 text-[11px] text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
                <RefreshCw size={12} /> Reset
              </button>
            </div>
            <div className="flex-1 overflow-hidden bg-slate-100 dark:bg-navy-950 p-4">
              <iframe
                title="email-preview"
                srcDoc={html || '<p style="font-family:sans-serif;color:#94a3b8;padding:20px;">Nothing to preview yet.</p>'}
                className="w-full h-full bg-white rounded-xl shadow-lg"
                sandbox=""
                style={{ border: 'none' }}
              />
            </div>
          </div>
        </div>

        {/* ─── Footer ──────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-end gap-3 border-t border-slate-100 dark:border-navy-700 px-5 py-3.5 shrink-0 bg-white dark:bg-navy-800">
          <button type="button" onClick={onClose}
            className="rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-800 px-5 py-2.5 text-xs font-semibold text-navy-900 dark:text-white hover:bg-slate-50 dark:hover:bg-navy-700 transition-colors">
            Cancel
          </button>
          <button type="button" onClick={() => onConfirm(html)}
            className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-violet-500 to-brand-500 px-6 py-2.5 text-xs font-bold text-white shadow hover:opacity-90 transition-opacity">
            <Check size={14} /> Use This HTML
          </button>
        </div>
      </div>
    </div>
  );
}
