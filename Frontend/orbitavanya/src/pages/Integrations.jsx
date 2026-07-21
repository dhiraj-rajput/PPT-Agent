import { useEffect, useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Sparkles, Globe, CalendarClock, Mail, Video, Landmark,
  CheckCircle2, XCircle, Eye, EyeOff, Loader2, ShieldCheck, ChevronDown,
} from 'lucide-react';
import { PageHeader, Card } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';
import { useNotifications } from '../context/NotificationContext.jsx';

// ---------------------------------------------------------------------------
// Small shared building blocks
// ---------------------------------------------------------------------------

function ConnectionPill({ connected, checking }) {
  if (checking) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 dark:bg-navy-800 px-2.5 py-1 text-[11px] font-bold text-slate-500 dark:text-slate-400">
        <Loader2 size={11} className="animate-spin" /> Checking…
      </span>
    );
  }
  return connected ? (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 dark:bg-emerald-500/10 px-2.5 py-1 text-[11px] font-bold text-emerald-700 dark:text-emerald-400">
      <CheckCircle2 size={12} /> Connected
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 dark:bg-navy-800 px-2.5 py-1 text-[11px] font-bold text-slate-500 dark:text-slate-400">
      <XCircle size={12} /> Not Connected
    </span>
  );
}

function KeyField({ label, value, onChange, placeholder }) {
  const [show, setShow] = useState(false);
  const filled = Boolean((value || '').trim());
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <label className="block text-[11px] font-bold text-slate-500 dark:text-slate-400">{label}</label>
        <span
          className={`flex items-center gap-1 text-[10px] font-bold ${
            filled ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-300 dark:text-slate-600'
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${filled ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-navy-700'}`} />
          {filled ? 'Set' : 'Not set'}
        </span>
      </div>
      <div className="relative">
        <input
          type={show ? 'text' : 'password'}
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full text-xs rounded-lg border border-slate-200 bg-white px-3 py-2 pr-8 outline-none focus:border-brand-400 dark:border-navy-700 dark:bg-navy-900 text-navy-900 dark:text-white transition-colors"
        />
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          tabIndex={-1}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-300 hover:text-slate-500 dark:hover:text-slate-400"
        >
          {show ? <EyeOff size={13} /> : <Eye size={13} />}
        </button>
      </div>
    </div>
  );
}

function SectionGroup({ icon: Icon, iconColor, title, description, connected, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-2xl border border-slate-100 dark:border-navy-800 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 bg-slate-50/60 dark:bg-navy-850/60 px-4 py-3.5 text-left hover:bg-slate-50 dark:hover:bg-navy-850 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${iconColor}`}>
            <Icon size={16} />
          </div>
          <div>
            <p className="text-sm font-bold text-navy-900 dark:text-white">{title}</p>
            <p className="text-[11px] text-slate-400 dark:text-slate-500">{description}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <ConnectionPill connected={connected} />
          <ChevronDown size={16} className={`text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
        </div>
      </button>
      {open && <div className="p-4 space-y-3 bg-white dark:bg-navy-900">{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Google Meet (working, OAuth-based)
// ---------------------------------------------------------------------------

function GoogleMeetCard({ notify }) {
  const [status, setStatus] = useState({ connected: false, connectedEmail: '' });
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState('');
  const [searchParams] = useSearchParams();

  async function loadStatus() {
    setLoading(true);
    try {
      const data = await api.googleIntegrationStatus();
      setStatus(data);
    } catch {
      // leave status as "not connected"
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStatus();
  }, []);

  useEffect(() => {
    const result = searchParams.get('google');
    if (result === 'connected') {
      loadStatus();
      notify('Google Meet connected', 'Meetings will now auto-generate Google Meet links.', '/integrations');
    }
    if (result === 'error') setError('Could not connect Google. Please try again.');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  async function handleConnect() {
    setError('');
    setConnecting(true);
    try {
      const { url } = await api.googleIntegrationAuthUrl();
      window.location.href = url;
    } catch (err) {
      setError(err.message || 'Could not start Google connection.');
      setConnecting(false);
    }
  }

  async function handleDisconnect() {
    setError('');
    setLoading(true);
    try {
      await api.googleDisconnect();
      setStatus({ connected: false, connectedEmail: '' });
      notify('Google Meet disconnected', 'Meeting links will no longer be auto-generated.', '/integrations');
    } catch (err) {
      setError(err.message || 'Could not disconnect Google integration.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-red-50 dark:bg-red-500/10 text-red-500">
          <Video size={19} />
        </div>
        <ConnectionPill connected={status.connected} checking={loading} />
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">Google Meet</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 flex-1">
        {status.connected
          ? `Linked${status.connectedEmail ? ` as ${status.connectedEmail}` : ''}. Meeting links are created automatically.`
          : 'Auto-create Google Meet links when scheduling meetings.'}
      </p>
      {error && <p className="mt-2 text-xs text-tomato-600">{error}</p>}
      <button
        onClick={status.connected ? handleDisconnect : handleConnect}
        disabled={connecting || loading}
        className={`mt-4 w-full rounded-lg py-2 text-xs font-semibold disabled:opacity-60 transition-all ${
          status.connected
            ? 'bg-rose-50 text-rose-600 hover:bg-rose-100 border border-transparent'
            : 'bg-brand-500 text-white hover:bg-brand-600'
        }`}
      >
        {connecting ? 'Redirecting…' : status.connected ? 'Disconnect' : 'Connect Google Meet'}
      </button>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// SAM.gov (working, API key based)
// ---------------------------------------------------------------------------

function SamGovCard({ notify }) {
  const [status, setStatus] = useState({ connected: false, apiKey: '' });
  const [loading, setLoading] = useState(true);
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [show, setShow] = useState(false);

  async function loadStatus() {
    setLoading(true);
    try {
      const data = await api.getSamStatus();
      setStatus(data);
    } catch {
      // leave as not connected
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStatus();
  }, []);

  async function handleConnect(e) {
    e.preventDefault();
    if (!apiKeyInput.trim()) return;
    setError('');
    setSaving(true);
    try {
      await api.connectSam(apiKeyInput.trim());
      await loadStatus();
      setApiKeyInput('');
      notify('SAM.gov connected', 'Federal tenders can now be auto-imported using your key.', '/integrations');
    } catch (err) {
      setError(err.message || 'Failed to save SAM.gov API key.');
    } finally {
      setSaving(false);
    }
  }

  async function handleDisconnect() {
    setError('');
    setLoading(true);
    try {
      await api.disconnectSam();
      setStatus({ connected: false, apiKey: '' });
      notify('SAM.gov disconnected', 'Automatic tender imports have been paused.', '/integrations');
    } catch (err) {
      setError(err.message || 'Could not disconnect SAM.gov.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-sky-50 dark:bg-sky-500/10 text-sky-500">
          <Landmark size={19} />
        </div>
        <ConnectionPill connected={status.connected} checking={loading} />
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">SAM.gov API</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 mb-2 flex-1">
        {status.connected ? `Key configured: ${status.apiKey}` : 'Auto-import federal tenders and opportunities using your key.'}
      </p>

      {error && <p className="text-xs text-tomato-600 mb-2">{error}</p>}

      {!status.connected ? (
        <form onSubmit={handleConnect} className="space-y-2 mt-2">
          <div className="relative">
            <input
              type={show ? 'text' : 'password'}
              value={apiKeyInput}
              onChange={(e) => setApiKeyInput(e.target.value)}
              placeholder="Enter SAM.gov API Key..."
              className="w-full text-xs rounded-lg border border-slate-200 bg-white p-2 pr-8 outline-none focus:border-brand-400 dark:border-navy-700 dark:bg-navy-900 text-navy-900 dark:text-white"
              disabled={saving || loading}
            />
            <button
              type="button"
              onClick={() => setShow((s) => !s)}
              tabIndex={-1}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-300 hover:text-slate-500"
            >
              {show ? <EyeOff size={13} /> : <Eye size={13} />}
            </button>
          </div>
          <button
            type="submit"
            disabled={!apiKeyInput.trim() || saving || loading}
            className="w-full rounded-lg py-2 text-xs font-semibold bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-60"
          >
            {saving ? 'Saving...' : 'Connect Key'}
          </button>
        </form>
      ) : (
        <button
          onClick={handleDisconnect}
          disabled={loading}
          className="mt-4 w-full rounded-lg py-2 text-xs font-semibold bg-rose-50 text-rose-600 hover:bg-rose-100 border border-transparent disabled:opacity-60 transition-all"
        >
          Disconnect
        </button>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// System-level API keys, grouped into collapsible, status-aware sections
// ---------------------------------------------------------------------------

function SystemConfigCard({ notify }) {
  const [keys, setKeys] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });

  async function fetchKeys() {
    setLoading(true);
    try {
      const data = await api.getEnvKeys();
      setKeys(data);
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Failed to load system configuration.' });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchKeys();
  }, []);

  const filled = (k) => Boolean((keys[k] || '').trim());

  const groupStatus = useMemo(
    () => ({
      ai: filled('GEMINI_API_KEY') || filled('OPENROUTER_API_KEY') || filled('OLLAMA_API_KEY'),
      search: filled('TAVILY_API_KEY') || filled('FIRECRAWL_API_KEY') || filled('LINKEDIN_LI_AT'),
      meetings:
        (filled('GOOGLE_CLIENT_ID') && filled('GOOGLE_CLIENT_SECRET')) ||
        (filled('ZOOM_ACCOUNT_ID') && filled('ZOOM_CLIENT_ID') && filled('ZOOM_CLIENT_SECRET')),
      smtp: filled('SMTP_HOST') && filled('SMTP_USER') && filled('SMTP_PASS'),
    }),
    [keys]
  );

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setMessage({ type: '', text: '' });
    try {
      const res = await api.saveEnvKeys(keys);
      setMessage({ type: 'success', text: res.message || 'Configuration saved successfully!' });
      const updated = await api.getEnvKeys();
      setKeys(updated);
      notify('System configuration updated', 'API keys & integration settings were saved.', '/integrations');
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Failed to save configuration.' });
    } finally {
      setSaving(false);
    }
  }

  const handleChange = (key, val) => {
    setKeys((prev) => ({ ...prev, [key]: val }));
  };

  if (loading) {
    return (
      <div className="mt-8 rounded-2xl bg-white dark:bg-navy-900 border border-slate-100 dark:border-navy-800 p-10 shadow-soft flex items-center justify-center gap-2 text-sm text-slate-400">
        <Loader2 size={16} className="animate-spin" /> Loading system environment keys…
      </div>
    );
  }

  return (
    <div className="mt-8 rounded-2xl bg-white dark:bg-navy-900 border border-slate-100 dark:border-navy-800 p-6 shadow-soft">
      <div className="border-b border-slate-100 dark:border-navy-800 pb-4 mb-6 flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 dark:bg-brand-500/10 text-brand-600 dark:text-brand-400">
          <ShieldCheck size={18} />
        </div>
        <div>
          <h3 className="text-base font-extrabold text-navy-900 dark:text-white">System API Keys & Configuration</h3>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
            Manage API tokens, scraping sessions, and outbound email settings. Each group shows whether it's
            currently configured — fill in a group's keys and save to connect it.
          </p>
        </div>
      </div>

      {message.text && (
        <div
          className={`mb-5 rounded-xl border p-4 text-xs font-semibold ${
            message.type === 'error'
              ? 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-950 dark:bg-rose-950/20'
              : 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-950 dark:bg-emerald-950/20'
          }`}
        >
          {message.text}
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-4">
        <SectionGroup
          icon={Sparkles}
          iconColor="bg-brand-50 dark:bg-brand-500/10 text-brand-600 dark:text-brand-400"
          title="AI & Core LLM Services"
          description="Powers matching, summarization, and proposal drafting"
          connected={groupStatus.ai}
        >
          <KeyField label="Gemini API Key" value={keys.GEMINI_API_KEY} onChange={(v) => handleChange('GEMINI_API_KEY', v)} placeholder="Enter Gemini key..." />
          <KeyField label="OpenRouter API Key" value={keys.OPENROUTER_API_KEY} onChange={(v) => handleChange('OPENROUTER_API_KEY', v)} placeholder="Enter OpenRouter key..." />
          <KeyField label="Ollama API Key" value={keys.OLLAMA_API_KEY} onChange={(v) => handleChange('OLLAMA_API_KEY', v)} placeholder="Enter Ollama API key..." />
        </SectionGroup>

        <SectionGroup
          icon={Globe}
          iconColor="bg-sky-50 dark:bg-sky-500/10 text-sky-600 dark:text-sky-400"
          title="Search & Web Scraping"
          description="Sources company and market intelligence from the web"
          connected={groupStatus.search}
        >
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <KeyField label="Tavily API Key" value={keys.TAVILY_API_KEY} onChange={(v) => handleChange('TAVILY_API_KEY', v)} placeholder="Enter Tavily Search key..." />
            <KeyField label="Firecrawl API Key" value={keys.FIRECRAWL_API_KEY} onChange={(v) => handleChange('FIRECRAWL_API_KEY', v)} placeholder="Enter Firecrawl key..." />
          </div>
          <KeyField label="LinkedIn li_at Cookie" value={keys.LINKEDIN_LI_AT} onChange={(v) => handleChange('LINKEDIN_LI_AT', v)} placeholder="Enter LinkedIn li_at cookie string..." />
        </SectionGroup>

        <SectionGroup
          icon={CalendarClock}
          iconColor="bg-violet-50 dark:bg-violet-500/10 text-violet-600 dark:text-violet-400"
          title="Meetings & Calendar"
          description="Powers scheduling links for Google Meet and Zoom"
          connected={groupStatus.meetings}
        >
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <KeyField label="Google Client ID" value={keys.GOOGLE_CLIENT_ID} onChange={(v) => handleChange('GOOGLE_CLIENT_ID', v)} placeholder="Enter Google client ID..." />
            <KeyField label="Google Client Secret" value={keys.GOOGLE_CLIENT_SECRET} onChange={(v) => handleChange('GOOGLE_CLIENT_SECRET', v)} placeholder="Enter client secret..." />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <KeyField label="Zoom Account ID" value={keys.ZOOM_ACCOUNT_ID} onChange={(v) => handleChange('ZOOM_ACCOUNT_ID', v)} placeholder="Enter Zoom Account ID..." />
            <KeyField label="Zoom Client ID" value={keys.ZOOM_CLIENT_ID} onChange={(v) => handleChange('ZOOM_CLIENT_ID', v)} placeholder="Enter Zoom Client ID..." />
            <KeyField label="Zoom Secret" value={keys.ZOOM_CLIENT_SECRET} onChange={(v) => handleChange('ZOOM_CLIENT_SECRET', v)} placeholder="Enter client secret..." />
          </div>
        </SectionGroup>

        <SectionGroup
          icon={Mail}
          iconColor="bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
          title="Outbound Mail (SMTP)"
          description="Sends proposal, campaign, and alert emails"
          connected={groupStatus.smtp}
        >
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="sm:col-span-2">
              <KeyField label="SMTP Host" value={keys.SMTP_HOST} onChange={(v) => handleChange('SMTP_HOST', v)} placeholder="E.g., smtp.gmail.com" />
            </div>
            <KeyField label="SMTP Port" value={keys.SMTP_PORT} onChange={(v) => handleChange('SMTP_PORT', v)} placeholder="E.g., 465" />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <KeyField label="SMTP Username" value={keys.SMTP_USER} onChange={(v) => handleChange('SMTP_USER', v)} placeholder="E.g., user@domain.com" />
            <KeyField label="SMTP Password" value={keys.SMTP_PASS} onChange={(v) => handleChange('SMTP_PASS', v)} placeholder="Enter app password..." />
          </div>
          <KeyField label="Sender From Email" value={keys.SMTP_FROM} onChange={(v) => handleChange('SMTP_FROM', v)} placeholder="E.g., OrbitAvanya <sender@domain.com>" />
        </SectionGroup>

        <div className="flex items-center justify-between border-t border-slate-100 dark:border-navy-800 pt-5">
          <p className="text-[10px] text-slate-400">
            * Fields showing **** are already saved — leave them untouched to keep the existing value.
          </p>
          <button
            type="submit"
            disabled={saving}
            className="rounded-xl bg-brand-500 hover:bg-brand-600 px-6 py-2.5 text-xs font-bold text-white shadow-soft transition-colors disabled:opacity-50"
          >
            {saving ? 'Saving Changes...' : 'Save Configuration'}
          </button>
        </div>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function Integrations() {
  const { createAlert } = useNotifications();

  async function notify(title, message, link) {
    try {
      await createAlert(title, message, link);
    } catch {
      // Notifications are best-effort — never block the integration flow.
    }
  }

  return (
    <div>
      <PageHeader title="Integrations" subtitle="Connect OrbitAvanya with the tools your team already uses" />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <GoogleMeetCard notify={notify} />
        <SamGovCard notify={notify} />
      </div>

      <SystemConfigCard notify={notify} />
    </div>
  );
}
