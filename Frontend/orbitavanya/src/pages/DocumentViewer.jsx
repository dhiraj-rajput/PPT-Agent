import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { FileText, Eye, Clock, ShieldCheck, Loader2 } from 'lucide-react';

export default function DocumentViewer() {
  const [searchParams] = useSearchParams();
  const path = searchParams.get('path') || '';
  const campaignId = searchParams.get('campaignId') || '';
  const leadId = searchParams.get('leadId') || '';
  const filename = searchParams.get('filename') || 'Document Brief';

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!campaignId || !leadId) return;

    // Load the tracking script from the backend
    const script = document.createElement('script');
    script.src = 'http://localhost:5050/tracking/tracker.js';
    script.async = true;
    script.onload = () => {
      if (window.EmailTracker) {
        window.EmailTracker.init({
          campaignId: campaignId,
          leadId: leadId,
          visitorId: leadId
        });
      }
    };
    document.body.appendChild(script);

    return () => {
      document.body.removeChild(script);
    };
  }, [campaignId, leadId]);

  if (!path) {
    return (
      <div className="flex h-screen flex-col items-center justify-center bg-slate-50 p-4 text-center">
        <FileText size={48} className="text-slate-400" />
        <h2 className="mt-4 text-lg font-bold text-navy-900">No Document Path Provided</h2>
        <p className="mt-1 text-sm text-slate-500">Please check your link and try again.</p>
      </div>
    );
  }

  // Stream URL from campaigns router view-file endpoint
  const streamUrl = `http://localhost:5050/api/campaigns/view-file?path=${encodeURIComponent(path)}`;

  return (
    <div className="flex h-screen w-screen flex-col bg-slate-900 font-sans text-white">
      {/* Header bar */}
      <header className="flex h-16 items-center justify-between border-b border-slate-800 bg-slate-950 px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-500/10 text-brand-400">
            <FileText size={18} />
          </div>
          <div className="min-w-0">
            <h1 className="text-sm font-bold truncate max-w-[200px] sm:max-w-md">{filename}</h1>
            <p className="text-[10px] text-slate-500">Orbit Document Viewer</p>
          </div>
        </div>

        {/* Secure stats display */}
        <div className="flex items-center gap-4 text-xs">
          <span className="hidden items-center gap-1.5 rounded-full bg-slate-900 px-3 py-1 text-slate-400 sm:flex">
            <Clock size={12} className="text-brand-400" />
            <span>Time tracked live</span>
          </span>
          <span className="flex items-center gap-1 text-emerald-400 bg-emerald-500/5 border border-emerald-500/10 px-2.5 py-1 rounded-full text-[10px] font-bold">
            <ShieldCheck size={12} />
            Secure Session
          </span>
        </div>
      </header>

      {/* Main viewer block */}
      <main className="relative flex-1 bg-slate-900">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900 z-10">
            <Loader2 className="animate-spin text-brand-400" size={32} />
          </div>
        )}
        <iframe
          src={streamUrl}
          title={filename}
          className="h-full w-full border-0"
          onLoad={() => setLoading(false)}
        />
      </main>
    </div>
  );
}
