import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Globe, Mail, Video, Landmark, CheckCircle2, XCircle, Loader2, FileText, Bot, Search
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
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">Google Meet (One-Click OAuth)</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 flex-1 mb-2">
        {status.connected
          ? `Linked${status.connectedEmail ? ` as ${status.connectedEmail}` : ''}. Meeting links are created automatically.`
          : 'Browser consent for auto-generating meeting links.'}
      </p>
      {error && <p className="mt-2 text-xs text-tomato-600 mb-2">{error}</p>}
      <button
        onClick={status.connected ? handleDisconnect : handleConnect}
        disabled={connecting || loading}
        className={`mt-auto w-full rounded-lg py-2 text-xs font-semibold disabled:opacity-60 transition-all ${
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
// SAM.gov API
// ---------------------------------------------------------------------------

function SamGovCard({ notify, onEdit }) {
  const [status, setStatus] = useState({ connected: false, apiKey: '' });
  const [loading, setLoading] = useState(true);

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

      <div className="mt-auto space-y-2">
        <button
          onClick={() => onEdit({
            name: 'samgov',
            label: 'SAM.gov',
            fields: [{ key: 'SAM_GOV_API_KEY', label: 'API Key', type: 'password' }],
            onSuccess: loadStatus
          })}
          className="w-full rounded-lg py-2 text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors"
        >
          Edit / Configure
        </button>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// LinkedIn, Companies House, SMTP, Docling, Ollama, WebSearch
// ---------------------------------------------------------------------------

function LinkedInCard({ notify, onEdit }) {
  const [status, setStatus] = useState({ connected: false, expired: false });
  const [loading, setLoading] = useState(true);

  async function loadStatus() {
    setLoading(true);
    try {
      if (api.getLinkedinStatus) {
        const res = await api.getLinkedinStatus();
        setStatus(res);
        if (res.expired || !res.connected) {
          notify('LinkedIn Expired', 'Please update your session cookie (li_at) to continue automated research.', '/integrations');
        }
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStatus();
  }, [notify]);

  return (
    <Card className="flex flex-col">
      {(status.expired || !status.connected) && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/30 dark:text-rose-400 font-semibold mb-3">
          ⚠️ LinkedIn Cookie Expired: Please update your session cookie (li_at) to continue automated research.
        </div>
      )}
      <div className="flex items-start justify-between">
         <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-blue-500 dark:bg-blue-500/10">
           <Globe size={19} />
         </div>
         <ConnectionPill connected={status.connected && !status.expired} checking={loading} />
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">LinkedIn Auto-Researcher</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 mb-2 flex-1">
        Automated research for companies and contacts.
      </p>
      <button onClick={() => onEdit({
          name: 'linkedin',
          label: 'LinkedIn',
          fields: [{ key: 'LINKEDIN_LI_AT', label: 'Cookie token (li_at string)', type: 'password' }],
          onSuccess: (formData) => {
             if (formData && formData.LINKEDIN_LI_AT) {
                // Optimistically clear the error
                setStatus({ connected: true, expired: false });
             }
             loadStatus();
          }
      })} className="mt-auto w-full rounded-lg py-2 text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors">
        Edit / Configure
      </button>
    </Card>
  )
}

function CompaniesHouseCard({ onEdit }) {
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
         <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-50 text-indigo-500 dark:bg-indigo-500/10">
           <Landmark size={19} />
         </div>
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">Companies House UK API</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 mb-2 flex-1">
        Company data and filings from UK Companies House.
      </p>
      <button onClick={() => onEdit({
          name: 'companies_house',
          label: 'Companies House UK',
          fields: [{ key: 'COMPANIES_HOUSE_KEY', label: 'API Key', type: 'password' }]
      })} className="mt-auto w-full rounded-lg py-2 text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors">
        Edit / Configure
      </button>
    </Card>
  )
}

function SmtpCard({ onEdit }) {
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
         <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-50 text-emerald-500 dark:bg-emerald-500/10">
           <Mail size={19} />
         </div>
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">Email SMTP Server</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 mb-2 flex-1">
        Send emails directly from the platform.
      </p>
      <button onClick={() => onEdit({
          name: 'smtp',
          label: 'Email SMTP',
          fields: [
            { key: 'SMTP_HOST', label: 'Base URL / Host', type: 'text' },
            { key: 'SMTP_PORT', label: 'Port', type: 'text', optional: true },
            { key: 'SMTP_USER', label: 'Username', type: 'text' },
            { key: 'SMTP_PASS', label: 'Password', type: 'password' }
          ]
      })} className="mt-auto w-full rounded-lg py-2 text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors">
        Edit / Configure
      </button>
    </Card>
  )
}

function DoclingCard() {
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
         <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-purple-50 text-purple-500 dark:bg-purple-500/10">
           <FileText size={19} />
         </div>
         <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 dark:bg-emerald-500/10 px-2.5 py-1 text-[11px] font-bold text-emerald-700 dark:text-emerald-400 border border-emerald-200/60 dark:border-emerald-900/40">
           Active (No API Key Required)
         </span>
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">Docling OCR Engine</p>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 leading-relaxed mb-3 flex-1">
        Local CPU document processing for PDFs, tables, and forms by IBM Research. Runs 100% locally on your machine — <strong>no API key, account, or setup needed</strong>.
      </p>
      <div className="rounded-xl bg-slate-50 dark:bg-navy-900 p-2.5 text-[11px] font-semibold text-slate-500 dark:text-slate-400 text-center border border-slate-100 dark:border-navy-800">
        ✓ Built-in Local Engine (Installed & Ready)
      </div>
    </Card>
  );
}

function OllamaCard({ onEdit }) {
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
         <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-purple-50 text-purple-500 dark:bg-purple-500/10">
           <Bot size={19} />
         </div>
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">Ollama AI Inference (Codespaces)</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 mb-2 flex-1">
        Local/Codespaces LLM inference configuration.
      </p>
      <button onClick={() => onEdit({
          name: 'ollama',
          label: 'Ollama AI',
          fields: [
            { key: 'OLLAMA_HOST', label: 'Host URL (e.g. https://humble-xylophone-gxqjr7g474pv29g6q-11434.app.github.dev)', type: 'text' },
            { key: 'OLLAMA_MODEL', label: 'Model Name (e.g. gemma4:e4b)', type: 'text' },
            { key: 'OLLAMA_API_KEY', label: 'API Key', type: 'password', optional: true },
            { key: 'OLLAMA_TIMEOUT', label: 'Timeout in Seconds', type: 'text', optional: true }
          ]
      })} className="mt-auto w-full rounded-lg py-2 text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors">
        Edit / Configure
      </button>
    </Card>
  )
}

function ZoomCard({ onEdit }) {
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
         <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-blue-500 dark:bg-blue-500/10">
           <Video size={19} />
         </div>
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">Zoom Video Meetings (Optional)</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 mb-2 flex-1">
        Zoom API integration for meetings.
      </p>
      <button onClick={() => onEdit({
          name: 'zoom',
          label: 'Zoom Video Meetings',
          fields: [
            { key: 'ZOOM_ACCOUNT_ID', label: 'ZOOM_ACCOUNT_ID (Optional)', type: 'text' },
            { key: 'ZOOM_CLIENT_ID', label: 'ZOOM_CLIENT_ID (Optional)', type: 'text' },
            { key: 'ZOOM_CLIENT_SECRET', label: 'ZOOM_CLIENT_SECRET (Optional)', type: 'password' }
          ]
      })} className="mt-auto w-full rounded-lg py-2 text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors">
        Edit / Configure
      </button>
    </Card>
  )
}

function GoogleCloudOAuthCard({ onEdit }) {
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
         <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-blue-500 dark:bg-blue-500/10">
           <Globe size={19} />
         </div>
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">Google Cloud OAuth Client Credentials</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 mb-2 flex-1">
        Manual GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET configuration.
      </p>
      <button onClick={() => onEdit({
          name: 'google_workspace',
          label: 'Google Cloud OAuth',
          fields: [
            { key: 'GOOGLE_CLIENT_ID', label: 'GOOGLE_CLIENT_ID', type: 'text' },
            { key: 'GOOGLE_CLIENT_SECRET', label: 'GOOGLE_CLIENT_SECRET', type: 'password' }
          ]
      })} className="mt-auto w-full rounded-lg py-2 text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors">
        Edit / Configure
      </button>
    </Card>
  )
}

function SerpApiCard({ onEdit }) {
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
         <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-teal-50 text-teal-500 dark:bg-teal-500/10">
           <Search size={19} />
         </div>
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">SerpAPI Search Engine (Optional)</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 mb-2 flex-1">
        Google search results via SerpAPI.
      </p>
      <button onClick={() => onEdit({
          name: 'serpapi',
          label: 'SerpAPI',
          fields: [
            { key: 'SERPAPI_API_KEY', label: 'SERPAPI_API_KEY (Optional)', type: 'password' }
          ]
      })} className="mt-auto w-full rounded-lg py-2 text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors">
        Edit / Configure
      </button>
    </Card>
  )
}

function FirecrawlCard({ onEdit }) {
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
         <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-orange-50 text-orange-500 dark:bg-orange-500/10">
           <Globe size={19} />
         </div>
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">Firecrawl Web Scraper (Optional)</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 mb-2 flex-1">
        Advanced web scraping capabilities.
      </p>
      <button onClick={() => onEdit({
          name: 'firecrawl',
          label: 'Firecrawl',
          fields: [
            { key: 'FIRECRAWL_API_KEY', label: 'FIRECRAWL_API_KEY (Optional)', type: 'password' }
          ]
      })} className="mt-auto w-full rounded-lg py-2 text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors">
        Edit / Configure
      </button>
    </Card>
  )
}

function TavilyCard({ onEdit }) {
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
         <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-50 text-indigo-500 dark:bg-indigo-500/10">
           <Search size={19} />
         </div>
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">Tavily AI Search (Optional)</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 mb-2 flex-1">
        AI-optimized search engine API.
      </p>
      <button onClick={() => onEdit({
          name: 'tavily',
          label: 'Tavily',
          fields: [
            { key: 'TAVILY_API_KEY', label: 'TAVILY_API_KEY (Optional)', type: 'password' }
          ]
      })} className="mt-auto w-full rounded-lg py-2 text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors">
        Edit / Configure
      </button>
    </Card>
  )
}

function GeminiCard({ onEdit }) {
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
         <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-blue-500 dark:bg-blue-500/10">
           <Bot size={19} />
         </div>
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">Gemini AI LLM (Optional)</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 mb-2 flex-1">
        Google Gemini AI integration.
      </p>
      <button onClick={() => onEdit({
          name: 'gemini',
          label: 'Gemini AI',
          fields: [
            { key: 'GEMINI_API_KEY', label: 'GEMINI_API_KEY (Optional)', type: 'password' }
          ]
      })} className="mt-auto w-full rounded-lg py-2 text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors">
        Edit / Configure
      </button>
    </Card>
  )
}

function OpenRouterCard({ onEdit }) {
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
         <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-purple-50 text-purple-500 dark:bg-purple-500/10">
           <Bot size={19} />
         </div>
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">OpenRouter AI LLM (Optional)</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 mb-2 flex-1">
        Access multiple LLMs via OpenRouter.
      </p>
      <button onClick={() => onEdit({
          name: 'openrouter',
          label: 'OpenRouter',
          fields: [
            { key: 'OPENROUTER_API_KEY', label: 'API Key', type: 'password' },
            { key: 'OPENROUTER_MODEL', label: 'Model Name (e.g. nvidia/nemotron-3-ultra-550b-a55b:free)', type: 'text', optional: true }
          ]
      })} className="mt-auto w-full rounded-lg py-2 text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors">
        Edit / Configure
      </button>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Edit Integration Modal
// ---------------------------------------------------------------------------

function EditIntegrationModal({ isOpen, onClose, integration, onSave }) {
  const [formData, setFormData] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setFormData({});
    }
  }, [isOpen, integration]);

  if (!isOpen || !integration) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave(integration.name, formData);
      if (integration.onSuccess) {
        integration.onSuccess(formData);
      }
      onClose();
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl dark:bg-navy-900">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-bold text-navy-900 dark:text-white">Edit {integration.label}</h2>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600"><XCircle size={20}/></button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
           {integration.fields.map(f => (
             <div key={f.key}>
                <label className="block text-xs font-bold text-slate-500 mb-1">{f.label}{f.optional && <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span>}</label>
                <input 
                  type={f.type || 'text'} 
                  value={formData[f.key] || ''} 
                  onChange={e => setFormData({...formData, [f.key]: e.target.value})}
                  className="w-full rounded-lg border border-slate-200 p-2 text-sm dark:bg-navy-800 dark:border-navy-700 dark:text-white" 
                />
             </div>
           ))}
           <div className="flex justify-end gap-2 mt-6">
             <button type="button" onClick={onClose} className="rounded-lg px-4 py-2 text-sm font-semibold bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300">Cancel</button>
             <button type="submit" disabled={saving} className="rounded-lg px-4 py-2 text-sm font-semibold bg-brand-500 text-white hover:bg-brand-600">{saving ? 'Saving...' : 'Save'}</button>
           </div>
        </form>
      </div>
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

  const [isModalOpen, setModalOpen] = useState(false);
  const [activeIntegration, setActiveIntegration] = useState(null);

  const handleEdit = (integrationDef) => {
    setActiveIntegration(integrationDef);
    setModalOpen(true);
  };

  const handleSaveConfig = async (name, configData) => {
    if (api.saveIntegrationConfig) {
      await api.saveIntegrationConfig(name, configData);
    } else if (api.saveIntegration) {
      await api.saveIntegration(name, configData);
    }
    notify(`${activeIntegration?.label || 'Integration'} configuration saved`, 'Your changes have been applied.', '/integrations');
  };

  return (
    <div>
      <PageHeader title="Integrations" subtitle="Connect OrbitAvanya with the tools your team already uses" />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 mt-6">
        <GoogleMeetCard notify={notify} />
        <GoogleCloudOAuthCard onEdit={handleEdit} />
        <ZoomCard onEdit={handleEdit} />
        <SamGovCard notify={notify} onEdit={handleEdit} />
        <LinkedInCard notify={notify} onEdit={handleEdit} />
        <CompaniesHouseCard onEdit={handleEdit} />
        <SmtpCard onEdit={handleEdit} />
        <DoclingCard />
        <OllamaCard onEdit={handleEdit} />
        <SerpApiCard onEdit={handleEdit} />
        <FirecrawlCard onEdit={handleEdit} />
        <TavilyCard onEdit={handleEdit} />
        <GeminiCard onEdit={handleEdit} />
        <OpenRouterCard onEdit={handleEdit} />
      </div>

      <EditIntegrationModal 
        isOpen={isModalOpen} 
        onClose={() => setModalOpen(false)} 
        integration={activeIntegration} 
        onSave={handleSaveConfig} 
      />
    </div>
  );
}
